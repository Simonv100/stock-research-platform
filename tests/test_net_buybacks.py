import unittest
from unittest.mock import patch

import pandas as pd

from stock_data import (
    StockDataError,
    extract_net_buybacks,
    extract_shareholder_yield,
    get_cashflow_history,
    get_net_buybacks,
)


def cashflows(net_issuance=-20.0):
    return pd.DataFrame(
        [[net_issuance] * 4], index=["Net Common Stock Issuance"],
        columns=pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]),
    )


class NetBuybackCalculationTests(unittest.TestCase):
    def test_net_buybacks_need_neither_dividend_nor_market_cap_data(self):
        result = extract_net_buybacks(cashflows(), 4, "TTM")
        self.assertEqual(result["NetBuybacks"], 80.0)
        self.assertEqual(result["Period"], "TTM ending 2026-06-30")
        self.assertIsNone(extract_shareholder_yield(cashflows(), 1000, 4, "TTM"))
        self.assertIsNone(extract_net_buybacks(cashflows().rename(
            index={"Net Common Stock Issuance": "Common Stock Dividend Paid"},
        ), 4, "TTM"))

    def test_reported_zero_and_negative_net_buybacks_are_valid_not_missing(self):
        for issuance, net_buybacks in ((0, 0), (10, -40), (-0.01, 0.04)):
            with self.subTest(issuance=issuance):
                result = extract_net_buybacks(cashflows(issuance), 4, "TTM")
                self.assertAlmostEqual(result["NetBuybacks"], net_buybacks)

    def test_component_fallback_subtracts_issuance_and_requires_both_reported_legs(self):
        frame = cashflows().rename(index={"Net Common Stock Issuance": "Repurchase Of Capital Stock"})
        self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))
        for issued, expected in ((0, 80), (10, 40), (20, 0), (30, -40)):
            frame.loc["Issuance Of Capital Stock"] = [issued] * 4
            self.assertEqual(extract_net_buybacks(frame, 4, "TTM")["NetBuybacks"], expected)
        frame.loc["Issuance Of Capital Stock"] = [-10] * 4
        self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))
        frame.loc["Issuance Of Capital Stock"] = [0] * 4
        frame.loc["Repurchase Of Capital Stock"] = [20] * 4
        self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))

    def test_net_common_line_takes_precedence_over_component_fallback(self):
        frame = cashflows(10)
        frame.loc["Repurchase Of Capital Stock"] = [-100] * 4
        frame.loc["Issuance Of Capital Stock"] = [0] * 4
        self.assertEqual(extract_net_buybacks(frame, 4, "TTM")["NetBuybacks"], -40)
        frame.loc["Net Common Stock Issuance", frame.columns[0]] = float("nan")
        self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))

    def test_invalid_latest_values_and_duplicate_rows_do_not_create_a_signal(self):
        for invalid in (None, float("nan"), float("inf"), -float("inf"), True, "bad", pd.Timestamp("2026-01-01"), 2j):
            frame = cashflows().astype(object)
            frame[pd.Timestamp("2025-06-30")] = [-20]
            frame.iloc[0, 0] = invalid
            with self.subTest(invalid=invalid):
                self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))
        self.assertIsNone(extract_net_buybacks(pd.concat([cashflows(), cashflows()]), 4, "TTM"))
        self.assertIsNone(extract_net_buybacks(cashflows(-1e308), 4, "TTM"))

    def test_missing_and_duplicate_quarters_are_not_ttm(self):
        for dates in (
            ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"],
            ["2026-06-30", "2026-06-30", "2025-12-31", "2025-09-30"],
        ):
            frame = cashflows()
            frame.columns = pd.to_datetime(dates)
            self.assertIsNone(extract_net_buybacks(frame, 4, "TTM"))
        self.assertIsNone(extract_net_buybacks(cashflows().iloc[:, :3], 4, "TTM"))

    def test_current_ttm_preferred_even_when_annual_buybacks_are_more_favorable(self):
        annual = cashflows(-100).iloc[:, :1].rename(columns=lambda value: pd.Timestamp("2025-12-31"))
        with patch("stock_data.get_cashflow_history", side_effect=lambda _, frequency: cashflows(10) if frequency == "quarterly" else annual) as loader:
            result = get_net_buybacks("EX", as_of="2026-09-20")
        self.assertEqual(result["NetBuybacks"], -40)
        self.assertEqual(result["PeriodBasis"], "TTM")
        loader.assert_called_once_with("EX", "quarterly")

    def test_incomplete_or_stale_ttm_uses_labeled_current_fiscal_year(self):
        annual = cashflows(-100).iloc[:, :1].rename(columns=lambda value: pd.Timestamp("2025-12-31"))
        for quarterly in (
            cashflows().iloc[:, :3],
            cashflows().rename(columns=lambda value: value - pd.DateOffset(years=2)),
        ):
            with patch("stock_data.get_cashflow_history", side_effect=lambda _, frequency: quarterly if frequency == "quarterly" else annual):
                result = get_net_buybacks("EX", as_of="2026-09-20")
            self.assertEqual(result["Period"], "Fiscal year ending 2025-12-31")
            self.assertEqual(result["NetBuybacks"], 100)

    def test_freshness_boundaries_and_future_periods(self):
        latest = pd.Timestamp("2026-06-30")
        for days, available in ((0, True), (200, True), (201, False), (-1, False)):
            with patch("stock_data.get_cashflow_history", side_effect=lambda _, frequency: cashflows() if frequency == "quarterly" else pd.DataFrame()):
                result = get_net_buybacks("EX", as_of=latest + pd.Timedelta(days=days))
            self.assertEqual(result is not None, available)
        annual = cashflows().iloc[:, :1]
        for days, available in ((550, True), (551, False), (-1, False)):
            with patch("stock_data.get_cashflow_history", side_effect=lambda _, frequency: pd.DataFrame() if frequency == "quarterly" else annual):
                result = get_net_buybacks("EX", as_of=latest + pd.Timedelta(days=days))
            self.assertEqual(result is not None, available)

    def test_provider_errors_are_not_disguised_as_no_buybacks(self):
        with patch("stock_data.get_cashflow_history", side_effect=StockDataError("Provider down")):
            with self.assertRaisesRegex(StockDataError, "Provider down"):
                get_net_buybacks("EX")
        with self.assertRaises(ValueError):
            get_cashflow_history("EX", "monthly")


class NetBuybackAssessmentTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        for cache in (app.cached_cashflow_history, app.cached_net_buyback_assessment,
                      app.cached_shareholder_yield, app.cached_shareholder_recovery):
            cache.clear()
            self.addCleanup(cache.clear)

    def test_positive_net_sign_and_unreported_currency_do_not_depend_on_market_cap(self):
        for value, status in ((0.01, "Pass"), (0, "Fail"), (-1, "Fail"),
                              (None, "Unknown"), (float("nan"), "Unknown"), (float("inf"), "Unknown"), (True, "Unknown")):
            self.app.cached_net_buyback_assessment.clear()
            with (
                patch.object(self.app, "cached_info", return_value={}),
                patch.object(self.app, "get_net_buybacks", return_value={
                    "NetBuybacks": value, "Period": "TTM ending 2026-06-30", "PeriodBasis": "TTM",
                    "PeriodEnd": "2026-06-30", "NetBuybackMethod": "Negative net common issuance.",
                }),
            ):
                result = self.app.cached_net_buyback_assessment("EX")
            self.assertEqual(result["BuybackStatus"], status)
            self.assertEqual(result["BuybackCurrency"], "Unreported")
            self.assertTrue(result["BuybackReason"])

    def test_fund_does_not_fetch_and_provider_failure_has_an_audit_reason(self):
        with patch.object(self.app, "cached_info", return_value={"quoteType": "ETF"}), \
                patch.object(self.app, "get_net_buybacks") as loader:
            self.assertEqual(self.app.cached_net_buyback_assessment("EX")["BuybackStatus"], "Not applicable")
            loader.assert_not_called()
        self.app.cached_net_buyback_assessment.clear()
        with patch.object(self.app, "cached_info", return_value={"financialCurrency": "JPY"}), \
                patch.object(self.app, "get_net_buybacks", side_effect=StockDataError("Cash feed unavailable")):
            result = self.app.cached_net_buyback_assessment("EX")
        self.assertEqual(result["BuybackStatus"], "Unknown")
        self.assertIn("Cash feed unavailable", result["BuybackReason"])

    def test_missing_metadata_is_explicit_but_does_not_invalidate_reported_cash_sign(self):
        with patch.object(self.app, "cached_info", side_effect=StockDataError("No metadata")), \
                patch.object(self.app, "get_net_buybacks", return_value=extract_net_buybacks(cashflows(), 4, "TTM")):
            result = self.app.cached_net_buyback_assessment("EX")
        self.assertEqual(result["BuybackStatus"], "Pass")
        self.assertIn("Reporting currency unavailable", result["BuybackReason"])

    def test_buybacks_and_shareholder_yield_share_cashflow_cache(self):
        frame = cashflows()
        frame.columns = pd.date_range(
            end=pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.offsets.QuarterEnd(),
            periods=4, freq="QE",
        )[::-1]
        frame.loc["Common Stock Dividend Paid"] = [-10] * 4
        info = {"currency": "USD", "financialCurrency": "USD", "marketCap": 1000, "quoteType": "EQUITY"}
        with patch.object(self.app, "cached_info", return_value=info), \
                patch.object(self.app, "get_cashflow_history", return_value=frame) as provider:
            buyback = self.app.cached_net_buyback_assessment("EX")
            shareholder = self.app.cached_shareholder_recovery("EX", self.app.RECOVERY_MODEL_VERSION)
            self.app.cached_net_buyback_assessment("EX")
            self.assertEqual(buyback["BuybackStatus"], "Pass")
            self.assertEqual(shareholder["ShareholderYieldStatus"], "Pass")
            self.assertEqual(buyback["NetBuybacks"], shareholder["ShareholderYieldNetBuybacks"])
            provider.assert_called_once_with("EX", "quarterly", statement_loader=self.app.cached_statement_history)
        self.assertEqual(self.app.cached_cashflow_history._info.ttl, 86400)

    def test_missing_quarterly_dividends_can_produce_distinct_labeled_periods(self):
        quarterly = cashflows()
        quarterly.columns = pd.date_range(
            end=pd.Timestamp.now(tz="UTC").tz_localize(None).normalize() - pd.offsets.QuarterEnd(),
            periods=4, freq="QE",
        )[::-1]
        annual = pd.DataFrame(
            [[-20.0], [-10.0]],
            index=["Net Common Stock Issuance", "Common Stock Dividend Paid"],
            columns=[pd.Timestamp(year=pd.Timestamp.now().year - 1, month=12, day=31)],
        )
        info = {"currency": "USD", "financialCurrency": "USD", "marketCap": 1000}
        with patch.object(self.app, "cached_info", return_value=info), patch.object(
            self.app, "get_cashflow_history",
            side_effect=lambda _, frequency, **kwargs: quarterly if frequency == "quarterly" else annual,
        ) as provider:
            buyback = self.app.cached_net_buyback_assessment("EX")
            shareholder = self.app.cached_shareholder_recovery("EX", self.app.RECOVERY_MODEL_VERSION)
        self.assertEqual(buyback["BuybackPeriodBasis"], "TTM")
        self.assertEqual(shareholder["ShareholderYieldBasis"], "Fiscal year")
        self.assertEqual(buyback["NetBuybacks"], 80)
        self.assertEqual(shareholder["ShareholderYieldNetBuybacks"], 20)
        self.assertEqual(provider.call_count, 2)


if __name__ == "__main__":
    unittest.main()
