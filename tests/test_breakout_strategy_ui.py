import copy
import unittest
from contextlib import ExitStack
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.testing.v1 import AppTest

from breakout_strategy import BREAKOUT_MODEL_VERSION, breakout_chart
from stock_data import StockDataError


scan_callback = Mock()
chart_callback = Mock()
reference_callback = Mock()
research_callback = Mock()
bookmark_callback = Mock()


def snapshot():
    row = {
        "Symbol": "CLMT", "Name": "Calumet", "Status": "Recent breakout", "Reason": "All rules passed",
        "AsOf": "2026-02-03", "Price": 23.99, "BreakoutDate": "2026-02-03",
        "BreakoutLevel": 23.41, "BreakoutClose": 23.99, "BreakoutReturn": 0.05543,
        "BreakoutVolumeRatio": 1.657, "BaseDepth": 0.2375, "EventVsMA50": 0.191,
        "CloseLocation": 0.993, "SessionsSinceBreakout": 0, "ExtensionFromBreakout": 0.02478,
        "BreakoutHeld": True,
    }
    international = {**row, "Symbol": "AIR.PA", "Name": "Airbus", "SessionsSinceBreakout": 4, "ExtensionFromBreakout": 0.08}
    return {
        "model_version": BREAKOUT_MODEL_VERSION, "universe": "Russell 2000 stocks",
        "requested_symbols": ["CLMT", "AIR.PA", "FAIL", "NONE", "MISSING"],
        "scanned_at": "2026-02-04T08:00:00+00:00", "as_of": "2026-02-03",
        "rows": [
            row, international,
            {**row, "Symbol": "FAIL", "Status": "Failed breakout", "BreakoutHeld": False, "Reason": "Lost pivot"},
            {"Symbol": "NONE", "Status": "No recent breakout", "Reason": "No qualifying event"},
            {"Symbol": "MISSING", "Status": "Unavailable", "Reason": "Insufficient history"},
        ],
    }


