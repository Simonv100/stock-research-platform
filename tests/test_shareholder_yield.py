import unittest
from unittest.mock import patch

import pandas as pd

from stock_data import StockDataError, extract_shareholder_yield, get_shareholder_yield


def cashflows(net_issuance=-20.0):
    return pd.DataFrame(
        [[-10.0] * 4, [net_issuance] * 4],
        index=["Common Stock Dividend Paid", "Net Common Stock Issuance"],
        columns=pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]),
    )


class ShareholderYieldCalculationTests(unittest.TestCase):
    def test_buybacks_and_dilution_have_opposite_signed_effects(self):
        for issuance, expected in ((-20.0, 0.12), (10.0, 0.0), (20.0, -0.04)):
            with self.subTest(issuance=issuance):
                result = extract_shareholder_yield(cashflows(issuance), 1000, 4, "TTM")
                self.assertAlmostEqual(result["ShareholderYield"], expected)
                self.assertEqual(result["PeriodEnd"], "2026-06-30")
                self.assertEqual(result["PeriodBasis"], "TTM")

    def test_missing_latest_values_do_not_backfill_older_quarters(self):
        frame = cashflows()
        frame[pd.Timestamp("2025-06-30")] = [-10.0, -20.0]
        for invalid in (None, float("nan"), float("inf"), float("-inf")):
            with self.subTest(invalid=invalid):
                frame.loc["Net Common Stock Issuance", pd.Timestamp("2026-06-30")] = invalid
                self.assertIsNone(extract_shareholder_yield(frame, 1000, 4, "TTM"))

    def test_ttm_rejects_gaps_and_duplicate_dates(self):
        frame = cashflows()
        for dates in (
            ["2026-06-30", "2026-03-31", "2025-12-31", "2025-06-30"],
            ["2026-06-30", "2026-06-30", "2025-12-31", "2025-09-30"],
        ):
            with self.subTest(dates=dates):
                frame.columns = pd.to_datetime(dates)
                self.assertIsNone(extract_shareholder_yield(frame, 1000, 4, "TTM"))

    def test_component_fallback_requires_reported_issuance_not_assumed_zero(self):
        frame = cashflows().rename(index={"Net Common Stock Issuance": "Repurchase Of Capital Stock"})
        self.assertIsNone(extract_shareholder_yield(frame, 1000, 4, "TTM"))
        frame.loc["Issuance Of Capital Stock"] = [30.0] * 4
        self.assertEqual(extract_shareholder_yield(frame, 1000, 4, "TTM")["ShareholderYield"], 0)
        frame.loc["Issuance Of Capital Stock", pd.Timestamp("2026-06-30")] = float("nan")
        self.assertIsNone(extract_shareholder_yield(frame, 1000, 4, "TTM"))
        frame.loc["Issuance Of Capital Stock"] = [0.0] * 4
        self.assertAlmostEqual(extract_shareholder_yield(frame, 1000, 4, "TTM")["ShareholderYield"], 0.12)

    def test_invalid_market_caps_never_fetch_or_produce_yield(self):
        for cap in (None, 0, -1, float("nan"), float("inf"), float("-inf"), True, "invalid"):
            with self.subTest(cap=cap), patch("stock_data.yf.Ticker") as ticker:
                self.assertIsNone(get_shareholder_yield("EX", cap))
                self.assertIsNone(extract_shareholder_yield(cashflows(), cap, 4, "TTM"))
                ticker.assert_not_called()

    def test_ttm_preferred_and_annual_fallback_is_explicit(self):
        annual = pd.DataFrame(
            [[-50], [-50]], index=cashflows().index,
            columns=pd.to_datetime(["2025-12-31"]),
        )
        with patch("stock_data.yf.Ticker") as ticker:
            ticker.return_value.quarterly_cashflow = cashflows()
            ticker.return_value.cashflow = annual
            ttm = get_shareholder_yield("EX", 1000, as_of="2026-09-20")
            self.assertEqual(ttm["PeriodBasis"], "TTM")
            ticker.return_value.quarterly_cashflow = cashflows().iloc[:, :3]
            result = get_shareholder_yield("EX", 1000, as_of="2026-09-20")
            self.assertEqual(result["Period"], "Fiscal year ending 2025-12-31")
            self.assertAlmostEqual(result["ShareholderYield"], 0.1)
            ticker.return_value.quarterly_cashflow = cashflows().rename(
                columns=lambda date: date - pd.DateOffset(years=2),
            )
            self.assertEqual(get_shareholder_yield("EX", 1000, as_of="2026-09-20"), result)

    def test_stale_and_future_periods_do_not_pass(self):
        with patch("stock_data.yf.Ticker") as ticker:
            for shift in (-2, 2):
                with self.subTest(shift=shift):
                    frame = cashflows().rename(columns=lambda date: date + pd.DateOffset(years=shift))
                    ticker.return_value.quarterly_cashflow = frame
                    ticker.return_value.cashflow = frame.iloc[:, :1]
                    self.assertIsNone(get_shareholder_yield("EX", 1000, as_of="2026-09-20"))


