import unittest
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError, analyze_infrastructure_income


class IncomeStrategyUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.companies = [
            {"Symbol": symbol, "Name": name, "Region": region, "Type": "Network",
             "MarketStructure": "Regulated network evidence", "Source": "https://example.com/network"}
            for symbol, name, region in (
                ("CIG", "Cemig", "Latin America"), ("INF.L", "Infra network", "Europe"),
                ("BAD.L", "Low yield network", "Europe"), ("MISS.L", "Missing data", "Europe"),
                ("UNKNOWN.X", "Unverified network", "Other"),
            )
        ]
        self.catalog = pd.DataFrame([
            {"Symbol": symbol, "Ticker": symbol.replace("-", "."), "Name": name, "Country": country,
             "Overview": f"{name} business overview.", "ResearchNotes": "Dated ADR evidence",
             "ResearchSource": "https://example.com/adr"}
            for symbol, name, country in (
                ("CIG", "Cemig ADR", "Brazil"), ("NVO", "Novo", "Denmark"),
                ("PBR", "Petrobras common", "Brazil"), ("PBR-A", "Petrobras preferred", "Brazil"),
                ("ADRERR", "Unavailable ADR", "Brazil"),
            )
        ])
        self.history_data = pd.DataFrame(
            {"Close": [100.0, 80.0], "Volume": [100, 200]},
            index=pd.to_datetime(["2026-09-10", "2026-09-11"]),
        )
        self.stack.enter_context(patch.object(app, "INFRASTRUCTURE_COMPANIES", self.companies))
        self.stack.enter_context(patch.object(app, "infrastructure_listing_details", side_effect=lambda symbol: {
            "ListingMarket": "Test exchange", "AccessStatus": "Unverified venue" if symbol == "UNKNOWN.X" else "Supported venue",
            "AccessNote": "Confirm account eligibility", "AccessSource": "https://example.com/venue",
            "IBKRExchange": "TEST",
        }))
        self.stack.enter_context(patch.object(app, "adr_catalog", return_value=self.catalog))
        self.infrastructure = self.stack.enter_context(patch.object(
            app, "load_infrastructure_income", side_effect=self.load_infrastructure,
        ))
        self.adr = self.stack.enter_context(patch.object(app, "cached_adr_scan", side_effect=self.load_adrs))
        self.history = self.stack.enter_context(patch.object(app, "cached_history", return_value=self.history_data))
        self.stack.enter_context(patch.object(app, "cached_info", return_value={"currency": "USD"}))
        self.stack.enter_context(patch.object(app, "price_chart", return_value=go.Figure()))
        self.bookmark = self.stack.enter_context(patch.object(app, "render_bookmark_button"))
        self.chat = self.stack.enter_context(patch.object(app, "render_stock_assistant"))
        self.download = self.stack.enter_context(patch.object(app.st, "download_button", wraps=app.st.download_button))

    def load_infrastructure(self, companies):
        rows, errors = [], []
        for company in companies:
            symbol = company["Symbol"]
            if symbol == "UNKNOWN.X":
                continue
            if symbol == "MISS.L":
                errors.append({"Symbol": symbol, "Error": "Infrastructure provider unavailable"})
                continue
            rows.append({
                **company, **analyze_infrastructure_income(
                    {"dividendYield": 6.0 if symbol == "INF.L" else 2.0, "payoutRatio": 0.7},
                    self.history_data,
                ),
                "InfrastructurePriceDate": "2026-09-11", "InfrastructureCurrency": "GBP",
            })
        return rows, errors

    @staticmethod
    def load_adrs(symbols, as_of):
        rows, errors = [], []
        for symbol in symbols:
            if symbol == "ADRERR":
                errors.append({"Symbol": symbol, "Error": "ADR dividend history unavailable"})
                continue
            dividend_yield = {"CIG": 5.0, "NVO": 0.0, "PBR": 8.0, "PBR-A": 9.0}[symbol]
            rows.append({
                "Symbol": symbol, "Price": 10.0, "TTMCash": dividend_yield / 10,
                "YieldPercent": dividend_yield, "PriceDate": "2026-09-11",
                "WindowStart": "2025-09-11", "DividendCount": int(dividend_yield > 0),
                "LastExDate": "2026-06-01" if dividend_yield else None,
                "FetchedAt": "2026-09-12T18:00:00+00:00",
                "LiveSource": f"https://finance.yahoo.com/quote/{symbol}/history/",
            })
        return rows, errors

    def ui(self, **state):
        ui = AppTest.from_string("from app import render_income_strategy\nrender_income_strategy()")
        for key, value in state.items():
            ui.session_state[key] = value
        return ui.run()

    @staticmethod
    def table(ui):
        return next(frame.value for frame in ui.dataframe if "Included via" in frame.value.columns)

    def test_one_table_deduplicates_overlap_without_confusing_yield_or_qualification(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Income strategies")
        table = self.table(ui)
        self.assertEqual(set(table["Symbol"]), {"CIG", "INF.L", "NVO", "PBR", "PBR-A"})
        self.assertTrue(table["Symbol"].is_unique)
        cig = table.set_index("Symbol").loc["CIG"]
        self.assertEqual(cig["Infrastructure status"], "Fail")
        self.assertEqual(cig["Included via"], "ADR")
        self.assertEqual(cig["Infrastructure forward yield (%)"], 2.0)
        self.assertEqual(cig["ADR TTM yield (%)"], 5.0)
        self.assertEqual(table.set_index("Symbol").loc["NVO", "ADR TTM yield (%)"], 0.0)
        self.assertFalse(ui.button(key="refresh_income").disabled)
        self.assertEqual(ui.metric[0].value, "1 / 5")
        self.assertEqual(ui.metric[1].value, "4 / 5")
        self.assertEqual(ui.metric[2].value, "5")
        exported = pd.read_csv(StringIO(self.download.call_args.kwargs["data"].decode()))
        self.assertEqual(exported["Symbol"].tolist(), table["Symbol"].tolist())
        self.assertIn("Infrastructure forward yield (%)", exported)
        self.assertIn("ADR TTM yield (%)", exported)

    def test_separate_strategy_filters_do_not_cross_apply(self):
        ui = self.ui()
        ui.number_input(key="income_minimum_adr_yield").set_value(7.0).run()
        self.assertFalse(ui.exception)
        self.assertEqual(set(self.table(ui)["Symbol"]), {"INF.L", "PBR", "PBR-A"})
        ui.selectbox(key="income_adr_country").select("Denmark").run()
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["INF.L"])
        ui.selectbox(key="income_strategy").select("Infrastructure").run()
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["INF.L"])
        self.assertTrue(ui.selectbox(key="income_adr_country").disabled)
        ui.checkbox(key="income_show_excluded").check().run()
        self.assertEqual(set(self.table(ui)["Symbol"]), {company["Symbol"] for company in self.companies})
        ui.selectbox(key="income_infrastructure_region").select("Latin America").run()
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["CIG"])

    def test_adr_only_sort_limits_chart_class_and_handoff(self):
        ui = self.ui(income_strategy="ADRs", income_sort="ADR TTM yield")
        self.infrastructure.assert_not_called()
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["PBR-A", "PBR", "CIG", "NVO"])
        self.bookmark.assert_called_with("PBR-A", "Petrobras preferred")
        self.history.assert_called_with("PBR-A", "5y", "1d")
        self.assertEqual(self.chat.call_args.args[0], "PBR-A")
        evidence = self.chat.call_args.args[-1]
        self.assertEqual(evidence["ADRYieldPercent"], 9.0)
        self.assertEqual(evidence["ADRStatus"], "Available")
        ui.button(key="income_next").click().run()
        self.assertEqual(ui.selectbox(key="income_symbol").value, "PBR")
        queue = self.table(ui)["Symbol"].tolist()
        ui.button(key="income_open_research").click().run()
        self.assertEqual(ui.session_state["stock_research_queue"], queue)
        self.assertEqual(ui.session_state["stock_research_queue_label"], "Income strategy candidates")
        self.assertEqual(ui.session_state["stock_query"], "PBR")

    def test_unavailable_audit_and_adr_retry_preserve_successful_cache(self):
        ui = self.ui()
        audit = next(frame.value for frame in ui.dataframe if "InfrastructureReason" in frame.value.columns
                     and "IncomeIncludedVia" not in frame.value.columns)
        self.assertIn("ADRERR", audit["Symbol"].tolist())
        self.assertIn("MISS.L", audit["Symbol"].tolist())
        self.assertIn("UNKNOWN.X", audit["Symbol"].tolist())
        with patch.object(self.app.cached_adr_dividend, "clear") as per_symbol:
            ui.button(key="income_retry_adr").click().run()
            self.adr.clear.assert_called_once()
            per_symbol.assert_not_called()
        self.assertNotIn("ADRERR", self.table(ui)["Symbol"].tolist())

    def test_no_data_on_one_side_does_not_hide_the_other(self):
        with patch.object(self.app, "adr_catalog", side_effect=StockDataError("Missing catalog")):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Missing catalog" in item.value for item in ui.error))
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["INF.L"])

    def test_coverage_view_is_research_only_and_keeps_unverified_venues(self):
        ui = self.ui(income_view="Infrastructure research coverage")
        self.assertFalse(ui.exception)
        self.infrastructure.assert_not_called()
        self.adr.assert_not_called()
        self.history.assert_not_called()
        self.assertIn("UNKNOWN.X", ui.dataframe[0].value["Symbol"].tolist())
        self.assertFalse(ui.button(key="refresh_income").disabled)

    def test_empty_filter_and_chart_failures_keep_controls(self):
        self.history.side_effect = StockDataError("Prices unavailable")
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Price chart unavailable" in item.value for item in ui.warning))
        self.assertEqual(len(self.table(ui)), 5)
        self.chat.assert_called()
        ui.selectbox(key="income_strategy").select("ADRs").run()
        ui.number_input(key="income_minimum_adr_yield").set_value(100.0).run()
        self.assertFalse(ui.exception)
        self.assertFalse(any(widget.key == "income_symbol" for widget in ui.selectbox))
        self.assertTrue(any("No income candidates match" in item.value for item in ui.info))
        self.assertFalse(ui.button(key="refresh_income").disabled)

    def test_navigation_replaces_old_routes_and_migrates_open_sessions(self):
        for old, expected in (("ADR dividend yield", "ADRs"), ("Infrastructure income", "Infrastructure"),
                              ("Income strategies", "All income candidates")):
            with self.subTest(route=old):
                ui = AppTest.from_string("from app import main\nmain()")
                ui.session_state["research_area"] = old
                ui.run()
                self.assertFalse(ui.exception)
                options = ui.radio(key="research_area").options
                self.assertIn("Income strategies", options)
                self.assertNotIn("ADR dividend yield", options)
                self.assertNotIn("Infrastructure income", options)
                self.assertEqual(ui.radio(key="research_area").value, "Income strategies")
                self.assertEqual(ui.selectbox(key="income_strategy").value, expected)

    def test_adr_migration_keeps_filters_result_limit_and_selection(self):
        ui = AppTest.from_string("from app import main\nmain()")
        for key, value in {
            "research_area": "ADR dividend yield", "adr_country": "Brazil",
            "adr_minimum_yield": 7.0, "adr_result_limit": 25,
            "adr_symbol": "PBR", "adr_show_chart": False,
        }.items():
            ui.session_state[key] = value
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="income_adr_country").value, "Brazil")
        self.assertEqual(ui.number_input(key="income_minimum_adr_yield").value, 7.0)
        self.assertEqual(ui.selectbox(key="income_limit").value, 25)
        self.assertEqual(ui.selectbox(key="income_symbol").value, "PBR")
        self.assertFalse(ui.checkbox(key="income_show_chart").value)
        self.history.assert_not_called()

    def test_entire_adr_fetch_failure_still_shows_infrastructure(self):
        self.adr.side_effect = StockDataError("ADR data is offline")
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(self.table(ui)["Symbol"].tolist(), ["INF.L"])
        self.assertEqual(ui.metric[1].value, "0 / 5")
        audit = next(frame.value for frame in ui.dataframe if "ADRReason" in frame.value.columns)
        self.assertTrue(audit["ADRReason"].str.contains("ADR data is offline", na=False).any())

    def test_empty_catalogs_leave_refresh_and_explanation(self):
        with patch.object(self.app, "INFRASTRUCTURE_COMPANIES", []), patch.object(
            self.app, "adr_catalog", return_value=pd.DataFrame(),
        ):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[2].value, "0")
        self.assertFalse(ui.button(key="refresh_income").disabled)
        self.assertTrue(any("No income candidates match" in item.value for item in ui.info))
        self.infrastructure.assert_not_called()
        self.adr.assert_not_called()

    def test_chat_context_keeps_both_yield_bases_and_statuses(self):
        from stock_chat import build_stock_context

        context = build_stock_context("CIG", "Cemig", {}, pd.DataFrame(), {"research_view": {
            "IncomeStrategies": "Infrastructure + ADR", "IncomeIncludedVia": "ADR",
            "InfrastructureStatus": "Fail", "InfrastructureYieldPercent": 2.0,
            "InfrastructureReason": "Forward yield must exceed 4%", "ADRStatus": "Available",
            "ADRYieldPercent": 5.0, "PriceDate": "2026-09-11",
            "DividendCoverageRatio": 0.7, "CoverageBasis": "Earnings payout ratio",
        }})
        evidence = context["sections"]["research_view"]
        self.assertEqual(evidence["InfrastructureYieldPercent"], 2.0)
        self.assertEqual(evidence["ADRYieldPercent"], 5.0)
        self.assertEqual(evidence["InfrastructureStatus"], "Fail")
        self.assertEqual(evidence["DividendCoverageRatio"], 0.7)


if __name__ == "__main__":
    unittest.main()
