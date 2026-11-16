import io
import json
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import patch

import pandas as pd

from news_sentiment import (
    NEWS_INSTRUCTIONS,
    analyze_company_news,
    get_company_news,
    prepare_news_articles,
    validate_news_analysis,
)
from stock_data import StockDataError


def article():
    return {
        "id": 1, "date": "2026-09-06T12:00:00+00:00",
        "title": "Example raises revenue outlook despite shares falling",
        "excerpt": "Example raised its revenue outlook following a new customer contract.",
        "provider": "Example News", "url": "https://example.com/news",
    }


def assessment():
    return {
        "overall": "Positive",
        "summary": "The higher revenue outlook suggests stronger demand [1].",
        "source_ids": [1], "limitations": "Only a headline and excerpt were available.",
        "articles": [{
            "id": 1, "impact": "Positive", "reason": "The company raised its revenue outlook.",
            "confidence": "Medium",
        }],
    }


def api_response(result=None):
    return {
        "status": "completed",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps(result or assessment())}],
        }],
    }


class NewsSentimentTests(unittest.TestCase):
    def test_preparation_filters_dates_deduplicates_and_cleans_text(self):
        rows = [
            ("2026-09-06", "<b>New contract</b> &amp; growth", "https://example.com/1"),
            ("2026-09-05", "NEW CONTRACT & GROWTH!", "https://example.com/2"),
            ("2026-09-04", "Another title for the same story", "https://example.com/1?tracking=2"),
            ("2026-07-01", "Old news", "https://example.com/old"),
            ("2026-09-08", "Future news", "https://example.com/future"),
            ("invalid", "Undated news", "https://example.com/undated"),
            ("2026-09-03", "Bad link", "javascript:alert(1)"),
            ("2026-09-03", "Malformed link", "https://[invalid"),
            ("2026-09-02", "Headline only", "https://example.com/headline"),
        ]
        frame = pd.DataFrame(rows, columns=["Date", "Title", "URL"])
        frame["Summary"] = ""
        frame["Provider"] = "Publisher"
        result = prepare_news_articles(frame, pd.Timestamp("2026-09-06T18:00:00Z"))
        self.assertEqual([row["id"] for row in result], [1, 2])
        self.assertEqual(result[0]["title"], "New contract & growth")
        self.assertEqual(result[1]["excerpt"], "")

    def test_preparation_bounds_article_count_and_excerpt_size(self):
        frame = pd.DataFrame([{
            "Date": "2026-09-05", "Title": f"Headline {i}",
            "Summary": "x" * 5000, "Provider": "Publisher",
            "URL": f"https://example.com/{i}",
        } for i in range(30)])
        result = prepare_news_articles(frame, pd.Timestamp("2026-09-06"))
        self.assertEqual(len(result), 20)
        self.assertTrue(all(len(row["excerpt"]) == 2000 for row in result))

    def test_empty_news_has_no_assessment(self):
        self.assertEqual(prepare_news_articles(pd.DataFrame()), [])
        with patch("openai_transport.urlopen") as request:
            with self.assertRaisesRegex(StockDataError, "No recent"):
                analyze_company_news("EX", "Example", [], "test-key")
            request.assert_not_called()

    @patch("news_sentiment.yf.Ticker")
    def test_feed_includes_news_and_press_releases(self, ticker):
        ticker.return_value.get_news.return_value = []
        result = get_company_news("EX")
        ticker.return_value.get_news.assert_called_once_with(count=100, tab="all")
        self.assertEqual(result["articles"], [])
        self.assertIn("fetched_at", result)

    @patch("news_sentiment.yf.Ticker")
    def test_news_failure_is_not_disguised_as_no_news(self, ticker):
        ticker.return_value.get_news.side_effect = ValueError("Bad upstream JSON")
        with self.assertRaisesRegex(StockDataError, "could not be loaded"):
            get_company_news("EX")

    @patch("openai_transport.urlopen")
    def test_request_uses_structured_output_public_text_and_no_storage(self, urlopen):
        urlopen.return_value.__enter__.return_value = io.StringIO(json.dumps(api_response()))
        result = analyze_company_news("EX", "Example", [article()], "test-key")
        self.assertEqual(result["overall"], "Positive")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        payload = json.loads(request.data)
        self.assertFalse(payload["store"])
        self.assertTrue(payload["text"]["format"]["strict"])
        self.assertNotIn("test-key", request.data.decode())
        public_input = json.loads(payload["input"])
        self.assertEqual(set(public_input), {"symbol", "company_name", "articles"})
        self.assertNotIn("url", public_input["articles"][0])
        self.assertIn("not article counts", payload["instructions"])
        self.assertIn("Reaction-only stories are Insufficient information", NEWS_INSTRUCTIONS)
        self.assertIn("negation", NEWS_INSTRUCTIONS)
        self.assertIn("untrusted data", NEWS_INSTRUCTIONS)

    def test_missing_key_never_calls_api(self):
        with patch("openai_transport.urlopen") as request:
            with self.assertRaisesRegex(StockDataError, "API key"):
                analyze_company_news("EX", "Example", [article()], "")
            request.assert_not_called()

    @patch("openai_transport.urlopen")
    def test_api_failures_surface_without_credentials_or_response_body(self, urlopen):
        for error in (
            HTTPError("https://api.openai.com", 401, "test-key", {}, None),
            HTTPError("https://api.openai.com", 429, "test-key", {}, None),
            URLError("test-key"),
        ):
            with self.subTest(error=type(error).__name__):
                urlopen.side_effect = error
                with self.assertRaises(StockDataError) as raised:
                    analyze_company_news("EX", "Example", [article()], "test-key")
                self.assertNotIn("test-key", str(raised.exception))
        self.assertEqual(urlopen.call_count, 3)

    @patch("openai_transport.urlopen")
    def test_incomplete_refused_or_malformed_output_is_not_accepted(self, urlopen):
        for response in (
            {"status": "incomplete"},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal"}]}]},
            {"status": "completed", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": None}]},
            [],
        ):
            with self.subTest(response=response):
                urlopen.return_value.__enter__.return_value = io.StringIO(json.dumps(response))
                with self.assertRaises(StockDataError):
                    analyze_company_news("EX", "Example", [article()], "test-key")

    def test_validation_rejects_missing_duplicate_and_invented_article_ids(self):
        for ids in ([], [1, 1], [99]):
            result = assessment()
            result["articles"] = [{**result["articles"][0], "id": value} for value in ids]
            with self.subTest(ids=ids), self.assertRaises(StockDataError):
                validate_news_analysis(result, [1])

    def test_validation_rejects_unsupported_citations_and_direction(self):
        invalid = []
        result = assessment()
        result["source_ids"] = [99]
        invalid.append(result)
        result = assessment()
        result["summary"] = "An unsupported claim [99]."
        invalid.append(result)
        result = assessment()
        result["articles"][0]["impact"] = "Not relevant"
        invalid.append(result)
        result = assessment()
        result["source_ids"] = []
        result["summary"] = "Good news without evidence."
        invalid.append(result)
        for result in invalid:
            with self.subTest(result=result), self.assertRaises(StockDataError):
                validate_news_analysis(result, [1])

    def test_insufficient_evidence_is_distinct_from_neutral(self):
        result = assessment()
        result.update({
            "overall": "Insufficient information",
            "summary": "Only a share-price reaction was reported.",
            "source_ids": [],
        })
        result["articles"][0].update({
            "impact": "Insufficient information",
            "reason": "A price reaction does not establish business impact.",
        })
        self.assertEqual(validate_news_analysis(result, [1])["overall"], "Insufficient information")


class NewsSentimentUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        app.cached_company_news.clear()
        app.cached_news_assessment.clear()

    def tearDown(self):
        self.app.cached_company_news.clear()
        self.app.cached_news_assessment.clear()

    def make_ui(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_string(
            "import streamlit as st\n"
            "from app import render_company_news\n"
            "symbol = st.selectbox('Test company', ['EX', 'EX2'])\n"
            "render_company_news(symbol, 'Example company')\n"
        )

    @patch.dict("os.environ", {"OPENAI_API_KEY": "", "OPENAI_NEWS_MODEL": "gpt-4.1-mini"})
    def test_ui_requires_key_and_explicit_opt_in_then_reuses_cache(self):
        news = {"articles": [article()], "fetched_at": "2026-09-06T12:00:00Z"}
        with patch.object(self.app, "get_company_news", return_value=news) as fetch:
            with patch.object(self.app, "analyze_company_news", return_value=assessment()) as analyze:
                ui = self.make_ui().run()
                self.assertFalse(ui.exception)
                self.assertTrue(ui.button[0].disabled)
                ui.text_input[0].input("test-key").run()
                fetch.assert_not_called()
                ui.button[0].click().run()
                self.assertFalse(ui.exception)
                self.assertEqual(ui.metric[0].value, "Positive")
                self.assertEqual(ui.dataframe[0].value.loc[0, "Source"], article()["url"])
                ui.run()
                ui.button[0].click().run()
                fetch.assert_called_once()
                analyze.assert_called_once()
                ui.checkbox[0].check().run()
                ui.selectbox[0].select("EX2").run()
                self.assertEqual(analyze.call_count, 2)
                ui.selectbox[0].select("EX").run()
                self.assertEqual(analyze.call_count, 2)
                self.assertFalse(ui.exception)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_failures_do_not_retry_on_rerun_or_candidate_navigation(self):
        news = {"articles": [article()], "fetched_at": "2026-09-06T12:00:00Z"}
        with patch.object(self.app, "get_company_news", return_value=news):
            with patch.object(self.app, "analyze_company_news", side_effect=StockDataError("API quota reached")) as analyze:
                ui = self.make_ui().run()
                ui.checkbox[0].check().run()
                self.assertIn("API quota reached", ui.warning[0].value)
                ui.run()
                self.assertEqual(analyze.call_count, 1)
                ui.selectbox[0].select("EX2").run()
                ui.selectbox[0].select("EX").run()
                self.assertEqual(analyze.call_count, 2)
                ui.button[0].click().run()
                self.assertEqual(analyze.call_count, 3)
                self.assertFalse(ui.exception)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_no_news_is_not_neutral_and_never_calls_ai(self):
        with patch.object(self.app, "get_company_news", return_value={"articles": []}):
            with patch.object(self.app, "analyze_company_news") as analyze:
                ui = self.make_ui().run()
                ui.button[0].click().run()
                self.assertFalse(ui.exception)
                self.assertIn("not neutral or positive", ui.info[0].value)
                self.assertEqual(len(ui.metric), 0)
                analyze.assert_not_called()


if __name__ == "__main__":
    unittest.main()
