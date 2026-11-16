import io
import json
import unittest
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from unittest.mock import patch

from revenue_outlook import (
    CHECK_LABELS,
    MAX_EXCERPT_CHARS,
    OUTLOOK_INSTRUCTIONS,
    analyze_revenue_outlook,
    evidence_balance,
    outlook_report_json,
    prepare_outlook_sources,
    validate_outlook_assessment,
    validate_revenue_outlook_report,
)
from stock_data import StockDataError


def sources():
    return [{
        "title": "Example Q2 earnings release", "date": "2026-08-01",
        "url": "https://example.com/investors/q2",
        "excerpt": (
            "Example reported funded backlog of USD 120 million, up from USD 100 million "
            "a year earlier. Management expects half to ship in the next twelve months. "
            "The excerpt does not discuss capacity or cancellation rights."
        ),
    }]


def assessment():
    checks = {
        key: {"status": "Insufficient evidence", "reason": "This check is not established by the excerpt.", "source_ids": []}
        for key in CHECK_LABELS
    }
    checks["demand"] = {
        "status": "Supportive", "reason": "Reported funded backlog is higher year over year.", "source_ids": [1],
    }
    return {
        "symbol": "EX", "horizon_months": 12,
        "summary": "The reported backlog is a supportive demand indicator, not a revenue guarantee [1].",
        "summary_source_ids": [1],
        "indicators": [{
            "name": "Funded backlog", "signal": "Supportive", "evidence_type": "Reported result",
            "evidence": "USD 120 million versus USD 100 million a year earlier.",
            "revenue_link": "Funded orders may support future shipments; delivery assumptions are not independently verified.",
            "timing": "Management expects half to ship over twelve months; this is an expectation.",
            "source_ids": [1],
        }],
        "checks": checks, "next_checks": ["Verify cancellation rights and delivery capacity."],
        "limitations": "Only one user-supplied excerpt; authenticity and completeness are unverified.",
    }


def api_response(result=None):
    return {
        "status": "completed", "output": [{
            "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": json.dumps(result if result is not None else assessment())}],
        }],
    }


def report():
    result = assessment()
    return {
        "symbol": "EX", "company_name": "Example", "as_of": "2026-10-01",
        "generated_at": "2026-10-01T12:00:00+00:00", "model": "gpt-4.1-mini", "horizon_months": 12,
        "sources": prepare_outlook_sources(sources(), as_of="2026-10-01"),
        "assessment": result, "evidence_balance": evidence_balance(result),
    }


class RevenueOutlookSourceTests(unittest.TestCase):
    def test_sources_are_dated_bounded_and_ids_are_assigned_by_app(self):
        prepared = prepare_outlook_sources(sources(), as_of="2026-10-01")
        self.assertEqual(prepared[0], {"id": 1, **sources()[0]})
        no_link = sources()
        no_link[0]["url"] = ""
        self.assertEqual(prepare_outlook_sources(no_link, as_of="2026-10-01")[0]["url"], "")
        maximum = [{**sources()[0], "excerpt": str(i) + "x" * (MAX_EXCERPT_CHARS - 1)} for i in range(4)]
        self.assertEqual(len(prepare_outlook_sources(maximum, as_of="2026-10-01")), 4)

    def test_invalid_or_duplicate_sources_are_rejected_not_silently_dropped(self):
        invalid_sources = [
            [], sources() * 2, sources() * 5, None,
            [{**sources()[0], "excerpt": "x" * (MAX_EXCERPT_CHARS + 1)}],
            [{**sources()[0], "title": ""}], [{**sources()[0], "excerpt": ""}],
            [{**sources()[0], "date": "2026-02-30"}], [{**sources()[0], "date": "2026-11-01"}],
            [{**sources()[0], "date": "2026-8-1"}],
            [{**sources()[0], "id": 99}], [{**sources()[0], "private_notes": "not public"}],
        ]
        for value in invalid_sources:
            with self.subTest(value=value), self.assertRaises(StockDataError):
                prepare_outlook_sources(value, as_of="2026-10-01")

    def test_source_urls_cannot_smuggle_credentials_or_non_http_links(self):
        for url in (
            "javascript:alert(1)", "file:///private.txt", "https://user:pass@example.com",
            "https://example.com?api_key=abc", "https://[invalid", "https://example.com?account=private",
        ):
            with self.subTest(url=url), self.assertRaises(StockDataError):
                prepare_outlook_sources([{**sources()[0], "url": url}], as_of="2026-10-01")
        for field in ("title", "excerpt", "url"):
            with self.subTest(field=field), self.assertRaises(StockDataError):
                prepare_outlook_sources(
                    [{**sources()[0], field: "https://example.com/test-key"}],
                    as_of="2026-10-01", api_key="test-key",
                )


