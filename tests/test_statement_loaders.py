import unittest
from functools import lru_cache
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, call, patch

import pandas as pd
from curl_cffi.requests.exceptions import Timeout
from yfinance.exceptions import YFException

from recovery_financials import analyze_financial_recovery, get_financial_recovery
from stock_data import (
    StockDataError,
    extract_financial_history,
    extract_share_count_history,
    get_cashflow_history,
    get_financial_history,
    get_net_buybacks,
    get_revenue_growth_scan,
    get_revenue_history,
    get_share_count_history,
    get_shareholder_yield,
    get_statement_history,
    merge_quarterly_revenue_histories,
    statement_revenue_growth_summary,
)


INFO = {
    "quoteType": "EQUITY",
    "financialCurrency": "USD",
    "sector": "Industrials",
    "industry": "Machinery",
}
AS_OF = pd.Timestamp("2026-08-01")
QUARTERS = pd.date_range("2024-09-30", periods=8, freq="QE")[::-1]
YEARS = pd.to_datetime(["2025-12-31", "2024-12-31"])
ATTRIBUTES = {
    ("income", "quarterly"): "quarterly_income_stmt",
    ("income", "annual"): "income_stmt",
    ("cashflow", "quarterly"): "quarterly_cashflow",
    ("cashflow", "annual"): "cashflow",
    ("balance", "quarterly"): "quarterly_balance_sheet",
    ("balance", "annual"): "balance_sheet",
}


def statements(frequency="quarterly"):
    dates = QUARTERS if frequency == "quarterly" else YEARS
    half = len(dates) // 2
    income = pd.DataFrame(
        [
            [120.0] * half + [100.0] * half,
            [24.0] * half + [10.0] * half,
            [72.0] * half + [60.0] * half,
        ],
        index=["Total Revenue", "Operating Income", "Cost Of Revenue"],
        columns=dates,
    )
    cashflow = pd.DataFrame(
        [
            [10.0] * half + [5.0] * half,
            [-20.0] * len(dates),
            [-5.0] * len(dates),
        ],
        index=["Free Cash Flow", "Net Common Stock Issuance", "Common Stock Dividend Paid"],
        columns=dates,
    )
    balance = pd.DataFrame(
        [[80.0, 100.0], [20.0, 20.0], [90.0, 100.0]],
        index=["Total Debt", "Cash And Cash Equivalents", "Ordinary Shares Number"],
        columns=dates[[0, half]],
    )
    return {"income": income, "cashflow": cashflow, "balance": balance}


class RawStatementLoaderTests(unittest.TestCase):
    def test_all_statement_frequencies_return_the_original_yahoo_frame(self):
        frames = {
            attribute: statements(frequency)[statement]
            for (statement, frequency), attribute in ATTRIBUTES.items()
        }
        ticker = SimpleNamespace(**frames)
        with patch("stock_data.yf.Ticker", return_value=ticker) as ticker_type:
            for (statement, frequency), attribute in ATTRIBUTES.items():
                with self.subTest(statement=statement, frequency=frequency):
                    actual = get_statement_history("TEST", statement, frequency)
                    self.assertIs(actual, frames[attribute])
            self.assertEqual(ticker_type.call_args_list, [call("TEST")] * 6)

    def test_empty_raw_statement_is_not_replaced_or_treated_as_error(self):
        frame = pd.DataFrame()
        with patch("stock_data.yf.Ticker", return_value=SimpleNamespace(income_stmt=frame)):
            self.assertIs(get_statement_history("TEST", "income", "annual"), frame)

    def test_unsupported_parameters_fail_before_any_provider_call(self):
        with patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")):
            for statement, frequency in (
                ("earnings", "annual"), ("INCOME", "quarterly"),
                ("income", "monthly"), ("cashflow", "Annual"),
            ):
                with self.subTest(statement=statement, frequency=frequency):
                    with self.assertRaises(ValueError):
                        get_statement_history("TEST", statement, frequency)

    def test_expected_constructor_and_statement_errors_are_wrapped_with_cause(self):
        for error in (Timeout("timed out"), YFException("provider failed")):
            for during_construction in (True, False):
                with self.subTest(error=error, during_construction=during_construction):
                    ticker = Mock()
                    type(ticker).quarterly_income_stmt = PropertyMock(side_effect=error)
                    with patch(
                        "stock_data.yf.Ticker", return_value=ticker,
                        side_effect=error if during_construction else None,
                    ):
                        with self.assertRaises(StockDataError) as caught:
                            get_statement_history("TEST", "income", "quarterly")
                    self.assertIs(caught.exception.__cause__, error)
                    self.assertIn("TEST", str(caught.exception))

    def test_unexpected_provider_errors_are_not_swallowed(self):
        error = RuntimeError("programmer bug")
        with patch("stock_data.yf.Ticker", side_effect=error):
            with self.assertRaises(RuntimeError) as caught:
                get_statement_history("TEST", "income", "quarterly")
        self.assertIs(caught.exception, error)


