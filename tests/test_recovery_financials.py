import json
import unittest
from unittest.mock import PropertyMock, patch

import pandas as pd
from curl_cffi.requests.exceptions import Timeout
from yfinance.exceptions import YFException

from recovery_financials import analyze_financial_recovery, get_financial_recovery
from stock_data import StockDataError


INFO = {"financialCurrency": "USD", "sector": "Industrials", "industry": "Machinery"}
QUARTERS = pd.to_datetime([
    "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31",
    "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31",
])
YEARS = pd.to_datetime(["2025-12-31", "2024-12-31"])


def statements(annual=False):
    dates = YEARS if annual else QUARTERS
    half = len(dates) // 2
    income = pd.DataFrame(
        [[100.0] * len(dates), [20.0] * half + [10.0] * half],
        index=["Total Revenue", "Operating Income"], columns=dates,
    )
    cashflow = pd.DataFrame(
        [[10.0] * half + [5.0] * half],
        index=["Free Cash Flow"], columns=dates,
    )
    balance = pd.DataFrame(
        [[80.0, 100.0], [20.0, 20.0]],
        index=["Total Debt", "Cash And Cash Equivalents"], columns=YEARS,
    )
    return income, cashflow, balance


def analyze(income, cashflow, balance, **kwargs):
    options = {"info": INFO, "symbol": "TEST", "as_of": "2026-03-01"}
    options.update(kwargs)
    return analyze_financial_recovery(income, cashflow, balance, **options)


