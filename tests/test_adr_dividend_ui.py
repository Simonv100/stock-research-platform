import unittest
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError


class ADRDividendUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.catalog = app.adr_catalog()
        self.rows = [
            {
                "Symbol": symbol, "Price": 10.0, "TTMCash": index / 100,
                "YieldPercent": index / 10, "PriceDate": "2026-09-11",
                "WindowStart": "2025-09-11", "DividendCount": int(index > 0),
                "LastExDate": "2026-06-01" if index else None,
                "FetchedAt": "2026-09-12T18:00:00+00:00",
                "LiveSource": f"https://finance.yahoo.com/quote/{symbol}/history/",
            }
            for index, symbol in enumerate(self.catalog["Symbol"])
        ]
        self.scan = self.stack.enter_context(patch.object(
            app, "cached_adr_scan", return_value=(self.rows, []),
        ))
        self.bookmark = self.stack.enter_context(patch.object(app, "render_bookmark_button"))
        self.history = self.stack.enter_context(patch.object(
            app, "cached_history", return_value=pd.DataFrame({"Close": [10, 11]}),
        ))
        self.stack.enter_context(patch.object(app, "price_chart", return_value=go.Figure()))
        self.download = self.stack.enter_context(patch.object(
            app.st, "download_button", wraps=app.st.download_button,
        ))

    def ui(self):
        return AppTest.from_string(
            "from app import render_adr_dividend_strategy\nrender_adr_dividend_strategy()"
        ).run()

    @staticmethod
    def table(ui):
        return next(frame.value for frame in ui.dataframe if "Rank" in frame.value.columns)

    def test_top_50_numeric_ranking_overviews_dates_and_export(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "ADR dividend yield")
        self.assertEqual(ui.selectbox(key="adr_result_limit").value, 50)
        self.assertEqual(ui.metric[0].value, "100 / 100")
        table = self.table(ui)
        self.assertEqual(len(table), 50)
        self.assertEqual(table["Rank"].tolist(), list(range(1, 51)))
        self.assertTrue(table["TTM yield (%)"].is_monotonic_decreasing)
        self.assertEqual(table.iloc[0]["TTM yield (%)"], 9.9)
        self.assertTrue(table["Business overview"].str.len().gt(0).all())
        self.assertTrue(table["Price date"].eq("2026-09-11").all())
        self.assertTrue(any("not forecasts" in item.value for item in ui.warning))
        self.history.assert_not_called()
        self.assertEqual(len(self.scan.call_args.args[0]), 100)
        exported = pd.read_csv(StringIO(self.download.call_args.kwargs["data"].decode()))
        self.assertEqual(exported["Ticker"].tolist(), table["Ticker"].tolist())
        self.assertEqual(exported["TTM yield (%)"].tolist(), table["TTM yield (%)"].tolist())
        self.assertTrue(exported["Live dividend history"].str.startswith("https://").all())

    def test_filtering_all_100_zero_yields_and_empty_state(self):
        ui = self.ui()
        ui.selectbox(key="adr_result_limit").select(100).run()
        self.assertEqual(len(self.table(ui)), 100)
        self.assertEqual(self.table(ui).iloc[-1]["TTM yield (%)"], 0.0)
        ui.selectbox(key="adr_country").select("Brazil").run()
        self.assertFalse(ui.exception)
        self.assertTrue(self.table(ui)["Country"].eq("Brazil").all())
        ui.number_input(key="adr_minimum_yield").set_value(100.0).run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No ADRs match" in item.value for item in ui.info))
        self.assertFalse(any(widget.key == "adr_symbol" for widget in ui.selectbox))

    def test_ties_use_ticker_order_and_filter_repairs_selected_candidate(self):
        for row in self.rows:
            row["YieldPercent"] = 5.0
        ui = self.ui()
        self.assertEqual(
            self.table(ui)["Ticker"].tolist(), sorted(self.catalog["Ticker"])[:50],
        )
        ui.selectbox(key="adr_country").select("Denmark").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="adr_symbol").value, "NVO")
        self.assertTrue(ui.button(key="adr_next").disabled)

    def test_share_class_navigation_bookmarks_and_research_queue(self):
        ui = self.ui()
        ui.selectbox(key="adr_result_limit").select(100).run()
        ui.selectbox(key="adr_symbol").select("PBR-A").run()
        self.assertFalse(ui.exception)
        self.bookmark.assert_called_with("PBR-A", "Petrobras preferred-share ADR")
        self.assertIn("PBR.A", ui.subheader[0].value)
        ui.checkbox(key="adr_show_chart").check().run()
        self.history.assert_called_with("PBR-A", "5y", "1d")
        expected_queue = self.table(ui)["Yahoo symbol"].tolist()
        ui.button(key="adr_open_research").click().run()
        self.assertEqual(ui.session_state["research_area"], "Individual stocks")
        self.assertEqual(ui.session_state["stock_query"], "PBR-A")
        self.assertEqual(ui.session_state["stock_research_queue"], expected_queue)
        self.assertEqual(
            ui.session_state["stock_research_queue_label"], "ADR dividend yield candidates",
        )
        ui.button(key="adr_next").click().run()
        self.assertNotEqual(ui.selectbox(key="adr_symbol").value, "PBR-A")

    def test_failures_are_unavailable_not_zero_and_retry_preserves_success_cache(self):
        failed_symbol = self.rows[0]["Symbol"]
        self.scan.return_value = (
            self.rows[1:], [{"Symbol": failed_symbol, "Error": "Dividend history unavailable"}],
        )
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "99 / 100")
        self.assertTrue(any("may omit higher yields" in item.value for item in ui.warning))
        errors = next(frame.value for frame in ui.dataframe if "Error" in frame.value.columns)
        self.assertEqual(errors["Symbol"].tolist(), [failed_symbol])
        with patch.object(self.app.cached_adr_dividend, "clear") as clear_successes:
            ui.button(key="adr_retry").click().run()
            self.scan.clear.assert_called_once()
            clear_successes.assert_not_called()
        self.scan.return_value = (
            [], [{"Symbol": row["Symbol"], "Error": "Provider unavailable"} for row in self.rows],
        )
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "0 / 100")
        self.assertTrue(any("No ADRs have complete market data" in item.value for item in ui.info))
        self.assertFalse(any("Rank" in frame.value.columns for frame in ui.dataframe))

    def test_chart_failure_keeps_results_and_dated_research_visible(self):
        self.history.side_effect = StockDataError("Provider unavailable")
        ui = self.ui()
        ui.checkbox(key="adr_show_chart").check().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(self.table(ui)), 50)
        self.assertTrue(any("Price chart unavailable" in item.value for item in ui.warning))
        self.assertTrue(any("Research note (2026-09-11)" in item.value for item in ui.caption))

    def test_main_navigation_migrates_adr_to_combined_income_strategy(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "ADR dividend yield"
        with patch.object(self.app, "render_income_strategy") as combined:
            ui.run()
        self.assertFalse(ui.exception)
        self.assertNotIn("ADR dividend yield", ui.radio(key="research_area").options)
        self.assertEqual(ui.radio(key="research_area").value, "Income strategies")
        self.assertEqual(ui.session_state["income_strategy"], "ADRs")
        combined.assert_called_once()

    def test_catalog_failure_is_visible(self):
        with patch.object(self.app, "adr_catalog", side_effect=StockDataError("Catalog missing")):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.error[0].value, "Catalog missing")
        self.scan.assert_not_called()


class ADRScanCacheTests(unittest.TestCase):
    def test_batch_failure_is_explicit_and_unexpected_errors_propagate(self):
        import app

        app.cached_adr_scan.clear()
        self.addCleanup(app.cached_adr_scan.clear)

        def load(symbol, as_of):
            if symbol == "FAIL":
                raise StockDataError("Missing dividends")
            return {"YieldPercent": 0.0}

        with patch.object(app, "cached_adr_dividend", side_effect=load) as fetch:
            rows, errors = app.cached_adr_scan(("GOOD", "FAIL"), "2026-09-12")
            self.assertEqual(rows, [{"Symbol": "GOOD", "YieldPercent": 0.0}])
            self.assertEqual(errors, [{"Symbol": "FAIL", "Error": "Missing dividends"}])
            app.cached_adr_scan(("GOOD", "FAIL"), "2026-09-12")
            self.assertEqual(fetch.call_count, 2)
        app.cached_adr_scan.clear()
        with patch.object(app, "cached_adr_dividend", side_effect=RuntimeError("Unexpected bug")):
            with self.assertRaisesRegex(RuntimeError, "Unexpected bug"):
                app.cached_adr_scan(("GOOD",), "2026-09-12")


if __name__ == "__main__":
    unittest.main()