class ExtractedStatementLoaderTests(unittest.TestCase):
    def test_injected_loaders_preserve_extraction_and_parameter_mapping(self):
        for frequency in ("quarterly", "annual"):
            frames = statements(frequency)
            for function, statement, extract in (
                (get_financial_history, "income", extract_financial_history),
                (get_share_count_history, "balance", extract_share_count_history),
                (get_cashflow_history, "cashflow", lambda frame: frame),
            ):
                with self.subTest(function=function.__name__, frequency=frequency):
                    original = frames[statement].copy(deep=True)
                    loader = Mock(return_value=frames[statement])
                    with (
                        patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")),
                        patch("stock_data.get_statement_history", side_effect=AssertionError("Default used")),
                    ):
                        actual = function("TEST", frequency, statement_loader=loader)
                    loader.assert_called_once_with("TEST", statement, frequency)
                    pd.testing.assert_frame_equal(actual, extract(frames[statement]))
                    pd.testing.assert_frame_equal(frames[statement], original)
                    if statement == "cashflow":
                        self.assertIs(actual, frames[statement])

    def test_default_public_functions_use_shared_raw_loader(self):
        frames = statements()
        with (
            patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")),
            patch(
                "stock_data.get_statement_history",
                side_effect=lambda symbol, statement, frequency: frames[statement],
            ) as loader,
        ):
            pd.testing.assert_frame_equal(
                get_financial_history("TEST", "quarterly"),
                extract_financial_history(frames["income"]),
            )
            pd.testing.assert_frame_equal(
                get_share_count_history("TEST", "quarterly"),
                extract_share_count_history(frames["balance"]),
            )
            self.assertIs(get_cashflow_history("TEST", "quarterly"), frames["cashflow"])
            pd.testing.assert_frame_equal(
                get_revenue_history("TEST", "quarterly"),
                extract_financial_history(frames["income"])[["Period", "Revenue", "Growth"]],
            )
        self.assertEqual(loader.call_args_list, [
            call("TEST", "income", "quarterly"),
            call("TEST", "balance", "quarterly"),
            call("TEST", "cashflow", "quarterly"),
            call("TEST", "income", "quarterly"),
        ])

    def test_default_public_functions_work_with_mocked_yahoo_properties(self):
        for frequency in ("quarterly", "annual"):
            frames = statements(frequency)
            ticker = SimpleNamespace(**{
                ATTRIBUTES[(statement, frequency)]: frame
                for statement, frame in frames.items()
            })
            with self.subTest(frequency=frequency), patch("stock_data.yf.Ticker", return_value=ticker):
                pd.testing.assert_frame_equal(
                    get_financial_history("TEST", frequency), extract_financial_history(frames["income"]),
                )
                pd.testing.assert_frame_equal(
                    get_share_count_history("TEST", frequency), extract_share_count_history(frames["balance"]),
                )
                self.assertIs(get_cashflow_history("TEST", frequency), frames["cashflow"])

    def test_invalid_frequency_does_not_invoke_injected_loader(self):
        for function in (get_financial_history, get_share_count_history, get_cashflow_history):
            loader = Mock(side_effect=AssertionError("Unexpected fetch"))
            with self.subTest(function=function.__name__), self.assertRaises(ValueError):
                function("TEST", "monthly", statement_loader=loader)
            loader.assert_not_called()

    def test_injected_loader_errors_remain_explicit(self):
        for function in (get_financial_history, get_share_count_history, get_cashflow_history):
            for error in (Timeout("timeout"), YFException("provider failed"),
                          StockDataError("unavailable"), RuntimeError("bug")):
                with self.subTest(function=function.__name__, error=error):
                    with self.assertRaises(
                        StockDataError if isinstance(error, (Timeout, YFException)) else type(error),
                    ) as caught:
                        function("TEST", "quarterly", statement_loader=Mock(side_effect=error))
                    if isinstance(error, (Timeout, YFException)):
                        self.assertIs(caught.exception.__cause__, error)
                    else:
                        self.assertIs(caught.exception, error)

    def test_shared_raw_frames_serve_extraction_and_recovery_without_refetch(self):
        frames = statements()
        originals = {name: frame.copy(deep=True) for name, frame in frames.items()}
        source = Mock(side_effect=lambda symbol, statement, frequency: frames[statement])
        cached_loader = lru_cache(maxsize=None)(source)
        with (
            patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")),
            patch("recovery_financials.get_company_info", side_effect=AssertionError("Metadata fetched")),
            patch("recovery_financials._date", return_value=AS_OF),
        ):
            financials = get_financial_history("TEST", "quarterly", statement_loader=cached_loader)
            shares = get_share_count_history("TEST", "quarterly", statement_loader=cached_loader)
            cashflow = get_cashflow_history("TEST", "quarterly", statement_loader=cached_loader)
            recovery = get_financial_recovery("TEST", info=INFO, statement_loader=cached_loader)
        self.assertEqual(source.call_args_list, [
            call("TEST", "income", "quarterly"),
            call("TEST", "balance", "quarterly"),
            call("TEST", "cashflow", "quarterly"),
        ])
        pd.testing.assert_frame_equal(financials, extract_financial_history(frames["income"]))
        pd.testing.assert_frame_equal(shares, extract_share_count_history(frames["balance"]))
        self.assertIs(cashflow, frames["cashflow"])
        self.assertEqual(recovery, analyze_financial_recovery(
            **frames, info=INFO, symbol="TEST", as_of=AS_OF,
        ))
        for name, original in originals.items():
            pd.testing.assert_frame_equal(frames[name], original)

    def test_capital_return_cashflow_injection_still_composes_with_raw_loader(self):
        frames = statements()
        raw_loader = Mock(return_value=frames["cashflow"])

        def cashflow_loader(symbol, frequency):
            return get_cashflow_history(symbol, frequency, statement_loader=raw_loader)

        with patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")):
            buybacks = get_net_buybacks("TEST", as_of=AS_OF, cashflow_loader=cashflow_loader)
            yield_result = get_shareholder_yield(
                "TEST", 1000.0, as_of=AS_OF, cashflow_loader=cashflow_loader,
            )
        self.assertEqual(buybacks["NetBuybacks"], 80.0)
        self.assertEqual(yield_result["Dividends"], 20.0)
        self.assertEqual(yield_result["ShareholderYield"], 0.1)
        self.assertEqual(raw_loader.call_args_list, [call("TEST", "cashflow", "quarterly")] * 2)


