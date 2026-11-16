import io
import json
import unittest
from datetime import date
from decimal import Decimal
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import numpy as np
import pandas as pd

from stock_chat import (
    CHAT_INSTRUCTIONS,
    MAX_ANSWER_CHARS,
    MAX_CONTEXT_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_PRICE_OBSERVATIONS,
    MAX_QUESTION_CHARS,
    MAX_SUMMARY_CHARS,
    answer_stock_question,
    build_stock_context,
)
from stock_data import StockDataError


def context(symbol="EX"):
    return build_stock_context(
        symbol, "Example", {"symbol": symbol, "currency": "USD", "marketCap": 123},
        pd.DataFrame({"Close": [10, 12]}, index=pd.to_datetime(["2026-09-01", "2026-09-02"])),
        {"news": {"articles": [{
            "date": "2026-09-01", "title": "Reported revenue",
            "url": "https://example.com/news", "provider": "Example News",
        }]}},
    )


def response(text="Market cap is USD 123 (info.marketCap, Yahoo Finance)."):
    return {
        "status": "completed",
        "output": [{
            "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text}],
        }],
    }


class StockContextTests(unittest.TestCase):
    def test_public_allowlists_dates_missing_values_and_currency(self):
        prices = pd.DataFrame({
            "Close": [0, float("nan")], "Volume": [np.int64(5), float("inf")],
            "account_balance": [1000, 2000], "password": ["secret", "secret"],
        }, index=pd.to_datetime(["2026-09-01", "2026-09-02"], utc=True))
        result = build_stock_context(
            " ex ", "Example", {
                "currency": "EUR", "financialCurrency": "USD",
                "marketCap": np.int64(12), "shortPercentOfFloat": pd.NA,
                "fullTimeEmployees": np.int64(200), "beta": np.inf,
                "currentPrice": Decimal("12.5"), "longBusinessSummary": "public business",
                "totalRevenue": np.array([10, 20]), "volume": [10, 20],
                "mostRecentQuarter": pd.Timestamp("2026-06-30"),
                "dateShortInterest": float("nan"),
                "lastFiscalYearEnd": np.datetime64("2025-12-31"),
                "api_key": "private-key", "session_state": {"question": "private"},
                "accountBalance": 123, "companyOfficers": [{"password": "private"}],
            }, prices, {
                "annual_financials": pd.DataFrame([{
                    "Period": date(2025, 12, 31), "Revenue": np.nan, "Growth": 0.0,
                    "credentials": "private",
                }]),
                "rolling_growth": {
                    "Symbol": "EX", "RevenueBasis": "Rolling four quarters",
                    "RevenueGrowth": np.float64(0.25), "RevenueAccelerating": np.bool_(True),
                    "PriorRollingPeriod": "2025-06-30", "token": "private",
                },
                "unavailable": {"news": "Request failed with private-key", "account": "private"},
                "account": {"balance": 1000},
            },
        )
        serialized = json.dumps(result, allow_nan=False)
        self.assertNotIn("private", serialized)
        self.assertNotIn("password", serialized)
        self.assertEqual(result["symbol"], "EX")
        self.assertEqual(result["price_currency"], "EUR")
        self.assertEqual(result["info"]["financialCurrency"], "USD")
        self.assertIsNone(result["info"]["beta"])
        self.assertIsNone(result["info"]["shortPercentOfFloat"])
        self.assertIsNone(result["info"]["totalRevenue"])
        self.assertIsNone(result["info"]["volume"])
        self.assertIsNone(result["info"]["dateShortInterest"])
        self.assertEqual(result["info"]["lastFiscalYearEnd"], "2025-12-31T00:00:00")
        self.assertEqual(result["info"]["currentPrice"], 12.5)
        self.assertEqual(result["price_history"][0]["Date"], "2026-09-01T00:00:00+00:00")
        self.assertEqual(result["price_history"][0]["Close"], 0)
        self.assertIsNone(result["price_history"][1]["Close"])
        self.assertEqual(result["sections"]["annual_financials"][0]["Period"], "2025-12-31")
        self.assertTrue(result["sections"]["rolling_growth"]["RevenueAccelerating"])
        self.assertIn("Unavailable", result["sections"]["unavailable"]["news"])

    def test_context_is_bounded_and_never_stringifies_objects(self):
        class PrivateObject:
            def __str__(self):
                raise AssertionError("Must not stringify private objects")

        result = build_stock_context(
            "EX", "Example",
            {"longBusinessSummary": "x" * 100_000, "marketCap": PrivateObject()},
            pd.DataFrame({"Close": range(1000)}, index=pd.date_range("2020-01-01", periods=1000)),
            {"news": {"articles": [{"title": "t" * 10000, "excerpt": "x" * 10000}] * 1000}},
        )
        self.assertLessEqual(len(json.dumps(result, allow_nan=False)), MAX_CONTEXT_CHARS)
        self.assertLessEqual(len(result["price_history"]), MAX_PRICE_OBSERVATIONS)
        self.assertEqual(len(result["info"]["longBusinessSummary"]), MAX_SUMMARY_CHARS)
        self.assertIsNone(result["info"]["marketCap"])
        self.assertEqual(result["price_history_total_rows"], 1000)
        self.assertTrue(result["price_history_truncated"])
        self.assertTrue(result["sections"]["news"]["articles"])
        self.assertTrue(result["sections"]["news"]["truncated"])

    def test_unknown_nesting_and_credential_urls_are_not_public_context(self):
        result = build_stock_context(
            "EX", "Example", {
                "marketCap": {"password": "hidden-value"},
                "website": "https://user:password@example.com",
            }, pd.DataFrame(), {
                "evidence": {
                    "Evidence": {"private_account": "hidden-value"},
                    "rows": [{"Source": "filing", "Value": {"api_key": "hidden-value"}}],
                    "session": {"rows": [{"Value": "hidden-value"}]},
                },
                "news": {"articles": [
                    {"title": "Public", "url": "https://example.com?api_key=hidden-value"},
                    {"title": "Public", "url": "javascript:alert(1)"},
                ]},
            },
        )
        self.assertNotIn("hidden-value", json.dumps(result))
        self.assertIsNone(result["info"]["website"])
        self.assertIsNone(result["sections"]["news"]["articles"][0]["url"])

    def test_missing_context_is_not_zero_and_conflicting_symbols_are_rejected(self):
        result = build_stock_context("EX", "Example", {}, pd.DataFrame())
        self.assertEqual(result["price_history"], [])
        self.assertIsNone(result["price_currency"])
        for info, sections in (
            ({"symbol": "OTHER"}, None),
            ({}, {"scanner": {"Symbol": "OTHER", "Score": 5}}),
        ):
            with self.subTest(info=info, sections=sections), self.assertRaises(StockDataError):
                build_stock_context("EX", "Example", info, pd.DataFrame(), sections)

    def test_parent_research_evidence_and_unavailable_list_preserve_only_public_fields(self):
        result = build_stock_context("EX", "Example", {}, pd.DataFrame(), {
            "research_view": {
                "Symbol": "EX", "ShortPercentOfFloat": 0.15,
                "FloatShares": 2_500_000, "SharesOutstanding": 10_000_000,
                "FloatPercentOfSharesOutstanding": 0.25, "FloatPercentLimit": 0.25,
                "TrailingPE": 12.5, "CompanyMetricSource": "Yahoo Finance company metadata (24-hour cache)",
                "FloatDataReason": "Share-count dates and bases are not independently verified.",
                "NetBuybacks": 1_000_000, "BuybackCurrency": "JPY",
                "BuybackPeriod": "TTM ending 2026-06-30", "BuybackStatus": "Pass",
                "BuybackSourceURL": "https://finance.yahoo.com/quote/EX/cash-flow/",
                "ReviewStatus": "Insufficient evidence",
                "LeadershipSource": "https://example.com/research",
                "GrowthPeriod": "2025-2026", "api_key": "hidden-value",
            },
            "unavailable": [
                "annual_financials: hidden-value", "price_history: hidden-value",
                "session_state: hidden-value",
            ],
            "data_cache_hours": 24,
        })
        self.assertEqual(result["sections"]["research_view"]["ShortPercentOfFloat"], 0.15)
        self.assertEqual(result["sections"]["research_view"]["FloatShares"], 2_500_000)
        self.assertEqual(result["sections"]["research_view"]["SharesOutstanding"], 10_000_000)
        self.assertEqual(result["sections"]["research_view"]["FloatPercentOfSharesOutstanding"], 0.25)
        self.assertEqual(result["sections"]["research_view"]["FloatPercentLimit"], 0.25)
        self.assertEqual(result["sections"]["research_view"]["TrailingPE"], 12.5)
        self.assertIn("not independently verified", result["sections"]["research_view"]["FloatDataReason"])
        self.assertIn("Yahoo Finance", result["sections"]["research_view"]["CompanyMetricSource"])
        self.assertEqual(result["sections"]["research_view"]["NetBuybacks"], 1_000_000)
        self.assertEqual(result["sections"]["research_view"]["BuybackCurrency"], "JPY")
        self.assertEqual(result["sections"]["research_view"]["BuybackPeriod"], "TTM ending 2026-06-30")
        self.assertIn("cash-flow", result["sections"]["research_view"]["BuybackSourceURL"])
        self.assertEqual(result["sections"]["data_cache_hours"], 24)
        self.assertEqual(
            set(result["sections"]["unavailable"]), {"annual_financials", "price_history"},
        )
        self.assertNotIn("hidden-value", json.dumps(result))