class EarlyBreakoutUITests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.scan = self.stack.enter_context(patch(f"{__name__}.scan_callback", return_value=snapshot()))
        history = pd.DataFrame({"Close": [23.99], "Volume": [1000]}, index=pd.to_datetime(["2026-02-03"]))
        self.chart = self.stack.enter_context(patch(f"{__name__}.chart_callback", return_value=history))
        self.reference = self.stack.enter_context(patch(f"{__name__}.reference_callback", return_value=history))
        self.research = self.stack.enter_context(patch(f"{__name__}.research_callback"))
        self.bookmark = self.stack.enter_context(patch(f"{__name__}.bookmark_callback"))
        self.figure = self.stack.enter_context(patch("breakout_strategy_ui.breakout_chart", return_value=go.Figure()))
        clock = self.stack.enter_context(patch("breakout_strategy_ui.datetime"))
        clock.now.return_value = datetime(2026, 10, 25, tzinfo=timezone.utc)

    def ui(self, with_header=False):
        header = (
            "from app import render_page_header\n"
            "render_page_header('Early breakout strategy', 'early_breakout')\n"
        ) if with_header else ""
        return AppTest.from_string(
            header +
            "from breakout_strategy_ui import render_early_breakout\n"
            f"from {__name__} import scan_callback, chart_callback, reference_callback, research_callback, bookmark_callback\n"
            "render_early_breakout(scan_callback, chart_callback, reference_callback, research_callback, bookmark_callback)"
        ).run()

    def run_scan(self):
        ui = self.ui()
        ui.button(key="early_breakout_run").click().run()
        self.assertFalse(ui.exception)
        return ui

    def test_initial_view_never_fetches_and_explains_early_reference(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.scan.assert_not_called()
        self.chart.assert_not_called()
        self.reference.assert_not_called()
        self.assertFalse(ui.get("plotly_chart"))
        self.assertEqual(ui.selectbox(key="early_breakout_universe").value, "Russell 2000 stocks")
        self.assertTrue(any("not the later explosive February 13" in item.value for item in ui.markdown))
        self.assertTrue(any("not the U-shape" in item.value for item in ui.markdown))

    def test_explicit_scan_and_local_filters_preserve_full_audit(self):
        with patch("breakout_strategy_ui.parse_breakout_symbols") as parser:
            ui = self.run_scan()
        parser.assert_not_called()
        self.scan.assert_called_once_with("Russell 2000 stocks", [])
        self.assertEqual([metric.value for metric in ui.metric[:3]], ["4 / 5", "2", "1"])
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["CLMT", "AIR.PA"])
        self.assertEqual(len(ui.dataframe[1].value), 5)
        ui.number_input(key="early_breakout_recent_sessions").set_value(2).run()
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["CLMT"])
        ui.number_input(key="early_breakout_max_extension").set_value(1).run()
        self.assertTrue(any("No matches" in item.value for item in ui.info))
        self.assertEqual(len(ui.dataframe[0].value), 5)
        self.scan.assert_called_once()
        self.chart.assert_not_called()
        self.reference.assert_not_called()

    def test_changed_input_does_not_run_or_relabel_prior_snapshot(self):
        ui = self.run_scan()
        ui.selectbox(key="early_breakout_universe").select("European stocks").run()
        self.scan.assert_called_once()
        self.assertTrue(any("Inputs changed" in item.value for item in ui.warning))
        self.assertTrue(any("Loaded universe: Russell 2000 stocks" in item.value for item in ui.caption))
        self.assertEqual(len(ui.dataframe[0].value), 2)

    def test_failure_preserves_prior_report_and_error_until_success(self):
        ui = self.run_scan()
        saved = copy.deepcopy(ui.session_state["_early_breakout_snapshot"])
        ui.selectbox(key="early_breakout_universe").select("European stocks").run()
        self.scan.side_effect = StockDataError("Provider unavailable")
        ui.button(key="early_breakout_run").click().run()
        self.assertFalse(ui.exception)
        self.assertIn("Provider unavailable", ui.error[0].value)
        self.assertTrue(any("prior successful report" in item.value for item in ui.warning))
        self.assertTrue(any("Inputs changed" in item.value for item in ui.warning))
        self.assertTrue(any("Loaded universe: Russell 2000 stocks" in item.value for item in ui.caption))
        self.assertEqual(ui.session_state["_early_breakout_snapshot"], saved)
        ui.number_input(key="early_breakout_recent_sessions").set_value(2).run()
        self.assertTrue(ui.error)
        self.scan.side_effect = None
        ui.button(key="early_breakout_run").click().run()
        self.assertFalse(ui.error)

    def test_failure_without_prior_report_is_not_empty_success(self):
        self.scan.side_effect = StockDataError("Offline")
        ui = self.run_scan()
        self.assertTrue(ui.error)
        self.assertFalse(ui.dataframe)
        self.assertFalse(any(metric.label == "Qualifying matches" for metric in ui.metric))

    def test_reference_and_selected_charts_are_explicit_and_cached(self):
        ui = self.run_scan()
        ui.button(key="early_breakout_load_reference").click().run()
        self.reference.assert_called_once_with()
        self.chart.assert_not_called()
        ui.button(key="early_breakout_load_chart").click().run()
        self.chart.assert_called_once_with("CLMT")
        self.assertEqual(len(ui.get("plotly_chart")), 2)
        ui.button(key="early_breakout_load_chart").click().run()
        ui.button(key="early_breakout_load_reference").click().run()
        ui.run()
        self.chart.assert_called_once()
        self.reference.assert_called_once()
        ui.selectbox(key="early_breakout_symbol").select("AIR.PA").run()
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.chart.assert_called_once()
        ui.button(key="early_breakout_load_chart").click().run()
        self.assertEqual(self.chart.call_args.args, ("AIR.PA",))
        ui.button(key="early_breakout_run").click().run()
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.reference.assert_called_once()

    def test_chart_errors_are_visible_and_retryable(self):
        ui = self.run_scan()
        self.chart.side_effect = StockDataError("No prices")
        self.reference.return_value = pd.DataFrame()
        ui.button(key="early_breakout_load_chart").click().run()
        self.assertIn("No prices", ui.error[0].value)
        self.assertFalse(ui.button(key="early_breakout_load_chart").disabled)
        ui.button(key="early_breakout_load_reference").click().run()
        self.assertTrue(any("No reference" in item.value for item in ui.error))
        self.assertFalse(ui.button(key="early_breakout_load_reference").disabled)

    def test_real_chart_rejects_malformed_history_without_page_exception(self):
        self.figure.side_effect = breakout_chart
        ui = self.run_scan()
        ui.button(key="early_breakout_load_chart").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Chart for CLMT could not be loaded" in item.value for item in ui.error))
        self.assertTrue(any("Open, High, Low, Close and Volume" in item.value for item in ui.error))
        self.assertFalse(ui.get("plotly_chart"))
        self.assertFalse(ui.button(key="early_breakout_load_chart").disabled)
        ui.button(key="early_breakout_load_reference").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("CLMT reference chart could not be loaded" in item.value for item in ui.error))
        self.assertFalse(ui.get("plotly_chart"))

    def test_global_refresh_preserves_loaded_charts_until_explicit_rescan_and_reload(self):
        import app
        ui = self.ui(with_header=True)
        ui.button(key="early_breakout_run").click().run()
        ui.button(key="early_breakout_load_chart").click().run()
        ui.button(key="early_breakout_load_reference").click().run()
        self.assertEqual(len(ui.get("plotly_chart")), 2)
        saved = copy.deepcopy(ui.session_state["_early_breakout_snapshot"])
        with patch.object(app.st.cache_data, "clear", wraps=app.st.cache_data.clear) as clear:
            ui.button(key="refresh_early_breakout").click().run()
        self.assertFalse(ui.exception)
        clear.assert_called_once_with()
        self.scan.assert_called_once()
        self.chart.assert_called_once()
        self.reference.assert_called_once()
        self.assertEqual(ui.session_state["_early_breakout_snapshot"], saved)
        self.assertEqual(len(ui.get("plotly_chart")), 2)
        self.assertTrue(any("use Run breakout scan to rescan" in item.value for item in ui.caption))
        revised = snapshot()
        revised["rows"][0]["BreakoutLevel"] = 22.0
        self.scan.return_value = revised
        ui.button(key="early_breakout_run").click().run()
        self.assertFalse(ui.exception)
        self.assertNotIn("_early_breakout_selected_chart", ui.session_state)
        self.assertFalse(ui.button(key="early_breakout_load_chart").disabled)
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.chart.assert_called_once()
        ui.button(key="early_breakout_load_chart").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(self.chart.call_count, 2)
        self.assertEqual(self.figure.call_args.args[1]["BreakoutLevel"], 22.0)
        self.reference.assert_called_once()

    def test_handoff_and_bookmark_preserve_international_symbol_and_queue(self):
        bookmark_clicks = []

        def bookmark(symbol, name):
            if st.button(f"Bookmark {symbol}", key=f"bookmark_{symbol}"):
                bookmark_clicks.append((symbol, name))

        self.bookmark.side_effect = bookmark
        ui = self.run_scan()
        ui.selectbox(key="early_breakout_symbol").select("AIR.PA").run()
        ui.button(key="bookmark_AIR.PA").click().run()
        self.assertEqual(bookmark_clicks, [("AIR.PA", "Airbus")])
        ui.button(key="early_breakout_open_research").click().run()
        self.research.assert_called_once_with(
            "AIR.PA", ["CLMT", "AIR.PA"], "Early breakout strategy — Russell 2000 stocks",
        )
        self.chart.assert_not_called()
        ui.number_input(key="early_breakout_max_extension").set_value(5).run()
        ui.button(key="early_breakout_open_research").click().run()
        self.assertEqual(self.research.call_args.args[1], ["CLMT"])

    def test_model_version_mismatch_hides_old_results(self):
        ui = self.run_scan()
        incompatible = copy.deepcopy(ui.session_state["_early_breakout_snapshot"])
        incompatible["model_version"] = "old-model"
        ui.session_state["_early_breakout_snapshot"] = incompatible
        ui.run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.dataframe)
        self.assertTrue(any("incompatible model version" in item.value for item in ui.warning))
        self.assertFalse(any(button.key == "early_breakout_open_research" for button in ui.button))
        self.scan.assert_called_once()

    def test_no_matches_and_unavailable_optional_fields_keep_audit(self):
        result = snapshot()
        result["rows"] = [{"Symbol": "MISSING", "Status": "Unavailable"}]
        result["requested_symbols"] = ["MISSING"]
        self.scan.return_value = result
        ui = self.run_scan()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No matches" in item.value for item in ui.info))
        self.assertEqual(ui.dataframe[0].value.iloc[0]["Reason"], "Data unavailable; no provider reason supplied.")
        self.assertEqual([metric.value for metric in ui.metric[:3]], ["0 / 1", "0", "0"])

    def test_bad_custom_input_never_calls_scan(self):
        ui = self.ui()
        ui.selectbox(key="early_breakout_universe").select("Custom tickers").run()
        self.assertEqual(ui.text_input(key="early_breakout_custom").value, "CLMT")
        ui.text_input(key="early_breakout_custom").set_value("BAD!!!").run()
        ui.button(key="early_breakout_run").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        self.scan.assert_not_called()
        ui.text_input(key="early_breakout_custom").set_value(" ".join(f"T{i}" for i in range(51))).run()
        ui.button(key="early_breakout_run").click().run()
        self.assertTrue(ui.error)
        self.scan.assert_not_called()

    def test_custom_input_parses_and_malformed_snapshot_preserves_prior(self):
        ui = self.run_scan()
        ui.selectbox(key="early_breakout_universe").select("Custom tickers").run()
        ui.text_input(key="early_breakout_custom").set_value("clmt, air.pa").run()
        self.scan.return_value = {}
        ui.button(key="early_breakout_run").click().run()
        self.assertEqual(self.scan.call_args.args, ("Custom tickers", ["CLMT", "AIR.PA"]))
        self.assertTrue(ui.error)
        self.assertEqual(len(ui.dataframe[0].value), 2)

    def test_units_staleness_and_csv_keep_fractional_percentages(self):
        with patch("breakout_strategy_ui.st.download_button") as download:
            ui = self.run_scan()
        self.assertTrue(any("Historical/stale snapshot" in item.value for item in ui.warning))
        self.assertTrue(any("adjusted quote units" in item.value for item in ui.caption))
        from io import StringIO
        exported = pd.read_csv(StringIO(download.call_args.args[1].decode()))
        self.assertAlmostEqual(exported.iloc[0]["BreakoutReturn"], 0.05543)
        self.assertIn('"format": "percent"', ui.dataframe[0].proto.columns)
        self.assertIn('"format": "YYYY-MM-DD"', ui.dataframe[0].proto.columns)


if __name__ == "__main__":
    unittest.main()