class RecoveryStatementLoaderTests(unittest.TestCase):
    def setUp(self):
        self.quarterly = statements()
        self.annual = statements("annual")
        self.loader = Mock(side_effect=lambda symbol, statement, frequency: (
            self.quarterly if frequency == "quarterly" else self.annual
        )[statement])
        ticker_patch = patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch"))
        date_patch = patch("recovery_financials._date", return_value=AS_OF)
        info_patch = patch("recovery_financials.get_company_info", return_value=INFO)
        self.ticker = ticker_patch.start()
        self.addCleanup(ticker_patch.stop)
        date_patch.start()
        self.addCleanup(date_patch.stop)
        self.get_info = info_patch.start()
        self.addCleanup(info_patch.stop)

    def fetch(self, info=INFO):
        return get_financial_recovery(" test ", info=info, statement_loader=self.loader)

    def expected(self, info=INFO):
        return analyze_financial_recovery(
            **self.quarterly,
            **{f"annual_{name}": frame for name, frame in self.annual.items()},
            info=info, symbol="TEST", as_of=AS_OF,
        )

    def assert_requests(self, annual_statements=()):
        expected = [
            call("TEST", statement, "quarterly") for statement in ("income", "cashflow", "balance")
        ]
        expected += [call("TEST", statement, "annual") for statement in annual_statements]
        self.assertEqual(self.loader.call_args_list, expected)
        self.ticker.assert_not_called()

    def test_complete_quarterly_evidence_avoids_metadata_and_annual_fetches(self):
        self.assertEqual(self.fetch(), self.expected())
        self.get_info.assert_not_called()
        self.assert_requests()

    def test_only_profitability_fallback_fetches_annual_income_and_cashflow(self):
        self.quarterly["income"] = self.quarterly["income"].iloc[:, :5]
        self.quarterly["cashflow"] = self.quarterly["cashflow"].iloc[:, :5]
        result = self.fetch()
        self.assertEqual(result, self.expected())
        self.assertIn("Fiscal year", result["FinancialPeriodBasis"])
        self.assertIn("Quarterly", result["FinancialDebtPeriodBasis"])
        self.assert_requests(("income", "cashflow"))

    def test_only_deleveraging_fallback_fetches_annual_cashflow_and_balance(self):
        self.quarterly["balance"] = pd.DataFrame()
        result = self.fetch()
        self.assertEqual(result, self.expected())
        self.assertIn("four quarters", result["FinancialPeriodBasis"])
        self.assertIn("Fiscal year", result["FinancialDebtPeriodBasis"])
        self.assert_requests(("cashflow", "balance"))

    def test_both_fallbacks_fetch_each_annual_statement_once(self):
        self.quarterly = {name: pd.DataFrame() for name in self.quarterly}
        result = self.fetch()
        self.assertEqual(result, self.expected())
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assert_requests(("income", "cashflow", "balance"))

    def test_fail_is_not_a_reason_to_fetch_annual_statements(self):
        self.quarterly["income"].loc["Operating Income"] = 0.0
        self.quarterly["balance"].loc["Total Debt"] = 100.0
        result = self.fetch()
        self.assertEqual(result["ProfitabilityStatus"], "Fail")
        self.assertEqual(result["DeleveragingStatus"], "Fail")
        self.assert_requests()

    def test_stale_but_complete_quarters_do_not_trigger_annual_fallback(self):
        with patch("recovery_financials._date", return_value=pd.Timestamp("2030-01-01")):
            result = self.fetch()
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        self.assert_requests()

    def test_supplied_empty_metadata_is_not_refetched(self):
        result = self.fetch(info={})
        self.get_info.assert_not_called()
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        self.assert_requests()

    def test_missing_metadata_is_fetched_once_and_shared_with_analysis(self):
        self.assertEqual(self.fetch(info=None), self.expected())
        self.get_info.assert_called_once_with("TEST")
        self.assert_requests()

    def test_unsuitable_firms_and_funds_skip_all_statement_loaders(self):
        for info in (
            {"quoteType": "ETF"}, {"quoteType": "MUTUALFUND"},
            {**INFO, "sector": "Financial Services"}, {**INFO, "industry": "REIT - Retail"},
        ):
            for supplied in (True, False):
                with self.subTest(info=info, supplied=supplied):
                    self.get_info.reset_mock()
                    self.get_info.return_value = info
                    result = self.fetch(info=info if supplied else None)
                    self.assertEqual(result["ProfitabilityStatus"], "Not applicable")
                    self.assertEqual(result["DeleveragingStatus"], "Not applicable")
                    self.loader.assert_not_called()
                    self.ticker.assert_not_called()
                    if supplied:
                        self.get_info.assert_not_called()
                    else:
                        self.get_info.assert_called_once_with("TEST")

    def test_default_recovery_loader_uses_shared_statement_api(self):
        with patch("recovery_financials.get_statement_history", self.loader):
            result = get_financial_recovery(" test ", info=INFO)
        self.assertEqual(result, self.expected())
        self.assert_requests()

    def test_default_recovery_loader_works_with_mocked_yahoo_properties(self):
        self.ticker.side_effect = None
        self.ticker.return_value = SimpleNamespace(**{
            ATTRIBUTES[(statement, "quarterly")]: frame
            for statement, frame in self.quarterly.items()
        })
        result = get_financial_recovery("TEST", info=INFO)
        self.assertEqual(result, self.expected())
        self.assertEqual(self.ticker.call_args_list, [call("TEST")] * 3)
        self.loader.assert_not_called()

    def test_loader_exceptions_preserve_provider_causes_and_unknown_errors(self):
        for frequency in ("quarterly", "annual"):
            for error in (Timeout("timeout"), YFException("provider failed"),
                          StockDataError("unavailable"), RuntimeError("bug")):
                with self.subTest(frequency=frequency, error=error):
                    def load(symbol, statement, requested_frequency):
                        if requested_frequency == frequency:
                            raise error
                        return pd.DataFrame()

                    with self.assertRaises(
                        StockDataError if isinstance(error, (Timeout, YFException)) else type(error),
                    ) as caught:
                        get_financial_recovery("TEST", info=INFO, statement_loader=load)
                    if isinstance(error, (Timeout, YFException)):
                        self.assertIs(caught.exception.__cause__, error)
                    else:
                        self.assertIs(caught.exception, error)

    def test_metadata_errors_and_blank_symbols_do_not_fetch_statements(self):
        self.get_info.side_effect = StockDataError("metadata unavailable")
        with self.assertRaisesRegex(StockDataError, "metadata unavailable"):
            self.fetch(info=None)
        self.get_info.reset_mock()
        with self.assertRaises(ValueError):
            get_financial_recovery(" ", statement_loader=self.loader)
        self.get_info.assert_not_called()
        self.loader.assert_not_called()


