import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from stock_chat import build_stock_context


class RecoveryResearchUITests(unittest.TestCase):
    def test_evidence_is_on_demand_and_reused_across_research_views(self):
        import app

        with patch("management_evidence_ui.render_management_evidence"), patch.object(
            app, "load_recovery_signals", return_value={
                "ProfitabilityStatus": "Pass", "ProfitabilityReason": "Shrinking cash burn",
                "FinancialCurrency": "EUR", "OperatingMarginLatest": -0.1,
                "OperatingMarginPrior": -0.2, "FreeCashFlowLatest": -5, "FreeCashFlowPrior": -10,
                "FinancialPeriodEnd": "2025-12-31", "FinancialPriorPeriodEnd": "2024-12-31",
                "FinancialPeriodBasis": "Fiscal-year fallback",
            },
        ) as loader:
            ui = AppTest.from_string(
                "from app import render_recovery_research\n"
                "render_recovery_research('EX.PA', 'Example')"
            ).run()
            self.assertFalse(ui.exception)
            loader.assert_not_called()
            ui.button(key="load_recovery_EX.PA").click().run()
            self.assertFalse(ui.exception)
            loader.assert_called_once_with("EX.PA", ("small_cap", "sector", "profitability", "deleveraging", "shareholder_yield"))
            self.assertTrue(ui.session_state["recovery_loaded_EX.PA"])
            metrics = ui.dataframe[1].value
            self.assertIn("EUR -5", metrics["Latest value"].tolist())
            self.assertIn("-10.00%", metrics["Latest value"].tolist())

    def test_empty_evidence_is_not_fabricated_zero(self):
        ui = AppTest.from_string(
            "from recovery_ui import render_recovery_evidence\nrender_recovery_evidence({})"
        ).run()
        self.assertFalse(ui.exception)
        self.assertEqual(set(ui.dataframe[0].value["Status"]), {"Not loaded"})

    def test_chat_receives_public_recovery_fields_without_manual_notes(self):
        import app

        evidence = {
            "Signal": "Early right side", "MarketCapUSD": 1e9,
            "SmallCapStatus": "Pass", "SectorBenchmark": "IXN",
            "SectorExcess3M": 0.2, "SectorAsOf": "2026-09-11",
            "ProfitabilityStatus": "Pass", "FinancialPeriodBasis": "Fiscal-year fallback",
            "FinancialCurrency": "EUR", "FreeCashFlowLatest": -5,
            "FinancialPeriodEnd": "2025-12-31",
            "FinancialSourceURL": "https://finance.yahoo.com/quote/EX/",
            "ShareholderYield": 0.03, "ShareholderYieldStatus": "Pass",
            "ShareholderYieldPeriod": "TTM ending 2026-06-30",
            "ShareholderYieldNetBuybacks": 10, "ShareholderYieldCurrency": "EUR",
            "ManagementMandate": "Private draft note", "ManagementStatus": "Favorable",
        }
        with ExitStack() as stack:
            for name, result in (
                ("cached_financial_history", pd.DataFrame()),
                ("cached_stock_revenue_growth", {}),
                ("cached_company_news", {}),
            ):
                stack.enter_context(patch.object(app, name, return_value=result))
            context = app.load_stock_chat_context(
                "EX", "Example", {"currency": "EUR"},
                pd.DataFrame({"Close": [1]}, index=pd.to_datetime(["2026-09-11"])), evidence,
            )
        financials = context["sections"]["recovery_financials"]
        market = context["sections"]["recovery_market"]
        self.assertEqual(financials["FreeCashFlowLatest"], -5)
        self.assertEqual(financials["FinancialCurrency"], "EUR")
        self.assertEqual(financials["ShareholderYield"], 0.03)
        self.assertEqual(financials["ShareholderYieldPeriod"], "TTM ending 2026-06-30")
        self.assertEqual(market["MarketCapUSD"], 1e9)
        self.assertEqual(market["SectorBenchmark"], "IXN")
        self.assertNotIn("Management", str(context))
        self.assertNotIn("Private draft note", str(context))

    def test_full_financial_evidence_fits_chat_section(self):
        from recovery_financials import analyze_financial_recovery

        columns = pd.to_datetime(["2025-12-31", "2024-12-31"])
        income = pd.DataFrame([[100, 100], [20, 10]], index=["Total Revenue", "Operating Income"], columns=columns)
        cashflow = pd.DataFrame([[10, 5]], index=["Free Cash Flow"], columns=columns)
        balance = pd.DataFrame([[50, 100], [10, 10]], index=["Total Debt", "Cash And Cash Equivalents"], columns=columns)
        evidence = analyze_financial_recovery(
            None, None, None, annual_income=income, annual_cashflow=cashflow,
            annual_balance=balance, info={"sector": "Technology", "financialCurrency": "USD"},
            symbol="EX", as_of="2026-09-11",
        )
        context = build_stock_context("EX", "Example", {}, pd.DataFrame(), {"recovery_financials": evidence})
        section = context["sections"]["recovery_financials"]
        self.assertEqual(section["ProfitabilityStatus"], "Pass")
        self.assertEqual(section["DeleveragingStatus"], "Pass")
        self.assertEqual(section["FreeCashFlowLatest"], 10)

    def test_management_storage_error_remains_explicit_unknown(self):
        import app
        from management_evidence import ManagementEvidenceError

        with patch("management_evidence.get_management_evidence",
                   side_effect=ManagementEvidenceError("Local evidence database is unavailable")):
            result = app.load_recovery_signals("EX", ("management",))
        self.assertEqual(result["ManagementStatus"], "Unknown")
        self.assertIn("database is unavailable", result["ManagementReason"])

    def test_shareholder_yield_evidence_shows_value_period_and_components(self):
        ui = AppTest.from_string(
            "from recovery_ui import render_recovery_evidence\n"
            "render_recovery_evidence({'ShareholderYield': 0.03, 'ShareholderYieldStatus': 'Pass', "
            "'ShareholderYieldPeriod': 'Fiscal year ending 2025-12-31', "
            "'ShareholderYieldDividends': 20, 'ShareholderYieldNetBuybacks': 10, "
            "'ShareholderYieldCurrency': 'USD'})"
        ).run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "3.00%")
        self.assertTrue(any("Fiscal year ending 2025-12-31" in caption.value for caption in ui.caption))
        details = ui.dataframe[-1].value.set_index("Field")
        self.assertEqual(details.loc["ShareholderYieldNetBuybacks", "Value"], "10")


if __name__ == "__main__":
    unittest.main()