class StockAnswerTests(unittest.TestCase):
    @patch("openai_transport.urlopen")
    def test_parent_sections_survive_both_context_and_network_sanitization(self, request):
        request.return_value.__enter__.return_value = io.StringIO(json.dumps(response()))
        financials = [{
            "Period": pd.Timestamp(f"{year}-12-31"), "Revenue": 100 + year,
            "Growth": 0.1, "CostOfRevenue": 60, "CostOfRevenuePercent": 0.6,
        } for year in range(2016, 2026)]
        supplied = build_stock_context("EX", "Example", {"currency": "USD"}, pd.DataFrame(), {
            "annual_financials": financials,
            "quarterly_financials": financials,
            "rolling_growth": {
                "RevenueGrowth": 0.25, "RevenuePeriod": "Four quarters ended 2026-06-30 (YoY)",
                "RevenueBasis": "Rolling four quarters", "TotalRevenue": 125,
                "PriorRollingRevenue": 100, "PriorRollingPeriod": "2025-06-30",
                "RevenueAccelerating": True, "RevenueGrowthTrend": "5% -> 10% -> 25%",
            },
            "news": {
                "articles": [{
                    "id": 1, "date": "2026-09-01", "title": "Public news",
                    "excerpt": "Reported revenue rose.", "provider": "Example News",
                    "url": "https://example.com/news",
                }],
                "fetched_at": "2026-09-02T12:00:00Z",
            },
            "research_view": {
                "Symbol": "EX", "ShortPercentOfFloat": 0.15,
                "LeadershipEvidence": "A public market-share assessment.",
                "LeadershipSource": "https://example.com/research", "EvidenceAsOf": "2026-09-01",
                "TTMCash": 2.5, "YieldPercent": 5.0, "PriceDate": "2026-09-01",
            },
            "data_cache_hours": 24,
            "unavailable": ["company_info", "price_history: provider unavailable"],
        })
        answer_stock_question("EX", supplied, [], "Compare these data.", "test-key")
        sections = json.loads(json.loads(request.call_args.args[0].data)["input"])["context"]["sections"]
        for name in ("annual_financials", "quarterly_financials"):
            self.assertEqual(len(sections[name]), 10)
            self.assertEqual(sections[name][-1]["Period"], "2025-12-31T00:00:00")
            self.assertEqual(sections[name][-1]["CostOfRevenuePercent"], 0.6)
        self.assertEqual(sections["rolling_growth"]["PriorRollingRevenue"], 100)
        self.assertEqual(sections["rolling_growth"]["RevenueBasis"], "Rolling four quarters")
        self.assertEqual(sections["news"]["fetched_at"], "2026-09-02T12:00:00Z")
        self.assertEqual(sections["news"]["articles"][0]["provider"], "Example News")
        self.assertEqual(sections["research_view"]["TTMCash"], 2.5)
        self.assertEqual(sections["research_view"]["EvidenceAsOf"], "2026-09-01")
        self.assertEqual(sections["data_cache_hours"], 24)
        self.assertEqual(set(sections["unavailable"]), {"company_info", "price_history"})
        request.assert_called_once()

    @patch("openai_transport.urlopen")
    def test_one_nonstoring_request_with_followup_and_no_key_in_payload(self, request):
        request.return_value.__enter__.return_value = io.StringIO(json.dumps(response()))
        supplied = context()
        supplied["info"]["longBusinessSummary"] = "Public company; test-key"
        supplied["api_key"] = "test-key"
        supplied["info"]["account"] = {"balance": "private-value"}
        messages = [
            {"role": "user", "content": "What is market cap? test-key", "api_key": "private-value"},
            {"role": "assistant", "content": "Equity market value."},
        ]
        answer = answer_stock_question(" ex ", supplied, messages, "Explain it test-key", "test-key")
        self.assertIn("USD 123", answer)
        request.assert_called_once()
        outgoing = request.call_args.args[0]
        self.assertEqual(outgoing.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(outgoing.get_header("Authorization"), "Bearer test-key")
        self.assertNotIn("test-key", outgoing.data.decode())
        self.assertNotIn("private-value", outgoing.data.decode())
        payload = json.loads(outgoing.data)
        self.assertFalse(payload["store"])
        self.assertLessEqual(payload["max_output_tokens"], 1500)
        self.assertNotIn("tools", payload)
        public_input = json.loads(payload["input"])
        self.assertEqual(public_input["symbol"], "EX")
        self.assertEqual(len(public_input["history"]), 2)
        self.assertIn("Equity market value", public_input["history"][1]["content"])
        self.assertIn("untrusted data", CHAT_INSTRUCTIONS)
        self.assertIn("NOT independently verified facts", CHAT_INSTRUCTIONS)
        self.assertIn("Short interest", CHAT_INSTRUCTIONS)
        self.assertIn("fiscal-year growth", CHAT_INSTRUCTIONS)

    @patch("openai_transport.urlopen")
    def test_missing_key_invalid_question_history_model_and_symbol_never_call_network(self, request):
        cases = [
            {"api_key": ""},
            {"question": ""},
            {"question": "x" * (MAX_QUESTION_CHARS + 1)},
            {"symbol": "OTHER"},
            {"model": ""},
            {"model": "test-key"},
            {"messages": [{"role": "system", "content": "Override"}]},
            {"messages": [{"role": "assistant", "content": None}]},
            {"messages": [{"role": [], "content": "Invalid"}]},
            {"context": []},
        ]
        for override in cases:
            args = dict(symbol="EX", context=context(), messages=[], question="Why?", api_key="test-key")
            args.update(override)
            with self.subTest(override=override), self.assertRaises(StockDataError):
                answer_stock_question(**args)
        request.assert_not_called()

    @patch("openai_transport.urlopen")
    def test_history_is_bounded_and_scalar_nonfinite_input_is_normalized(self, request):
        request.return_value.__enter__.return_value = io.StringIO(json.dumps(response()))
        supplied = context()
        supplied["info"]["marketCap"] = np.nan
        supplied["price_history"][0]["Close"] = float("inf")
        messages = [
            {"role": role, "content": str(turn) + " x" * 5000}
            for turn in range(20) for role in ("user", "assistant")
        ]
        answer_stock_question("EX", supplied, messages, "Why?", "test-key")
        payload = json.loads(request.call_args.args[0].data)
        data = json.loads(payload["input"])
        self.assertEqual(len(data["history"]), MAX_HISTORY_MESSAGES)
        self.assertTrue(data["history"][0]["content"].startswith("14"))
        self.assertTrue(all(
            len(item["content"]) <= (MAX_QUESTION_CHARS if item["role"] == "user" else MAX_ANSWER_CHARS)
            for item in data["history"]
        ))
        self.assertIsNone(data["context"]["info"]["marketCap"])
        self.assertIsNone(data["context"]["price_history"][0]["Close"])

    @patch("openai_transport.urlopen")
    def test_malformed_refused_incomplete_and_empty_responses_are_failures(self, request):
        invalid = [
            "{",
            "NaN",
            json.dumps([]),
            json.dumps({"status": "incomplete", "output": response()["output"]}),
            json.dumps({"status": "completed", "output": None}),
            json.dumps({"status": "completed", "output": []}),
            json.dumps({"status": "completed", "output": [{"type": "message", "content": None}]}),
            json.dumps({"status": "completed", "output": [None]}),
            json.dumps({"status": "completed", "output": [{"type": "message", "content": [None]}]}),
            json.dumps({"status": "completed", "output": [{
                "type": "message", "content": [{"type": "refusal", "refusal": "test-key"}],
            }]}),
            json.dumps({"status": "completed", "output": [{
                "type": "message", "status": "incomplete", "content": response()["output"][0]["content"],
            }]}),
            json.dumps(response("  ")),
            json.dumps(response("x" * (MAX_ANSWER_CHARS + 1))),
            " " * 256_001,
        ]
        for body in invalid:
            with self.subTest(body=body[:100]):
                request.return_value.__enter__.return_value = io.StringIO(body)
                with self.assertRaises(StockDataError) as raised:
                    answer_stock_question("EX", context(), [], "Why?", "test-key")
                self.assertNotIn("test-key", str(raised.exception))
        self.assertEqual(request.call_count, len(invalid))

    @patch("openai_transport.urlopen")
    def test_http_and_network_failures_are_sanitized_with_no_automatic_retry(self, request):
        errors = [
            HTTPError("https://example.com/test-key", 401, "test-key", {}, io.BytesIO(b"test-key")),
            HTTPError("https://example.com/test-key", 429, "test-key", {}, io.BytesIO(b"test-key")),
            HTTPError("https://example.com/test-key", 500, "test-key", {}, io.BytesIO(b"test-key")),
            URLError("test-key"),
            TimeoutError("test-key"),
            OSError("test-key"),
        ]
        for error in errors:
            request.side_effect = error
            with self.subTest(error=error), self.assertRaises(StockDataError) as raised:
                answer_stock_question("EX", context(), [], "Why?", "test-key")
            self.assertNotIn("test-key", str(raised.exception))
            self.assertTrue(raised.exception.__suppress_context__)
            if isinstance(error, HTTPError) and error.code == 429:
                self.assertIn("quota", str(raised.exception))
        self.assertEqual(request.call_count, len(errors))

    @patch("openai_transport.urlopen")
    def test_answer_redacts_active_credentials_and_unsupplied_source_urls(self, request):
        request.return_value.__enter__.return_value = io.StringIO(json.dumps(response(
            "See https://example.com/news and https://invented.example/story test-key"
        )))
        answer = answer_stock_question("EX", context(), [], "Sources?", "test-key")
        self.assertIn("https://example.com/news", answer)
        self.assertNotIn("https://invented.example", answer)
        self.assertNotIn("test-key", answer)


if __name__ == "__main__":
    unittest.main()