class RevenueScanLoaderTests(unittest.TestCase):
    def test_injected_sources_preserve_merge_growth_and_sorted_unique_symbols(self):
        quarters = pd.date_range("2024-03-31", periods=10, freq="QE")
        historical = pd.DataFrame({"Period": quarters[:8], "Revenue": [10.0] * 8})
        recent = pd.DataFrame({"Period": quarters[6:], "Revenue": [11.0, 12.0, 14.0, 17.0]})
        annual = pd.DataFrame({
            "Period": pd.to_datetime(["2025-12-31"]), "Revenue": [100.0], "Growth": [-0.5],
        })
        sec_loader = Mock(return_value=historical)
        financial_loader = Mock(side_effect=lambda symbol, frequency: (
            recent if frequency == "quarterly" else annual
        ))
        with (
            patch("stock_data.yf.Ticker", side_effect=AssertionError("Unexpected fetch")),
            patch("stock_data.get_sec_quarterly_revenue", side_effect=AssertionError("Default used")),
            patch("stock_data.get_financial_history", side_effect=AssertionError("Default used")),
        ):
            result = get_revenue_growth_scan(
                ["ZZZ", "AAA", "ZZZ"], sec_loader=sec_loader, financial_loader=financial_loader,
            )
        summary = statement_revenue_growth_summary(
            merge_quarterly_revenue_histories(historical, recent), annual,
        )
        self.assertEqual(result.to_dict("records"), [
            {"Symbol": symbol, **summary} for symbol in ("AAA", "ZZZ")
        ])
        self.assertTrue(summary["RevenueAccelerating"])
        self.assertEqual(len(summary["RevenueGrowthHistory"]), 3)
        self.assertEqual(sec_loader.call_args_list, [call("AAA"), call("ZZZ")])
        self.assertEqual(financial_loader.call_args_list, [
            call(symbol, frequency) for symbol in ("AAA", "ZZZ") for frequency in ("quarterly", "annual")
        ])

    def test_unavailable_sources_preserve_unavailable_and_annual_fallback_rows(self):
        annual = pd.DataFrame({
            "Period": pd.to_datetime(["2025-12-31"]), "Revenue": [25.0], "Growth": [0.25],
        })
        sec_loader = Mock(side_effect=StockDataError("SEC unavailable"))
        financial_loader = Mock(side_effect=[
            StockDataError("Quarterly unavailable"), StockDataError("Annual unavailable"),
            pd.DataFrame(), annual,
        ])
        result = get_revenue_growth_scan(
            ["MISSING", "VALID"], sec_loader=sec_loader, financial_loader=financial_loader,
        ).set_index("Symbol")
        self.assertTrue(pd.isna(result.loc["MISSING", "RevenueGrowth"]))
        self.assertEqual(result.loc["MISSING", "RevenuePeriod"], "Statement growth unavailable")
        self.assertFalse(result.loc["MISSING", "RevenueAccelerating"])
        self.assertEqual(result.loc["VALID", "RevenueBasis"], "Fiscal-year fallback")
        self.assertEqual(result.loc["VALID", "RevenueGrowth"], 0.25)
        self.assertFalse(result.loc["VALID", "RevenueAccelerating"])

    def test_default_revenue_scan_callbacks_are_resolved_at_call_time(self):
        with (
            patch("stock_data.get_sec_quarterly_revenue", return_value=pd.DataFrame()) as sec_loader,
            patch("stock_data.get_financial_history", return_value=pd.DataFrame()) as financial_loader,
        ):
            result = get_revenue_growth_scan(["TEST"])
        self.assertEqual(result.iloc[0]["RevenueBasis"], "Unavailable")
        sec_loader.assert_called_once_with("TEST")
        self.assertEqual(financial_loader.call_args_list, [
            call("TEST", "quarterly"), call("TEST", "annual"),
        ])

    def test_unexpected_source_errors_are_not_disguised_as_unavailable(self):
        for failing_source in ("sec", "financial"):
            for error in (RuntimeError("bug"), Timeout("unwrapped transport error")):
                sec_loader = Mock(return_value=pd.DataFrame())
                financial_loader = Mock(return_value=pd.DataFrame())
                (sec_loader if failing_source == "sec" else financial_loader).side_effect = error
                with self.subTest(source=failing_source, error=error), self.assertRaises(type(error)) as caught:
                    get_revenue_growth_scan(
                        ["TEST"], sec_loader=sec_loader, financial_loader=financial_loader,
                    )
                self.assertIs(caught.exception, error)

    def test_empty_scan_does_not_fetch_sources(self):
        sec_loader = Mock()
        financial_loader = Mock()
        result = get_revenue_growth_scan([], sec_loader=sec_loader, financial_loader=financial_loader)
        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), [])
        sec_loader.assert_not_called()
        financial_loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