class ShareholderYieldAssessmentTests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        app.cached_shareholder_recovery.clear()
        self.addCleanup(app.cached_shareholder_recovery.clear)
        self.info = {"currency": "USD", "financialCurrency": "USD", "marketCap": 1000, "quoteType": "EQUITY"}
        self.metrics = extract_shareholder_yield(cashflows(), 1000, 4, "TTM")

    def assess(self, info=None, data=None):
        self.app.cached_shareholder_recovery.clear()
        with (
            patch.object(self.app, "cached_info", return_value=self.info if info is None else info),
            patch.object(self.app, "cached_shareholder_yield", return_value=self.metrics if data is None else data),
        ):
            return self.app.load_recovery_signals("EX", ("shareholder_yield",))

    def test_strict_positive_boundary_and_nonfinite_unknowns(self):
        for value, status in ((0.01, "Pass"), (0, "Fail"), (-0.01, "Fail"),
                              (None, "Unknown"), (float("nan"), "Unknown"),
                              (float("inf"), "Unknown"), (True, "Unknown")):
            with self.subTest(value=value):
                result = self.assess(data={**self.metrics, "ShareholderYield": value})
                self.assertEqual(result["ShareholderYieldStatus"], status)
                self.assertTrue(result["ShareholderYieldReason"])

    def test_currencies_must_match_and_pence_does_not_scale_market_cap(self):
        result = self.assess(info={**self.info, "currency": "GBp", "financialCurrency": "GBP"})
        self.assertEqual(result["ShareholderYieldStatus"], "Pass")
        self.assertEqual(result["ShareholderYieldMarketCap"], 1000)
        self.assertEqual(result["ShareholderYieldCurrency"], "GBP")
        for changes in ({"financialCurrency": "EUR"}, {"financialCurrency": None}, {"currency": None},
                        {"marketCap": None}, {"marketCap": float("inf")}, {"marketCap": 0}):
            with self.subTest(changes=changes):
                self.assertEqual(self.assess(info={**self.info, **changes})["ShareholderYieldStatus"], "Unknown")

    def test_funds_are_not_applicable_and_dont_load_cash_flows(self):
        with (
            patch.object(self.app, "cached_info", return_value={**self.info, "quoteType": "ETF"}),
            patch.object(self.app, "cached_shareholder_yield") as loader,
        ):
            result = self.app.load_recovery_signals("EX", ("shareholder_yield",))
        self.assertEqual(result["ShareholderYieldStatus"], "Not applicable")
        loader.assert_not_called()

    def test_missing_data_provider_errors_and_cache_reuse(self):
        with (
            patch.object(self.app, "cached_info", return_value=self.info),
            patch.object(self.app, "cached_shareholder_yield", return_value=None) as loader,
        ):
            result = self.app.load_recovery_signals("EX", ("shareholder_yield",))
            self.assertEqual(result["ShareholderYieldStatus"], "Unknown")
            self.assertIn("No complete", result["ShareholderYieldReason"])
            self.app.load_recovery_signals("EX", ("shareholder_yield",))
            loader.assert_called_once()
            self.app.cached_shareholder_recovery.clear()
            loader.side_effect = StockDataError("Provider temporarily unavailable")
            result = self.app.load_recovery_signals("EX", ("shareholder_yield",))
            self.assertIn("Provider temporarily unavailable", result["ShareholderYieldReason"])
            self.assertEqual(result["ShareholderYieldStatus"], "Unknown")


if __name__ == "__main__":
    unittest.main()
