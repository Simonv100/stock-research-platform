import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from infrastructure_research import (
    INFRASTRUCTURE_RESEARCH_GAPS,
    infrastructure_listing_details,
)
from stock_data import StockDataError, analyze_infrastructure_income
from strategy_catalog import INFRASTRUCTURE_COMPANIES


class InfrastructureVenueTests(unittest.TestCase):
    def test_official_polish_romanian_and_african_venues_are_retained(self):
        for symbol, code in (
            ("PGE.WA", "WSE"), ("TEL.RO", "BVB"), ("TKG.JO", "JSE"),
            ("AAF.L", "LSE"), ("CIG", "NYSE / NASDAQ"), ("TVE1T.TL", "N.TALLINN"),
        ):
            with self.subTest(symbol=symbol):
                details = infrastructure_listing_details(symbol)
                self.assertEqual(details["AccessStatus"], "Supported venue")
                self.assertEqual(details["IBKRExchange"], code)

    def test_data_provider_coverage_is_not_mistaken_for_exchange_access(self):
        for symbol in ("AOT.BK", "QGTS.QA", "AGUAS-A.SN", "AIA.AT", "TAVHL.IS"):
            self.assertEqual(
                infrastructure_listing_details(symbol)["AccessStatus"], "Unverified venue"
            )
        self.assertEqual(
            infrastructure_listing_details("POWERGRID.NS")["AccessStatus"],
            "Restricted venue",
        )
        self.assertEqual(
            infrastructure_listing_details("UNKNOWN.XX")["AccessStatus"], "Unverified venue"
        )

    def test_all_catalog_venues_are_reviewed_and_access_gaps_remain_documented(self):
        for company in INFRASTRUCTURE_COMPANIES:
            self.assertNotEqual(
                infrastructure_listing_details(company["Symbol"])["ListingMarket"],
                "Unreviewed",
            )
        symbols = {row["Local symbol"] for row in INFRASTRUCTURE_RESEARCH_GAPS}
        self.assertTrue({"KZTO", "KEGC", "KZTK", "SCOM", "KPLC", "SNTS"}.issubset(symbols))
        self.assertTrue(all(row["Reason"] and row["Source"] for row in INFRASTRUCTURE_RESEARCH_GAPS))


class InfrastructureAnalysisTests(unittest.TestCase):
    def test_rejection_reasons_match_each_financial_filter(self):
        history = pd.DataFrame({"Close": [100.0, 99.0]})
        result = analyze_infrastructure_income(
            {"dividendYield": 4.0, "payoutRatio": 0.81}, history
        )
        self.assertFalse(result["Qualifies"])
        self.assertEqual(
            result["ExclusionReason"],
            "Forward yield must exceed 4%; Payout / coverage exceeds 80%; "
            "Price is less than 5% below five-year high",
        )

    def test_missing_metrics_are_not_reported_as_failed_numeric_thresholds(self):
        result = analyze_infrastructure_income(
            {}, pd.DataFrame({"Close": [100.0, 80.0]})
        )
        self.assertFalse(result["Qualifies"])
        self.assertEqual(
            result["ExclusionReason"],
            "Forward yield unavailable; Payout / coverage unavailable",
        )

    def test_qualified_cash_flow_fallback_has_no_rejection(self):
        result = analyze_infrastructure_income(
            {
                "dividendYield": 5.0,
                "dividendRate": 2.0,
                "sharesOutstanding": 100,
                "freeCashflow": 250,
            },
            pd.DataFrame({"Close": [100.0, 90.0]}),
        )
        self.assertTrue(result["Qualifies"])
        self.assertEqual(result["CoverageBasis"], "Dividend / free cash flow")
        self.assertEqual(result["ExclusionReason"], "")


class InfrastructureIncomeUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.companies = [
            {
                "Symbol": symbol,
                "Name": name,
                "Region": region,
                "Type": "Electricity transmission",
                "MarketStructure": "Regulated transmission network",
                "Source": "https://example.com/network",
            }
            for symbol, name, region in [
                ("CIG", "Cemig", "Latin America"),
                ("TEST.JO", "African network", "Middle East and Africa"),
                ("TEST.WA", "Polish network", "Emerging Europe"),
            ]
        ]
        self.stack.enter_context(
            patch.object(app, "INFRASTRUCTURE_COMPANIES", self.companies)
        )
        self.info = self.stack.enter_context(
            patch.object(app, "cached_info", side_effect=self.company_info)
        )
        self.history = self.stack.enter_context(
            patch.object(
                app, "cached_history",
                return_value=pd.DataFrame(
                    {"Close": [100.0, 80.0], "Volume": [1000, 1200]},
                    index=pd.to_datetime(["2026-09-10", "2026-09-11"]),
                ),
            )
        )

    @staticmethod
    def company_info(symbol):
        return {
            "dividendYield": {"CIG": 8.0, "TEST.JO": None, "TEST.WA": 2.0}[symbol],
            "payoutRatio": 0.70,
        }

    def ui(self):
        return AppTest.from_string(
            "from app import render_infrastructure_income_strategy\n"
            "render_infrastructure_income_strategy()"
        ).run()

    @staticmethod
    def select(ui, label):
        return next(widget for widget in ui.selectbox if widget.label == label)

    def test_global_screen_and_failed_rows_preserve_catalog_order(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "1 / 3")
        self.assertEqual(ui.metric[1].value, "3 / 3")
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["CIG"])
        ui.checkbox[0].check().run()
        self.assertFalse(ui.exception)
        rows = ui.dataframe[0].value
        self.assertEqual(rows["Symbol"].tolist(), ["CIG", "TEST.JO", "TEST.WA"])
        self.assertEqual(
            rows.loc[rows["Symbol"] == "TEST.JO", "Why excluded"].iloc[0],
            "Forward yield unavailable",
        )

    def test_africa_region_only_loads_its_own_candidates(self):
        ui = self.ui()
        self.info.reset_mock()
        self.history.reset_mock()
        self.select(ui, "Infrastructure region").select("Middle East and Africa").run()
        self.assertFalse(ui.exception)
        self.info.assert_called_once_with("TEST.JO")
        self.history.assert_called_once_with("TEST.JO", "5y", "1d")
        self.assertEqual(ui.metric[0].value, "0 / 1")
        self.assertTrue(any("No companies currently meet" in item.value for item in ui.info))
        ui.checkbox[0].check().run()
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["TEST.JO"])

    def test_missing_market_data_stays_in_denominator_and_is_explained(self):
        def company_info(symbol):
            if symbol == "TEST.JO":
                raise StockDataError("Provider did not return African prices")
            return self.company_info(symbol)

        self.info.side_effect = company_info
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "1 / 3")
        self.assertEqual(ui.metric[1].value, "2 / 3")
        self.assertTrue(any(
            "TEST.JO: Provider did not return African prices" in item.value
            for item in ui.markdown
        ))

    def test_all_unavailable_still_shows_scope_and_errors(self):
        self.info.side_effect = StockDataError("Provider unavailable")
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "0 / 3")
        self.assertEqual(ui.metric[1].value, "0 / 3")
        self.assertTrue(any("Provider unavailable" in item.value for item in ui.warning))

    def test_empty_catalog_has_explanation_instead_of_worker_error(self):
        with patch.object(self.app, "INFRASTRUCTURE_COMPANIES", []):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No infrastructure companies" in item.value for item in ui.info))
        self.info.assert_not_called()
        self.history.assert_not_called()

    def test_research_coverage_includes_failures_without_fetching_market_data(self):
        ui = self.ui()
        self.info.reset_mock()
        self.history.reset_mock()
        self.select(ui, "Infrastructure view").select("Research coverage").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "3")
        self.assertEqual(
            ui.dataframe[0].value["Symbol"].tolist(), ["CIG", "TEST.JO", "TEST.WA"]
        )
        self.info.assert_not_called()
        self.history.assert_not_called()

    def test_unverified_venues_are_visible_in_research_but_not_fetched_for_income(self):
        self.companies.append({
            **self.companies[0], "Symbol": "AGUAS-A.SN", "Name": "Aguas Andinas"
        })
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "1 / 3")
        self.assertNotIn("AGUAS-A.SN", [call.args[0] for call in self.info.call_args_list])
        self.assertTrue(any("AGUAS-A.SN" in item.value for item in ui.warning))
        self.select(ui, "Infrastructure view").select("Research coverage").run()
        self.assertEqual(ui.metric[0].value, "4")
        self.assertIn("AGUAS-A.SN", ui.dataframe[0].value["Symbol"].tolist())

    def test_shared_loader_preserves_dated_values_and_structured_errors(self):
        from app import load_infrastructure_income

        companies = [
            {**company, **infrastructure_listing_details(company["Symbol"])}
            for company in self.companies
        ]
        self.info.side_effect = lambda symbol: (
            {"dividendYield": 8.0, "payoutRatio": 0.7, "currency": "USD"}
            if symbol == "CIG" else self.company_info(symbol)
        )
        rows, errors = load_infrastructure_income(companies)
        self.assertFalse(errors)
        self.assertEqual([row["Symbol"] for row in rows], ["CIG", "TEST.JO", "TEST.WA"])
        self.assertEqual(rows[0]["InfrastructurePriceDate"], "2026-09-11")
        self.assertEqual(rows[0]["InfrastructureCurrency"], "USD")
        self.assertTrue(rows[0]["Qualifies"])
        self.info.side_effect = StockDataError("Provider offline")
        rows, errors = load_infrastructure_income(companies)
        self.assertFalse(rows)
        self.assertEqual(errors[0], {"Symbol": "CIG", "Error": "Provider offline"})
        self.assertEqual(len(errors), 3)

    def test_shared_loader_skips_unverified_venues_and_propagates_unexpected_errors(self):
        from app import load_infrastructure_income

        company = {**self.companies[0], "AccessStatus": "Unverified venue"}
        self.assertEqual(load_infrastructure_income([company]), ([], []))
        self.info.assert_not_called()
        self.info.side_effect = RuntimeError("Unexpected implementation error")
        with self.assertRaisesRegex(RuntimeError, "Unexpected implementation error"):
            load_infrastructure_income([{**company, "AccessStatus": "Supported venue"}])


if __name__ == "__main__":
    unittest.main()
