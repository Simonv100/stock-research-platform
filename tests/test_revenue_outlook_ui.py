import copy
import json
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import revenue_outlook_ui
from revenue_outlook import CHECK_LABELS, DEFAULT_OUTLOOK_MODEL, MAX_EXCERPT_CHARS
from stock_data import StockDataError


SCRIPT = """
import streamlit as st
from revenue_outlook_ui import render_revenue_outlook
symbol = st.selectbox("Test stock", ["EX", "ex", "EX2"])
key = st.text_input("Test API key", type="password")
view = st.radio("Test view", ["Stock research", "Scanner"])
visible = st.checkbox("Show outlook", value=True)
if visible:
    render_revenue_outlook(symbol, "Example", key)
"""

SOURCE = {
    "title": "Quarterly update",
    "date": "2025-01-15",
    "url": "https://example.com/investors/results",
    "excerpt": "Reported backlog increased to $50 million. Management expects delivery within 12 months.",
}


def valid_report(symbol="EX", horizon=12, sources=None):
    return {
        "symbol": symbol,
        "company_name": "Example",
        "as_of": "2025-02-01",
        "generated_at": "2025-02-01T12:00:00+00:00",
        "horizon_months": horizon,
        "model": DEFAULT_OUTLOOK_MODEL,
        "sources": [
            {"id": index + 1, **source}
            for index, source in enumerate(sources if sources is not None else [SOURCE])
        ],
        "assessment": {
            "symbol": symbol,
            "horizon_months": horizon,
            "summary": "Backlog supports potential revenue, but conversion is uncertain [1].",
            "summary_source_ids": [1],
            "indicators": [{
                "name": "Backlog",
                "signal": "Supportive",
                "evidence_type": "Reported result",
                "evidence": "Reported backlog increased to $50 million.",
                "revenue_link": "Orders could become revenue when delivered.",
                "timing": "Management expects delivery within 12 months; not guaranteed.",
                "source_ids": [1],
            }],
            "checks": {
                key: {
                    "status": "Mixed",
                    "reason": "Reported backlog supports demand; cancellations are not quantified.",
                    "source_ids": [1],
                }
                for key in CHECK_LABELS
            },
            "next_checks": ["Check order cancellations and delivery progress in the next release."],
            "limitations": "User-provided excerpts and dates are not independently verified.",
        },
        "evidence_balance": "Mixed",
    }


def widget(ui, collection, label):
    return next(item for item in getattr(ui, collection) if item.label == label)


def input_source(ui, source=None, index=0, symbol="EX"):
    for field, value in (SOURCE if source is None else source).items():
        collection = ui.text_area if field == "excerpt" else ui.text_input
        collection(key=revenue_outlook_ui._widget_key(symbol, field, index)).input(value)
    ui.run()
    return ui


def enable_run(ui, symbol="EX"):
    widget(ui, "text_input", "Test API key").input("test-key").run()
    ui.checkbox(key=revenue_outlook_ui._widget_key(symbol, "consent")).check().run()
    return ui


def run_assessment(ui):
    widget(ui, "button", "Run assessment").click().run()
    return ui