class FinancialRecoveryAnalysisTests(unittest.TestCase):
    def test_complete_quarters_pass_both_gates_with_flat_json_evidence(self):
        result = analyze(*statements())
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertAlmostEqual(result["OperatingMarginLatest"], 0.2)
        self.assertAlmostEqual(result["OperatingMarginPrior"], 0.1)
        self.assertEqual(result["FreeCashFlowLatest"], 40)
        self.assertEqual(result["FreeCashFlowPrior"], 20)
        self.assertEqual(result["GrossDebtLatest"], 80)
        self.assertEqual(result["NetDebtLatest"], 60)
        self.assertEqual(result["FinancialPeriodEnd"], "2025-12-31")
        self.assertEqual(result["FinancialPriorPeriodEnd"], "2024-12-31")
        self.assertEqual(result["FinancialCurrency"], "USD")
        self.assertIn("four quarters", result["FinancialPeriodBasis"])
        self.assertIn("/TEST/financials/", result["FinancialIncomeSourceURL"])
        self.assertIn("/TEST/cash-flow/", result["FinancialCashFlowSourceURL"])
        self.assertIn("/TEST/balance-sheet/", result["FinancialBalanceSourceURL"])
        self.assertIn("do not prove cash-funded", result["DeleveragingReason"])
        for limitation in ("asset sales", "dilution", "maturities", "not verified"):
            self.assertIn(limitation, result["FinancialLimitations"])
        self.assertTrue(all(value is None or isinstance(value, (str, int, float, bool))
                            for value in result.values()))
        json.dumps(result, allow_nan=False)

    def test_shrinking_negative_burn_qualifies_only_for_profitability(self):
        income, cashflow, balance = statements()
        cashflow.loc["Free Cash Flow"] = [-2] * 4 + [-5] * 4
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Fail")
        self.assertEqual(result["FreeCashFlowLatest"], -8)

    def test_profitability_requires_both_strict_improvements(self):
        for operating, fcf in ((10, 10), (5, 10), (20, 5), (20, 1)):
            with self.subTest(operating=operating, fcf=fcf):
                income, cashflow, balance = statements()
                income.loc["Operating Income", QUARTERS[:4]] = operating
                cashflow.loc["Free Cash Flow", QUARTERS[:4]] = fcf
                self.assertEqual(analyze(income, cashflow, balance)["ProfitabilityStatus"], "Fail")

    def test_margin_is_ratio_of_sums_not_average_of_quarterly_margins(self):
        income, cashflow, balance = statements()
        income.loc["Total Revenue"] = [1000, 1, 1, 1] + [100] * 4
        income.loc["Operating Income"] = [0, 1, 1, 1] + [10] * 4
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["ProfitabilityStatus"], "Fail")
        self.assertAlmostEqual(result["OperatingMarginLatest"], 3 / 1003)

    def test_negative_operating_margin_can_improve(self):
        income, cashflow, balance = statements()
        income.loc["Operating Income"] = [-5] * 4 + [-10] * 4
        self.assertEqual(analyze(income, cashflow, balance)["ProfitabilityStatus"], "Pass")

    def test_signed_and_positive_magnitude_capex_are_subtracted(self):
        for capex in (-10, 10):
            with self.subTest(capex=capex):
                income, cashflow, balance = statements()
                cashflow = cashflow.drop(index="Free Cash Flow")
                cashflow.loc["Operating Cash Flow"] = [20] * 4 + [15] * 4
                cashflow.loc["Capital Expenditure"] = capex
                result = analyze(income, cashflow, balance)
                self.assertEqual(result["FreeCashFlowLatest"], 40)
                self.assertEqual(result["FreeCashFlowPrior"], 20)
                self.assertIn("minus absolute", result["FreeCashFlowBasis"])
                self.assertEqual(result["ProfitabilityStatus"], "Pass")

    def test_reported_fcf_takes_precedence_over_derived_fcf(self):
        income, cashflow, balance = statements()
        cashflow.loc["Operating Cash Flow"] = 100
        cashflow.loc["Capital Expenditure"] = -200
        self.assertEqual(analyze(income, cashflow, balance)["FreeCashFlowLatest"], 40)

    def test_incomplete_reported_fcf_uses_consistent_derived_basis(self):
        income, cashflow, balance = statements()
        cashflow.loc["Free Cash Flow", QUARTERS[0]] = None
        cashflow.loc["Operating Cash Flow"] = [30] * 4 + [20] * 4
        cashflow.loc["Capital Expenditure"] = -10
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["FreeCashFlowLatest"], 80)
        self.assertEqual(result["FreeCashFlowPrior"], 40)

    def test_missing_capex_does_not_become_zero(self):
        income, cashflow, balance = statements()
        cashflow = cashflow.rename(index={"Free Cash Flow": "Operating Cash Flow"})
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        self.assertIsNone(result["FreeCashFlowLatest"])

    def test_five_quarters_use_explicit_fiscal_year_profitability_fallback(self):
        income, cashflow, balance = statements()
        annual_income, annual_cashflow, annual_balance = statements(annual=True)
        result = analyze(
            income.iloc[:, :5], cashflow.iloc[:, :5], balance,
            annual_income=annual_income, annual_cashflow=annual_cashflow,
            annual_balance=annual_balance,
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["FinancialPeriodBasis"], "Fiscal year vs prior fiscal year (fallback)")
        self.assertEqual(result["FreeCashFlowLatest"], 10)
        self.assertIn("Need 8", result["FinancialFallbackReason"])
        self.assertIn("fiscal-year", result["ProfitabilityReason"].lower())
        self.assertIn("four-quarter", result["FinancialDebtPeriodBasis"])
        self.assertEqual(result["FreeCashFlowDeleveragingLatest"], 40)
        self.assertIsNone(result["FinancialLatestQuarterEnds"])

    def test_missing_latest_quarter_uses_annual_not_older_eight(self):
        income, cashflow, balance = statements()
        extra_date = pd.Timestamp("2023-12-31")
        income[extra_date] = [100, 5]
        cashflow[extra_date] = 1
        income.loc["Operating Income", QUARTERS[0]] = None
        annual_income, annual_cashflow, annual_balance = statements(annual=True)
        result = analyze(
            income, cashflow, balance, annual_income=annual_income,
            annual_cashflow=annual_cashflow, annual_balance=annual_balance,
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertIn("Fiscal year", result["FinancialPeriodBasis"])
        self.assertEqual(result["FreeCashFlowLatest"], 10)

    def test_incomplete_quarters_and_no_annual_are_unknown(self):
        income, cashflow, balance = statements()
        result = analyze(income.iloc[:, :5], cashflow.iloc[:, :5], balance)
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertIn("fallback unavailable", result["ProfitabilityReason"])

    def test_annual_only_fallback_passes(self):
        income, cashflow, balance = statements(annual=True)
        result = analyze(
            None, None, None, annual_income=income,
            annual_cashflow=cashflow, annual_balance=balance,
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertIn("Fiscal year", result["FinancialDebtPeriodBasis"])
        self.assertEqual(result["FreeCashFlowDeleveragingLatest"], 10)

    def test_quarterly_gaps_and_non_year_ago_annual_periods_are_unknown(self):
        for quarterly in (True, False):
            with self.subTest(quarterly=quarterly):
                income, cashflow, balance = statements(annual=not quarterly)
                old = QUARTERS[3] if quarterly else YEARS[1]
                replacement = pd.Timestamp("2025-02-01") if quarterly else pd.Timestamp("2023-12-31")
                income = income.rename(columns={old: replacement})
                cashflow = cashflow.rename(columns={old: replacement})
                if quarterly:
                    result = analyze(income, cashflow, balance)
                else:
                    result = analyze(
                        None, None, None, annual_income=income,
                        annual_cashflow=cashflow, annual_balance=balance,
                    )
                self.assertEqual(result["ProfitabilityStatus"], "Unknown")

    def test_mismatched_latest_income_cashflow_dates_do_not_use_older_data(self):
        income, cashflow, balance = statements()
        income[pd.Timestamp("2026-03-31")] = [100, 30]
        result = analyze(income, cashflow, balance, as_of="2026-04-30")
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")

    def test_latest_cash_and_debt_must_share_dates(self):
        income, cashflow, balance = statements()
        balance = balance.rename(columns={YEARS[0]: pd.Timestamp("2025-09-30")})
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        self.assertIn("do not match", result["DeleveragingReason"])

    def test_year_ago_balance_does_not_mean_arbitrary_old_snapshot(self):
        for prior in ("2024-09-30", "2023-12-31", "2025-01-10"):
            with self.subTest(prior=prior):
                income, cashflow, balance = statements()
                balance = balance.rename(columns={YEARS[1]: pd.Timestamp(prior)})
                self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")

    def test_seven_day_fiscal_calendar_drift_allowed_but_eight_not(self):
        for days, expected in ((7, "Pass"), (8, "Unknown")):
            with self.subTest(days=days):
                income, cashflow, balance = statements()
                balance = balance.rename(columns={YEARS[1]: YEARS[1] + pd.Timedelta(days=days)})
                self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], expected)

    def test_gross_and_net_debt_must_both_decline(self):
        for gross, cash in ((110, 100), (100, 40), (80, 0)):
            with self.subTest(gross=gross, cash=cash):
                income, cashflow, balance = statements()
                balance.loc["Total Debt", YEARS[0]] = gross
                balance.loc["Cash And Cash Equivalents", YEARS[0]] = cash
                self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Fail")

    def test_zero_and_negative_fcf_fail_deleveraging(self):
        for value in (0, -1):
            with self.subTest(value=value):
                income, cashflow, balance = statements()
                cashflow.loc["Free Cash Flow", QUARTERS[:4]] = value
                self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Fail")

    def test_known_zero_debt_is_not_missing_and_negative_net_debt_is_valid(self):
        income, cashflow, balance = statements()
        balance.loc["Total Debt", YEARS[0]] = 0
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertEqual(result["GrossDebtLatest"], 0)
        self.assertEqual(result["NetDebtLatest"], -20)
        balance.loc["Total Debt", YEARS[1]] = 0
        self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Fail")

    def test_missing_debt_and_cash_are_unknown_not_zero(self):
        for row in ("Total Debt", "Cash And Cash Equivalents"):
            with self.subTest(row=row):
                income, cashflow, balance = statements()
                balance.loc[row, YEARS[0]] = None
                result = analyze(income, cashflow, balance)
                self.assertEqual(result["DeleveragingStatus"], "Unknown")
                self.assertIsNone(result["GrossDebtLatest"])

    def test_all_debt_components_required_with_consistent_definition(self):
        income, cashflow, balance = statements()
        balance = balance.drop(index="Total Debt")
        balance.loc["Current Debt"] = [0, 0]
        balance.loc["Long Term Debt"] = [80, 100]
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertIn("Current Debt + Long Term Debt", result["GrossDebtBasis"])
        balance.loc["Current Debt", YEARS[0]] = None
        self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")

    def test_does_not_mix_reported_total_and_partial_components_between_years(self):
        income, cashflow, balance = statements()
        balance.loc["Total Debt", YEARS[0]] = None
        balance.loc["Current Debt"] = [0, None]
        balance.loc["Long Term Debt"] = [80, None]
        self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")

    def test_capital_lease_debt_components_are_kept_on_a_common_basis(self):
        income, cashflow, balance = statements()
        balance = balance.drop(index="Total Debt")
        balance.loc["Current Debt And Capital Lease Obligation"] = [10, 20]
        balance.loc["Long Term Debt And Capital Lease Obligation"] = [70, 80]
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertEqual(result["GrossDebtLatest"], 80)
        self.assertIn("Capital Lease", result["GrossDebtBasis"])

    def test_short_term_investments_do_not_substitute_for_cash_equivalents(self):
        income, cashflow, balance = statements()
        balance = balance.rename(
            index={"Cash And Cash Equivalents": "Cash Cash Equivalents And Short Term Investments"}
        )
        self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")

    def test_negative_nonfinite_or_duplicate_balance_values_are_unknown(self):
        for value in (-1, float("inf"), float("nan")):
            with self.subTest(value=value):
                income, cashflow, balance = statements()
                balance.loc["Total Debt", YEARS[0]] = value
                self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")
        income, cashflow, balance = statements()
        balance = pd.concat([balance, balance.iloc[:, :1]], axis=1)
        self.assertEqual(analyze(income, cashflow, balance)["DeleveragingStatus"], "Unknown")

    def test_ebitda_does_not_substitute_for_operating_income_or_debt(self):
        income, cashflow, balance = statements()
        income = income.rename(index={"Operating Income": "EBITDA"})
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertEqual(analyze(income, cashflow, None)["DeleveragingStatus"], "Unknown")

    def test_unsuitable_financials_and_reits_are_not_applicable(self):
        for info in (
            {"sector": "Financial Services"},
            {"sector": "Financials"},
            {"sector": "Real Estate", "industry": "REIT - Industrial"},
            {"sector": "Real Estate", "industry": "Real Estate Investment Trust"},
            {"industry": "Banks - Regional"},
            {"industry": "Insurance - Life"},
        ):
            with self.subTest(info=info):
                result = analyze(None, None, None, info=info)
                self.assertEqual(result["ProfitabilityStatus"], "Not applicable")
                self.assertEqual(result["DeleveragingStatus"], "Not applicable")

    def test_real_estate_developer_is_not_automatically_a_reit(self):
        result = analyze(
            *statements(),
            info={"financialCurrency": "EUR", "sector": "Real Estate", "industry": "Real Estate - Development"},
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")

    def test_non_equity_quote_types_are_not_applicable_even_with_company_data(self):
        for quote_type in ("ETF", "MUTUALFUND", "INDEX", "CRYPTOCURRENCY", " etf "):
            with self.subTest(quote_type=quote_type):
                result = analyze(*statements(), info={**INFO, "quoteType": quote_type})
                self.assertEqual(result["ProfitabilityStatus"], "Not applicable")
                self.assertEqual(result["DeleveragingStatus"], "Not applicable")
                self.assertIn(quote_type.strip().upper(), result["ProfitabilityReason"])
                self.assertIn("quoteType", result["DeleveragingReason"])
                self.assertIsNone(result["OperatingMarginLatest"])
                self.assertIsNone(result["GrossDebtLatest"])

    def test_equity_and_missing_quote_types_allow_company_analysis(self):
        for quote_type in ("EQUITY", " equity ", None, ""):
            with self.subTest(quote_type=quote_type):
                result = analyze(*statements(), info={**INFO, "quoteType": quote_type})
                self.assertEqual(result["ProfitabilityStatus"], "Pass")
                self.assertEqual(result["DeleveragingStatus"], "Pass")

    def test_unknown_currency_or_classification_prevents_qualification(self):
        for info in (
            {"currency": "USD", "sector": "Industrials"},
            {"financialCurrency": "USD"},
            {},
        ):
            with self.subTest(info=info):
                result = analyze(*statements(), info=info)
                self.assertEqual(result["ProfitabilityStatus"], "Unknown")
                self.assertEqual(result["DeleveragingStatus"], "Unknown")

    def test_reporting_currency_is_used_not_listing_currency(self):
        result = analyze(*statements(), info={**INFO, "financialCurrency": "EUR", "currency": "USD"})
        self.assertEqual(result["FinancialCurrency"], "EUR")
        self.assertIn("EUR", result["ProfitabilityReason"])

    def test_quarterly_staleness_boundary_and_future_dates(self):
        for days, expected in ((0, "Pass"), (200, "Pass"), (201, "Unknown"), (-1, "Unknown")):
            with self.subTest(days=days):
                result = analyze(*statements(), as_of=YEARS[0] + pd.Timedelta(days=days))
                self.assertEqual(result["ProfitabilityStatus"], expected)
                self.assertEqual(result["DeleveragingStatus"], expected)
                self.assertEqual(result["FinancialStatementAgeDays"], days)

    def test_annual_staleness_boundary_and_future_dates(self):
        income, cashflow, balance = statements(annual=True)
        for days, expected in ((550, "Pass"), (551, "Unknown"), (-1, "Unknown")):
            with self.subTest(days=days):
                result = analyze(
                    None, None, None, annual_income=income, annual_cashflow=cashflow,
                    annual_balance=balance, as_of=YEARS[0] + pd.Timedelta(days=days),
                )
                self.assertEqual(result["ProfitabilityStatus"], expected)
                self.assertEqual(result["DeleveragingStatus"], expected)

    def test_complete_but_stale_quarters_do_not_hide_behind_annual_fallback(self):
        annual_income, annual_cashflow, annual_balance = statements(annual=True)
        result = analyze(
            *statements(), annual_income=annual_income, annual_cashflow=annual_cashflow,
            annual_balance=annual_balance, as_of="2026-08-01",
        )
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        self.assertIn("stale", result["ProfitabilityReason"])
        self.assertIn("four quarters", result["FinancialPeriodBasis"])

    def test_unsorted_columns_and_timezone_aware_as_of_are_supported(self):
        income, cashflow, balance = statements()
        result = analyze(
            income.iloc[:, ::-1], cashflow.iloc[:, ::-1], balance.iloc[:, ::-1],
            as_of=pd.Timestamp("2026-03-01", tz="Europe/Prague"),
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Pass")

    def test_duplicates_invalid_dates_nan_and_infinity_do_not_pass(self):
        for kind in ("duplicate_date", "duplicate_row", "nan", "inf", "bad_date", "zero_revenue"):
            with self.subTest(kind=kind):
                income, cashflow, balance = statements()
                if kind == "duplicate_date":
                    income = pd.concat([income, income.iloc[:, :1]], axis=1)
                elif kind == "duplicate_row":
                    income = pd.concat([income, income.loc[["Operating Income"]]])
                elif kind == "nan":
                    income.loc["Operating Income", QUARTERS[0]] = float("nan")
                elif kind == "inf":
                    income.loc["Operating Income", QUARTERS[0]] = float("inf")
                elif kind == "bad_date":
                    income = income.rename(columns={QUARTERS[0]: "TTM"})
                else:
                    income.loc["Total Revenue"] = 0
                result = analyze(income, cashflow, balance)
                self.assertEqual(result["ProfitabilityStatus"], "Unknown")
                json.dumps(result, allow_nan=False)

    def test_empty_statements_are_unknown_and_json_safe(self):
        result = analyze(None, pd.DataFrame(), None)
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        json.dumps(result, allow_nan=False)

    def test_overflowing_changes_are_json_safe_not_infinite(self):
        income, cashflow, balance = statements(annual=True)
        cashflow.loc["Free Cash Flow"] = [1e308, -1e308]
        balance.loc["Total Debt"] = [0, 1e308]
        balance.loc["Cash And Cash Equivalents"] = [1e308, 0]
        result = analyze(
            None, None, None, annual_income=income,
            annual_cashflow=cashflow, annual_balance=balance,
        )
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Pass")
        self.assertIsNone(result["FreeCashFlowChange"])
        self.assertIsNone(result["NetDebtChange"])
        json.dumps(result, allow_nan=False)

    def test_overflowing_flow_totals_cannot_pass(self):
        income, cashflow, balance = statements()
        cashflow.loc["Free Cash Flow"] = 1e308
        result = analyze(income, cashflow, balance)
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")
        json.dumps(result, allow_nan=False)

    def test_invalid_as_of_and_wrong_frame_types_are_not_silently_swallowed(self):
        with self.assertRaises(ValueError):
            analyze(*statements(), as_of="not a date")
        with self.assertRaises(TypeError):
            analyze({}, None, None)

    def test_analysis_does_not_mutate_input_frames(self):
        frames = statements()
        originals = tuple(frame.copy(deep=True) for frame in frames)
        analyze(*frames)
        for actual, expected in zip(frames, originals):
            pd.testing.assert_frame_equal(actual, expected)


class FinancialRecoveryFetchingTests(unittest.TestCase):
    @patch("recovery_financials.get_company_info")
    @patch("stock_data.yf.Ticker")
    def test_supplied_cached_metadata_avoids_metadata_fetch(self, ticker_type, get_info):
        ticker = ticker_type.return_value
        ticker.quarterly_income_stmt, ticker.quarterly_cashflow, ticker.quarterly_balance_sheet = statements()
        with patch("recovery_financials._date", return_value=pd.Timestamp("2026-03-01")):
            result = get_financial_recovery(" test ", info={**INFO, "quoteType": "EQUITY"})
        get_info.assert_not_called()
        self.assertEqual(ticker_type.call_count, 3)
        self.assertTrue(all(call.args == ("TEST",) for call in ticker_type.call_args_list))
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["FinancialQuoteType"], "EQUITY")

    @patch("recovery_financials.get_company_info")
    @patch("stock_data.yf.Ticker")
    def test_supplied_empty_metadata_is_not_refetched(self, ticker_type, get_info):
        ticker = ticker_type.return_value
        ticker.quarterly_income_stmt, ticker.quarterly_cashflow, ticker.quarterly_balance_sheet = statements()
        result = get_financial_recovery("TEST", info={})
        get_info.assert_not_called()
        self.assertEqual(result["ProfitabilityStatus"], "Unknown")
        self.assertEqual(result["DeleveragingStatus"], "Unknown")

    @patch("recovery_financials.get_company_info")
    @patch("stock_data.yf.Ticker")
    def test_non_equity_metadata_skips_statements_whether_supplied_or_fetched(self, ticker_type, get_info):
        for quote_type in ("ETF", "MUTUALFUND"):
            for supplied in (True, False):
                with self.subTest(quote_type=quote_type, supplied=supplied):
                    info = {"quoteType": quote_type}
                    get_info.reset_mock()
                    get_info.return_value = info
                    result = get_financial_recovery("FUND", info=info if supplied else None)
                    self.assertEqual(result["ProfitabilityStatus"], "Not applicable")
                    self.assertEqual(result["DeleveragingStatus"], "Not applicable")
                    self.assertEqual(result["FinancialQuoteType"], quote_type)
                    ticker_type.assert_not_called()
                    if supplied:
                        get_info.assert_not_called()
                    else:
                        get_info.assert_called_once_with("FUND")

    @patch("recovery_financials.get_company_info", return_value=INFO)
    @patch("stock_data.yf.Ticker")
    def test_fetches_quarters_and_annual_fallback_with_one_metadata_call(self, ticker_type, get_info):
        ticker = ticker_type.return_value
        income, cashflow, balance = statements()
        ticker.quarterly_income_stmt = income.iloc[:, :5]
        ticker.quarterly_cashflow = cashflow.iloc[:, :5]
        ticker.quarterly_balance_sheet = balance
        ticker.income_stmt, ticker.cashflow, ticker.balance_sheet = statements(annual=True)
        with patch("recovery_financials._date", return_value=pd.Timestamp("2026-03-01")):
            result = get_financial_recovery(" test ")
        get_info.assert_called_once_with("TEST")
        self.assertEqual(ticker_type.call_count, 5)
        self.assertTrue(all(call.args == ("TEST",) for call in ticker_type.call_args_list))
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertIn("Fiscal year", result["FinancialPeriodBasis"])

    @patch("recovery_financials.get_company_info", return_value=INFO)
    @patch("stock_data.yf.Ticker")
    def test_does_not_fetch_annual_when_complete_quarters_suffice(self, ticker_type, get_info):
        ticker = ticker_type.return_value
        ticker.quarterly_income_stmt, ticker.quarterly_cashflow, ticker.quarterly_balance_sheet = statements()
        annual = PropertyMock(side_effect=AssertionError("Annual fetch must not happen"))
        type(ticker).income_stmt = annual
        type(ticker).cashflow = annual
        type(ticker).balance_sheet = annual
        with patch("recovery_financials._date", return_value=pd.Timestamp("2026-03-01")):
            result = get_financial_recovery("TEST")
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        annual.assert_not_called()
        get_info.assert_called_once()

    @patch("recovery_financials.get_company_info", return_value={"sector": "Financial Services"})
    @patch("stock_data.yf.Ticker")
    def test_unsuitable_sector_does_not_fetch_statements(self, ticker_type, get_info):
        result = get_financial_recovery("BANK")
        self.assertEqual(result["ProfitabilityStatus"], "Not applicable")
        ticker_type.assert_not_called()
        get_info.assert_called_once_with("BANK")

    @patch("recovery_financials.get_company_info", return_value=INFO)
    @patch("stock_data.yf.Ticker")
    def test_expected_yahoo_and_network_errors_are_wrapped(self, ticker_type, get_info):
        for error in (Timeout("timed out"), YFException("provider failed")):
            with self.subTest(error=error):
                ticker_type.side_effect = error
                with self.assertRaises(StockDataError) as caught:
                    get_financial_recovery("TEST")
                self.assertIs(caught.exception.__cause__, error)

    @patch("recovery_financials.get_company_info", return_value=INFO)
    @patch("stock_data.yf.Ticker")
    def test_expected_errors_from_annual_statement_fetch_are_wrapped(self, ticker_type, get_info):
        ticker = ticker_type.return_value
        ticker.quarterly_income_stmt = pd.DataFrame()
        ticker.quarterly_cashflow = pd.DataFrame()
        ticker.quarterly_balance_sheet = pd.DataFrame()
        error = Timeout("annual request timed out")
        type(ticker).income_stmt = PropertyMock(side_effect=error)
        with self.assertRaises(StockDataError) as caught:
            get_financial_recovery("TEST")
        self.assertIs(caught.exception.__cause__, error)

    @patch("recovery_financials.get_company_info", return_value=INFO)
    @patch("stock_data.yf.Ticker", side_effect=RuntimeError("programmer bug"))
    def test_unexpected_errors_are_not_caught(self, ticker_type, get_info):
        with self.assertRaisesRegex(RuntimeError, "programmer bug"):
            get_financial_recovery("TEST")

    @patch("recovery_financials.get_company_info", side_effect=StockDataError("metadata unavailable"))
    def test_metadata_error_remains_stock_data_error(self, get_info):
        with self.assertRaisesRegex(StockDataError, "metadata unavailable"):
            get_financial_recovery("TEST")

    @patch("recovery_financials.get_company_info")
    def test_blank_symbol_is_rejected_without_fetch(self, get_info):
        with self.assertRaises(ValueError):
            get_financial_recovery(" ")
        get_info.assert_not_called()


if __name__ == "__main__":
    unittest.main()