class RevenueOutlookValidationTests(unittest.TestCase):
    def test_complete_unknown_is_not_negative_or_positive_growth(self):
        result = assessment()
        result["indicators"] = []
        result["summary"] = "No leading indicators are established by the supplied material."
        result["summary_source_ids"] = []
        result["checks"]["demand"] = {
            "status": "Insufficient evidence", "reason": "Unrelated material.", "source_ids": [],
        }
        self.assertIs(validate_outlook_assessment(result, "EX", 12, [1]), result)
        self.assertEqual(evidence_balance(result), "Insufficient evidence")

    def test_partial_support_and_conflicting_evidence_are_separate_from_coverage(self):
        result = assessment()
        self.assertEqual(evidence_balance(result), "Supportive")
        self.assertEqual(result["checks"]["delivery"]["status"], "Insufficient evidence")
        result["checks"]["delivery"] = {
            "status": "Negative", "reason": "Capacity constraint reported in the excerpt.", "source_ids": [1],
        }
        self.assertEqual(evidence_balance(result), "Mixed")
        result["indicators"][0]["signal"] = "Negative"
        result["checks"]["demand"]["status"] = "Negative"
        self.assertEqual(evidence_balance(result), "Negative")

    def test_wrong_symbol_horizon_schema_or_unbounded_response_is_rejected(self):
        for field, value in (
            ("symbol", "OTHER"), ("horizon_months", True), ("horizon_months", 6),
            ("summary", ""), ("summary", "x" * 2001), ("next_checks", []),
            ("next_checks", ["x"] * 9), ("limitations", None),
            ("indicators", [assessment()["indicators"][0]] * 11),
            ("checks", {}), ("indicators", "positive"),
        ):
            result = assessment()
            result[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(StockDataError):
                validate_outlook_assessment(result, "EX", 12, [1])
        result = assessment()
        result["probability"] = 0.9
        with self.assertRaises(StockDataError):
            validate_outlook_assessment(result, "EX", 12, [1])

    def test_unsupported_duplicate_and_boolean_references_are_rejected(self):
        for ids in ([99], [1, 1], [True], "1", []):
            result = assessment()
            result["indicators"][0]["source_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(StockDataError):
                validate_outlook_assessment(result, "EX", 12, [1])
        for field, value in (
            ("summary", "Unsupported summary [2]."), ("summary_source_ids", []),
        ):
            result = assessment()
            result[field] = value
            with self.subTest(field=field), self.assertRaises(StockDataError):
                validate_outlook_assessment(result, "EX", 12, [1])
        result = assessment()
        result["summary"] = "Unrelated source [2]."
        result["summary_source_ids"] = [2]
        with self.assertRaises(StockDataError):
            validate_outlook_assessment(result, "EX", 12, [1, 2])

    def test_fabricated_links_and_unsupported_check_claims_fail_validation(self):
        mutations = [
            ("evidence_type", "Not established"),
            ("evidence", "Unsupported [99]."),
            ("timing", "Read https://invented.example.com"),
            ("signal", "Guaranteed growth"),
        ]
        for field, value in mutations:
            result = assessment()
            result["indicators"][0][field] = value
            with self.subTest(field=field), self.assertRaises(StockDataError):
                validate_outlook_assessment(result, "EX", 12, [1])
        result = assessment()
        result["checks"]["delivery"]["status"] = "Supportive"
        with self.assertRaises(StockDataError):
            validate_outlook_assessment(result, "EX", 12, [1])

    def test_report_export_preserves_original_inputs_dates_and_company_identity(self):
        saved = report()
        self.assertIs(validate_revenue_outlook_report(saved), saved)
        exported = json.loads(outlook_report_json(saved))
        self.assertEqual(exported["sources"][0]["excerpt"], sources()[0]["excerpt"])
        self.assertEqual(exported["generated_at"], saved["generated_at"])
        self.assertEqual(exported["assessment"]["symbol"], exported["symbol"])
        for field, value in (
            ("symbol", "OTHER"), ("evidence_balance", "Negative"),
            ("generated_at", "not a timestamp"), ("generated_at", "2026-10-01T12:00:00"),
            ("sources", [{**saved["sources"][0], "id": 2}]),
            ("horizon_months", 24),
        ):
            changed = {**saved, field: value}
            with self.subTest(field=field), self.assertRaises(StockDataError):
                validate_revenue_outlook_report(changed)


class RevenueOutlookRequestTests(unittest.TestCase):
    @patch("openai_transport.urlopen")
    def test_exactly_one_nonstoring_request_sends_only_allowlisted_inputs_without_urls_or_tools(self, network):
        network.return_value.__enter__.return_value = io.BytesIO(json.dumps(api_response()).encode())
        result = analyze_revenue_outlook(" ex ", "Example", sources(), 12, "test-key")
        network.assert_called_once()
        request = network.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertFalse(payload["store"])
        self.assertNotIn("tools", payload)
        self.assertTrue(payload["text"]["format"]["strict"])
        context = json.loads(payload["input"])
        self.assertEqual(set(context), {"symbol", "company_name", "as_of", "horizon_months", "sources"})
        self.assertEqual(set(context["sources"][0]), {"id", "title", "date", "excerpt"})
        self.assertNotIn("test-key", request.data.decode())
        self.assertNotIn("example.com", payload["input"])
        self.assertEqual(result["symbol"], "EX")
        self.assertEqual(result["evidence_balance"], "Supportive")
        self.assertEqual(result["sources"][0]["url"], sources()[0]["url"])

    @patch("revenue_outlook.request_openai_response")
    def test_invalid_inputs_never_make_an_api_request(self, request):
        cases = [
            ("EX", "Example", sources(), 12, ""),
            ("bad symbol", "Example", sources(), 12, "test-key"),
            ("EX", "Example", [], 12, "test-key"),
            ("EX", "Example", sources(), 0, "test-key"),
            ("EX", "Example", sources(), True, "test-key"),
            ("EX", "Example test-key", sources(), 12, "test-key"),
        ]
        for args in cases:
            with self.subTest(args=args), self.assertRaises(StockDataError):
                analyze_revenue_outlook(*args)
        with self.assertRaises(StockDataError):
            analyze_revenue_outlook("EX", "Example", sources(), 12, "test-key", model="bad model")
        future = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
        with self.assertRaises(StockDataError):
            analyze_revenue_outlook("EX", "Example", [{**sources()[0], "date": future}], 12, "test-key")
        request.assert_not_called()

    @patch("revenue_outlook.request_openai_response")
    def test_incomplete_refused_tool_calls_malformed_or_unsafe_output_is_not_accepted(self, request):
        invalid = [
            {"status": "incomplete", "output": []},
            {"status": "completed", "error": {"message": "No"}, "output": []},
            {"status": "completed", "output": [{"type": "web_search_call"}]},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
            api_response({**assessment(), "symbol": "OTHER"}),
        ]
        for text in ("not JSON", "x" * 30001, '{"symbol":"EX","symbol":"OTHER"}', "test-key"):
            response = api_response()
            response["output"][0]["content"][0]["text"] = text
            invalid.append(response)
        duplicate = api_response()
        duplicate["output"][0]["content"][0]["text"] = json.dumps(assessment()).replace(
            '"symbol": "EX"', '"symbol": "OTHER", "symbol": "EX"', 1,
        )
        invalid.append(duplicate)
        for response in invalid:
            request.return_value = response
            with self.subTest(response=str(response)[:100]), self.assertRaises(StockDataError):
                analyze_revenue_outlook("EX", "Example", sources(), 12, "test-key")
        self.assertEqual(request.call_count, len(invalid))

    @patch("openai_transport.urlopen")
    def test_provider_errors_are_sanitized_without_retries(self, network):
        network.side_effect = HTTPError("https://api.openai.com", 429, "private test-key", {}, None)
        with self.assertRaises(StockDataError) as error:
            analyze_revenue_outlook("EX", "Example", sources(), 12, "test-key")
        self.assertIn("429", str(error.exception))
        self.assertNotIn("test-key", str(error.exception))
        network.assert_called_once()

    def test_instructions_distinguish_conversion_risk_and_missing_evidence(self):
        for phrase in (
            "untrusted data", "No browsing", "delayed shipments", "current versus total",
            "design wins", "capacity", "Insufficient evidence", "not a leading indicator",
            "not guaranteed commercial revenue", "not establish authenticity",
        ):
            self.assertIn(phrase, OUTLOOK_INSTRUCTIONS)


if __name__ == "__main__":
    unittest.main()