class RevenueOutlookUITests(unittest.TestCase):
    def assert_no_exception(self, ui):
        self.assertFalse(ui.exception, [item.message for item in ui.exception])

    def test_key_and_consent_gate_run_and_no_passive_calls(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook") as analyze, \
                patch("openai_transport.urlopen") as network:
            ui = AppTest.from_string(SCRIPT).run()
            self.assert_no_exception(ui)
            self.assertTrue(widget(ui, "button", "Run assessment").disabled)
            self.assertEqual(
                ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "horizon_months")).value, 12,
            )
            widget(ui, "text_input", "Test API key").input("test-key").run()
            self.assertTrue(widget(ui, "button", "Run assessment").disabled)
            ui.checkbox(key=revenue_outlook_ui._widget_key("EX", "consent")).check().run()
            self.assertFalse(widget(ui, "button", "Run assessment").disabled)
            input_source(ui)
            ui.run()
            ui.radio[0].set_value("Scanner").run()
            ui.selectbox[0].select("EX2").run()
            self.assertTrue(widget(ui, "button", "Run assessment").disabled)
            ui.selectbox[0].select("EX").run()
            widget(ui, "text_input", "Test API key").input("").run()
            self.assertTrue(widget(ui, "button", "Run assessment").disabled)
            analyze.assert_not_called()
            network.assert_not_called()
            captions = " ".join(item.value for item in ui.caption)
            labels = " ".join(item.label for item in ui.checkbox)
            self.assertIn("no web search", captions)
            self.assertIn("not saved across a server restart", captions)
            self.assertIn("URLs are optional and never fetched", captions)
            self.assertIn("Paid API fees", labels)
            self.assertIn("store=false", labels)
            self.assertIn("App chat, notes and holdings are not sent", labels)

    def test_explicit_success_sends_only_selected_inputs_and_renders_five_checks(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze, \
                patch("openai_transport.urlopen") as network:
            ui = AppTest.from_string(SCRIPT).run()
            ui.session_state["holdings"] = "private portfolio"
            ui.session_state["notes"] = "private notes"
            ui.session_state["_stock_chat_sessions"] = {"EX": {"messages": ["private chat"]}}
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            self.assert_no_exception(ui)
            analyze.assert_called_once_with(
                symbol="EX", company_name="Example", sources=[SOURCE],
                horizon_months=12, api_key="test-key", model=DEFAULT_OUTLOOK_MODEL,
            )
            texts = "\n".join(item.value for item in ui.text)
            for label in CHECK_LABELS.values():
                self.assertIn(label, texts)
            self.assertIn("Reported result", texts)
            self.assertIn("$50 million", texts)
            self.assertIn("2025-02-01T12:00:00+00:00", texts)
            self.assertEqual(len(ui.get("download_button")), 1)
            state = ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]
            self.assertNotIn("test-key", json.dumps(state))
            self.assertNotIn("private", json.dumps(analyze.call_args.kwargs))
            ui.run()
            ui.radio[0].set_value("Scanner").run()
            widget(ui, "text_input", "Test API key").input("").run()
            self.assertEqual(len(ui.get("download_button")), 1)
            analyze.assert_called_once()
            network.assert_not_called()

    def test_drafts_survive_source_count_stock_case_and_visibility_changes(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook") as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            input_source(ui)
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(2).run()
            second = {**SOURCE, "title": "Second source", "excerpt": "Usage expanded."}
            input_source(ui, second, index=1)
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "horizon_months")).select(24).run()
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(1).run()
            ui.selectbox[0].select("EX2").run()
            self.assertEqual(ui.text_area[0].value, "")
            self.assertEqual(
                ui.selectbox(key=revenue_outlook_ui._widget_key("EX2", "horizon_months")).value, 12,
            )
            input_source(ui, {**SOURCE, "title": "Other company"}, symbol="EX2")
            ui.selectbox[0].select("ex").run()
            self.assertEqual(ui.text_area[0].value, SOURCE["excerpt"])
            self.assertEqual(
                ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "horizon_months")).value, 24,
            )
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(2).run()
            self.assertEqual(ui.text_area[1].value, second["excerpt"])
            widget(ui, "checkbox", "Show outlook").uncheck().run()
            widget(ui, "checkbox", "Show outlook").check().run()
            self.assertEqual(ui.text_area[1].value, second["excerpt"])
            self.assert_no_exception(ui)
            analyze.assert_not_called()

    def test_edited_sources_and_horizon_label_previous_result_without_relabelling(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            self.assertFalse(ui.warning)
            ui.text_area[0].input("A changed backlog excerpt.").run()
            self.assertTrue(any("Previous assessment of old inputs" in item.value for item in ui.warning))
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "horizon_months")).select(6).run()
            texts = "\n".join(item.value for item in ui.text)
            self.assertIn("12-month horizon", texts)
            self.assertNotIn("6-month horizon", texts)
            self.assertIn(SOURCE["excerpt"], texts)
            self.assertEqual(
                ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]["report"]["horizon_months"], 12,
            )
            analyze.assert_called_once()
            self.assert_no_exception(ui)

    def test_failure_retains_report_timestamp_and_drafts_without_retry(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            original = copy.deepcopy(ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]["report"])
            analyze.side_effect = StockDataError("test-key private upstream response")
            ui.text_area[0].input("Revised excerpt").run()
            run_assessment(ui)
            self.assert_no_exception(ui)
            warnings = " ".join(item.value for item in ui.warning)
            self.assertIn("not a new success", warnings)
            self.assertIn("No automatic retry", warnings)
            self.assertNotIn("private upstream", warnings)
            self.assertNotIn("test-key", warnings)
            self.assertEqual(ui.text_area[0].value, "Revised excerpt")
            self.assertEqual(
                ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]["report"], original,
            )
            self.assertIn(original["generated_at"], " ".join(item.value for item in ui.text))
            ui.run()
            ui.selectbox[0].select("EX2").run()
            ui.selectbox[0].select("EX").run()
            self.assertEqual(analyze.call_count, 2)
            self.assertTrue(any("not a new success" in item.value for item in ui.warning))
            analyze.side_effect = None
            analyze.return_value = valid_report(sources=[{**SOURCE, "excerpt": "Revised excerpt"}])
            run_assessment(ui)
            self.assertFalse(ui.warning)
            self.assertEqual(analyze.call_count, 3)

    def test_clear_only_current_stock_sources_report_consent_and_hidden_drafts(self):
        def respond(**kwargs):
            return valid_report(kwargs["symbol"], kwargs["horizon_months"], kwargs["sources"])

        with patch("revenue_outlook_ui.analyze_revenue_outlook", side_effect=respond) as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(2).run()
            input_source(ui, {**SOURCE, "excerpt": "Hidden draft"}, index=1)
            ui.selectbox[0].select("EX2").run()
            enable_run(ui, symbol="EX2")
            input_source(ui, symbol="EX2")
            run_assessment(ui)
            ui.selectbox[0].select("EX").run()
            widget(ui, "button", "Clear this stock's sources and report").click().run()
            self.assert_no_exception(ui)
            self.assertEqual(ui.text_area[0].value, "")
            self.assertEqual(len(ui.get("download_button")), 0)
            self.assertTrue(widget(ui, "button", "Run assessment").disabled)
            self.assertEqual(
                ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"],
                revenue_outlook_ui._empty_state(),
            )
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(2).run()
            self.assertEqual(ui.text_area[1].value, "")
            ui.selectbox[0].select("EX2").run()
            self.assertEqual(len(ui.get("download_button")), 1)
            self.assertEqual(ui.text_area[0].value, SOURCE["excerpt"])
            self.assertEqual(analyze.call_count, 2)

    def test_blank_sources_omitted_hidden_sources_not_sent_and_partial_sources_preserved(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(3).run()
            input_source(ui, {**SOURCE, "title": "Excluded"}, index=2)
            ui.selectbox(key=revenue_outlook_ui._widget_key("EX", "source_count")).select(2).run()
            run_assessment(ui)
            self.assertEqual(analyze.call_args.kwargs["sources"], [SOURCE])
            ui.text_input(key=revenue_outlook_ui._widget_key("EX", "title", 1)).input("Partial source").run()
            analyze.side_effect = StockDataError("Required date and excerpt are missing.")
            run_assessment(ui)
            self.assertEqual(
                analyze.call_args.kwargs["sources"][1],
                {"title": "Partial source", "date": "", "url": "", "excerpt": ""},
            )
            self.assertTrue(ui.warning)
            self.assertEqual(ui.text_area[0].proto.max_chars, MAX_EXCERPT_CHARS)
            self.assert_no_exception(ui)

    def test_invalid_mocked_reports_and_cross_stock_or_horizon_results_rejected(self):
        invalid = []
        missing = valid_report()
        del missing["assessment"]["summary"]
        invalid.append(missing)
        invalid.append(valid_report(symbol="EX2"))
        invalid.append(valid_report(horizon=6))
        bad_citation = valid_report()
        bad_citation["assessment"]["summary_source_ids"] = [99]
        invalid.append(bad_citation)
        missing_citation = valid_report()
        missing_citation["assessment"]["summary"] = "A summary with no source citation."
        invalid.append(missing_citation)
        unestablished = valid_report()
        unestablished["assessment"]["indicators"][0]["evidence_type"] = "Not established"
        invalid.append(unestablished)
        unsafe_url = valid_report()
        unsafe_url["sources"][0]["url"] = "javascript:alert(1)"
        invalid.append(unsafe_url)
        model_url = valid_report()
        model_url["assessment"]["next_checks"] = ["https://untrusted.example/model-link"]
        invalid.append(model_url)
        invalid.extend([None, {"symbol": "EX"}])
        for bad_report in invalid:
            with self.subTest(report=bad_report), \
                    patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=bad_report) as analyze:
                ui = AppTest.from_string(SCRIPT).run()
                enable_run(ui)
                input_source(ui)
                run_assessment(ui)
                self.assert_no_exception(ui)
                self.assertTrue(ui.warning)
                self.assertIsNone(ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]["report"])
                self.assertEqual(len(ui.get("download_button")), 0)
                ui.run()
                analyze.assert_called_once()

    def test_user_and_model_text_is_inert_and_source_links_only_come_from_validated_sources(self):
        payload = "$50 and $60 ![image](https://untrusted.example/pixel) <img src='https://untrusted.example/x'>"
        model_payload = "$50 and $60 ![image](//untrusted.example/pixel) <b>literal text</b>"
        source = {**SOURCE, "title": payload, "excerpt": payload}
        report = valid_report(sources=[source])
        report["assessment"]["summary"] = model_payload + " [1]"
        report["assessment"]["indicators"][0]["evidence"] = model_payload
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=report), \
                patch("openai_transport.urlopen") as network:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui, source)
            run_assessment(ui)
            self.assert_no_exception(ui)
            self.assertIn(payload, [item.value for item in ui.text])
            self.assertIn(model_payload + " [1]", [item.value for item in ui.text])
            self.assertFalse(any("untrusted.example" in item.value for item in ui.markdown))
            self.assertEqual(len(ui.get("imgs")), 0)
            links = ui.get("link_button")
            self.assertEqual(len(links), 1)
            self.assertEqual(links[0].proto.url, SOURCE["url"])
            network.assert_not_called()

    def test_missing_source_url_is_explicitly_unverified_and_never_a_link(self):
        source = {**SOURCE, "url": ""}
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report(sources=[source])):
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui, source)
            run_assessment(ui)
            self.assert_no_exception(ui)
            self.assertEqual(len(ui.get("link_button")), 0)
            self.assertIn(
                "No source URL supplied; this excerpt is not independently verified.",
                [item.value for item in ui.caption],
            )

    def test_download_uses_validated_report_and_never_requests_an_assessment(self):
        real_download = revenue_outlook_ui.st.download_button
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze, \
                patch("revenue_outlook_ui.st.download_button", wraps=real_download) as download:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            kwargs = download.call_args.kwargs
            self.assertEqual(kwargs["on_click"], "ignore")
            self.assertEqual(kwargs["mime"], "application/json")
            self.assertEqual(json.loads(kwargs["data"])["symbol"], "EX")
            self.assertEqual(json.loads(kwargs["data"])["sources"][0]["excerpt"], SOURCE["excerpt"])
            self.assertTrue(any(
                "JSON export includes the original source excerpts" in item.value for item in ui.caption
            ))
            self.assertNotIn("test-key", kwargs["data"])
            self.assertEqual(ui.get("download_button")[0].proto.ignore_rerun, True)
            ui.run()
            analyze.assert_called_once()

    def test_credentials_redacted_from_drafts_submitted_inputs_reports_and_export(self):
        source = {**SOURCE, "title": "Quarterly test-key update", "excerpt": "Backlog test-key grew."}
        report = valid_report(sources=[source])
        report["assessment"]["summary"] = "Summary test-key sk-abcdefghijklmnopqrstuvwxyz [1]"
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=report) as analyze:
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui, source)
            run_assessment(ui)
            self.assert_no_exception(ui)
            state = ui.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]
            self.assertNotIn("test-key", json.dumps(state))
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", json.dumps(state))
            self.assertNotIn("test-key", str(analyze.call_args.kwargs["sources"]))
            self.assertNotIn("test-key", " ".join(item.value for item in ui.text))

    def test_fully_unknown_assessment_has_no_indicators_and_is_not_presented_as_negative(self):
        report = valid_report()
        report["assessment"]["summary"] = "The provided excerpt does not establish leading revenue evidence."
        report["assessment"]["summary_source_ids"] = []
        report["assessment"]["indicators"] = []
        report["assessment"]["checks"] = {
            key: {
                "status": "Insufficient evidence",
                "reason": "The supplied excerpt does not establish this check.",
                "source_ids": [],
            }
            for key in CHECK_LABELS
        }
        report["evidence_balance"] = "Insufficient evidence"
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=report):
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            self.assert_no_exception(ui)
            self.assertFalse(ui.warning)
            texts = "\n".join(item.value for item in ui.text)
            self.assertIn("Evidence balance: Insufficient evidence", texts)
            self.assertIn("No leading indicators established", texts)
            self.assertNotIn("Negative", texts)
            self.assertEqual(len(ui.get("download_button")), 1)
            self.assertTrue(any(
                "does not mean zero demand or a negative finding" in item.value for item in ui.caption
            ))

    def test_supportive_indicator_with_unknown_checks_discloses_incomplete_coverage(self):
        report = valid_report()
        report["assessment"]["checks"] = {
            key: {
                "status": "Insufficient evidence",
                "reason": "The supplied excerpt does not establish this check.",
                "source_ids": [],
            }
            for key in CHECK_LABELS
        }
        report["evidence_balance"] = "Supportive"
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=report):
            ui = AppTest.from_string(SCRIPT).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            self.assert_no_exception(ui)
            self.assertFalse(ui.warning)
            texts = "\n".join(item.value for item in ui.text)
            self.assertIn("Evidence balance: Supportive", texts)
            for label in CHECK_LABELS.values():
                self.assertIn(f"{label} — Insufficient evidence", texts)
            self.assertTrue(any(
                "unknown checks and incomplete coverage" in item.value
                and "not a revenue forecast" in item.value
                for item in ui.caption
            ))

    def test_browser_sessions_are_independent(self):
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()):
            first = AppTest.from_string(SCRIPT).run()
            enable_run(first)
            input_source(first)
            run_assessment(first)
            second = AppTest.from_string(SCRIPT).run()
            self.assertEqual(second.text_area[0].value, "")
            self.assertIsNone(second.session_state[revenue_outlook_ui.OUTLOOK_STATE_KEY]["EX"]["report"])
            self.assertEqual(len(second.get("download_button")), 0)

    def test_fragment_reruns_and_symbol_switches_do_not_duplicate_assessments(self):
        script = SCRIPT.replace("if visible:", "@st.fragment\ndef panel():")
        script += "\nif visible:\n    panel()\n"
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze:
            ui = AppTest.from_string(script).run()
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            ui.run()
            ui.selectbox[0].select("EX2").run()
            self.assertEqual(len(ui.get("download_button")), 0)
            ui.selectbox[0].select("EX").run()
            self.assertEqual(len(ui.get("download_button")), 1)
            analyze.assert_called_once()
            self.assert_no_exception(ui)

    def test_nested_scanner_expander_and_fragment_work_when_price_history_is_unavailable(self):
        script = SCRIPT.replace("if visible:", "@st.fragment\ndef panel():")
        script += """
with st.expander("Selected-stock research", expanded=True):
    if visible:
        panel()
    st.warning("Price history is unavailable; source-based research remains available.")
"""
        with patch("revenue_outlook_ui.analyze_revenue_outlook", return_value=valid_report()) as analyze, \
                patch("openai_transport.urlopen") as network:
            ui = AppTest.from_string(script).run()
            self.assert_no_exception(ui)
            enable_run(ui)
            input_source(ui)
            run_assessment(ui)
            self.assert_no_exception(ui)
            self.assertEqual(len(ui.get("download_button")), 1)
            self.assertIn(SOURCE["excerpt"], [item.value for item in ui.text])
            self.assertIn(
                "Original source excerpts used in this assessment",
                [item.label for item in ui.expander],
            )
            self.assertTrue(any("Price history is unavailable" in item.value for item in ui.warning))
            ui.run()
            ui.selectbox[0].select("EX2").run()
            ui.selectbox[0].select("EX").run()
            self.assertEqual(len(ui.get("download_button")), 1)
            self.assert_no_exception(ui)
            analyze.assert_called_once()
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
