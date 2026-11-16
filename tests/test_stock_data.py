from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import pandas as pd
from curl_cffi.requests.exceptions import Timeout

from stock_data import (
    StockDataError,
    analyze_fashion_downtrend,
    analyze_infrastructure_income,
    compact_number,
    company_screening_metrics,
    analyze_etf_inflection,
    extract_financial_history,
    extract_revenue_history,
    extract_share_count_history,
    extract_shareholder_yield,
    format_value,
    generate_revenue_acceleration_reasons,
    generate_stock_drivers,
    generate_cost_drivers,
    generate_stock_catalysts,
    get_business_context,
    get_company_info,
    get_price_history,
    get_revenue_growth_scan,
    key_metric_sections,
    normalize_etf_holdings,
    normalize_company_developments,
    normalize_european_holdings,
    normalize_insider_buys,
    normalize_russell_holdings,
    normalize_sp500_holdings,
    normalize_stock_catalyst_data,
    normalize_sec_quarterly_revenue,
    merge_quarterly_revenue_histories,
    prepare_price_history,
    revenue_growth_summary,
    rolling_revenue_growth_history,
    short_interest_rows,
    statement_revenue_growth_summary,
    summarize_fashion_signals,
    summarize_insider_buys,
    summarize_price_history,
    x_discussion_links,
)


class CompanyScreeningMetricsTests(unittest.TestCase):
    def test_float_is_fraction_of_outstanding_not_short_interest(self):
        result = company_screening_metrics({
            "floatShares": "2500000", "sharesOutstanding": 10_000_000,
            "shortPercentOfFloat": 0.8, "trailingPE": "12.5", "enterpriseToRevenue": 4.5,
        })
        self.assertEqual(result["FloatShares"], 2_500_000)
        self.assertEqual(result["SharesOutstanding"], 10_000_000)
        self.assertEqual(result["FloatPercentOfSharesOutstanding"], 0.25)
        self.assertEqual(result["ShortPercentOfFloat"], 0.8)
        self.assertEqual(result["TrailingPE"], 12.5)
        self.assertEqual(result["EnterpriseToRevenue"], 4.5)
        self.assertIn("floatShares / sharesOutstanding", result["FloatDataReason"])
        self.assertIn("Yahoo Finance", result["CompanyMetricSource"])

    def test_missing_nonpositive_or_inconsistent_share_counts_are_unknown(self):
        for floating, outstanding in (
            (None, 100), (10, None), (0, 100), (10, 0), (-10, 100),
            (10, -100), (101, 100), (float("inf"), 100), (10, float("nan")),
        ):
            with self.subTest(floating=floating, outstanding=outstanding):
                result = company_screening_metrics({
                    "floatShares": floating, "sharesOutstanding": outstanding,
                    "heldPercentInsiders": 0.01,
                })
                self.assertTrue(pd.isna(result["FloatPercentOfSharesOutstanding"]))
                self.assertIn("Unavailable", result["FloatDataReason"])
        self.assertEqual(
            company_screening_metrics({"floatShares": 100, "sharesOutstanding": 100})
            ["FloatPercentOfSharesOutstanding"], 1.0,
        )

    def test_invalid_scalar_and_nonscalar_values_do_not_become_numeric_signals(self):
        for value in (
            None, "bad", "NaN", "inf", float("inf"), -float("inf"), float("nan"),
            True, False, complex(2, 1), pd.NA, pd.Timestamp("2026-01-01"),
            pd.Timedelta(days=1), [10], {"value": 10}, 10 ** 400,
        ):
            with self.subTest(value=repr(value)):
                result = company_screening_metrics({
                    "floatShares": value, "sharesOutstanding": 100, "trailingPE": value,
                })
                self.assertTrue(pd.isna(result["FloatShares"]))
                self.assertTrue(pd.isna(result["FloatPercentOfSharesOutstanding"]))
                self.assertTrue(pd.isna(result["TrailingPE"]))

    def test_pe_preserves_zero_negative_and_small_positive_without_forward_fallback(self):
        for value in (0, -1, 0.000001, 1e12):
            self.assertEqual(company_screening_metrics({"trailingPE": value})["TrailingPE"], value)
        self.assertTrue(pd.isna(company_screening_metrics({"forwardPE": 15})["TrailingPE"]))


class StockDataFormattingTests(unittest.TestCase):
    def test_infrastructure_income_requires_yield_coverage_and_price_discount(self) -> None:
        history = pd.DataFrame({"Close": [100.0, 80.0]})

        result = analyze_infrastructure_income(
            {
                "dividendYield": 4.5,
                "payoutRatio": 0.70,
            },
            history,
        )

        self.assertTrue(result["Qualifies"])
        self.assertEqual(result["CoverageBasis"], "Earnings payout ratio")
        self.assertAlmostEqual(result["DistanceToFiveYearHigh"], -0.20)

    def test_fashion_signal_requires_two_independent_declining_sources(self) -> None:
        result = summarize_fashion_signals(
            {
                "Available": True,
                "Momentum": -0.30,
                "CurrentInterest": 14,
                "PreviousInterest": 20,
            },
            {"Available": False},
            {
                "Available": True,
                "Momentum": -0.50,
                "RecentCount": 3,
                "PreviousCount": 12,
            },
        )

        self.assertTrue(result["Qualifies"])
        self.assertEqual(result["SignalCount"], 2)
        self.assertEqual(result["DecliningSources"], "Google Trends, News")

    def test_fashion_signal_rejects_low_volume_declines(self) -> None:
        result = summarize_fashion_signals(
            {
                "Available": True,
                "Momentum": -0.50,
                "CurrentInterest": 4,
                "PreviousInterest": 8,
            },
            {
                "Available": True,
                "Momentum": -1.0,
                "RecentCount": 0,
                "PreviousCount": 2,
            },
            {
                "Available": True,
                "Momentum": -0.50,
                "RecentCount": 3,
                "PreviousCount": 12,
            },
        )

        self.assertFalse(result["Qualifies"])
        self.assertEqual(result["SignalCount"], 1)
        self.assertEqual(result["DecliningSources"], "News")

    def test_fashion_signal_rejects_accelerating_attention(self) -> None:
        result = summarize_fashion_signals(
            {
                "Available": True,
                "Momentum": 0.30,
                "CurrentInterest": 26,
                "PreviousInterest": 20,
            },
            {
                "Available": True,
                "Momentum": 0.50,
                "RecentCount": 9,
                "PreviousCount": 12,
            },
            {
                "Available": True,
                "Momentum": 0.50,
                "RecentCount": 9,
                "PreviousCount": 12,
            },
        )

        self.assertFalse(result["Qualifies"])
        self.assertEqual(result["SignalCount"], 0)

    def test_fashion_downtrend_requires_close_and_ma50_below_ma200(self) -> None:
        result = analyze_fashion_downtrend(
            pd.DataFrame({"Close": [100.0] * 150 + [80.0] * 50})
        )

        self.assertTrue(result["BelowMA200"])
        self.assertTrue(result["MA50BelowMA200"])
        self.assertTrue(result["DowntrendQualifies"])
        self.assertAlmostEqual(result["LatestClose"], 80.0)
        self.assertAlmostEqual(result["MA50"], 80.0)
        self.assertAlmostEqual(result["MA200"], 95.0)

    def test_fashion_downtrend_rejects_close_below_ma200_without_bearish_alignment(
        self,
    ) -> None:
        result = analyze_fashion_downtrend(
            pd.DataFrame({"Close": [100.0] * 150 + [120.0] * 49 + [90.0]})
        )

        self.assertTrue(result["BelowMA200"])
        self.assertFalse(result["MA50BelowMA200"])
        self.assertFalse(result["DowntrendQualifies"])

    def test_fashion_downtrend_requires_200_closes(self) -> None:
        with self.assertRaisesRegex(StockDataError, "at least 200"):
            analyze_fashion_downtrend(pd.DataFrame({"Close": [100.0] * 199}))

    def test_compact_number_formats_large_currency_value(self) -> None:
        self.assertEqual(compact_number(2_450_000_000, "USD"), "USD 2.45B")

    def test_format_value_keeps_zero_distinct_from_missing(self) -> None:
        self.assertEqual(format_value(0, "percent"), "0.00%")
        self.assertEqual(format_value(None, "percent"), "N/A")

    def test_format_value_converts_unix_date_as_utc(self) -> None:
        timestamp = datetime(2025, 1, 15, tzinfo=timezone.utc).timestamp()
        self.assertEqual(format_value(timestamp, "date"), "2025-01-15")

    def test_short_interest_rows_include_available_values_only(self) -> None:
        rows = short_interest_rows(
            {
                "sharesShort": 1_250_000,
                "shortPercentOfFloat": 0.034,
                "shortRatio": None,
            }
        )
        self.assertEqual(
            rows,
            [
                {"Metric": "Shares short", "Value": "1,250,000"},
                {"Metric": "Short % of float", "Value": "3.40%"},
            ],
        )

    def test_normalize_etf_holdings_preserves_symbols_and_weights(self) -> None:
        holdings = pd.DataFrame(
            {
                "Name": ["Alpha Inc", "Beta Corp"],
                "Holding Percent": [0.08125, 0.0475],
            },
            index=pd.Index(["ALPHA", "BETA"], name="Symbol"),
        )

        result = normalize_etf_holdings(holdings)

        self.assertEqual(result["Symbol"].tolist(), ["ALPHA", "BETA"])
        self.assertEqual(result["Name"].tolist(), ["Alpha Inc", "Beta Corp"])
        self.assertEqual(result["Weight"].tolist(), [0.08125, 0.0475])

    def test_normalize_etf_holdings_handles_unavailable_data(self) -> None:
        result = normalize_etf_holdings(pd.DataFrame())

        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), ["Symbol", "Name", "Weight"])

    def test_normalize_insider_buys_keeps_recent_open_market_purchases(self) -> None:
        transactions = pd.DataFrame(
            {
                "Start Date": ["2026-08-01", "2026-07-15", "2026-01-01"],
                "Text": [
                    "Purchase at price 12.50 per share.",
                    "Stock Gift at price 0.00 per share.",
                    "Purchase at price 8.00 per share.",
                ],
                "Insider": ["Buyer", "Recipient", "Old Buyer"],
                "Position": ["Director", "Officer", "Director"],
                "Shares": [1000, 500, 200],
                "Value": [12500, 0, 1600],
                "URL": ["https://example.com/filing", "", ""],
            }
        )

        result = normalize_insider_buys(
            transactions,
            as_of=pd.Timestamp("2026-08-19"),
        )

        self.assertEqual(result["Insider"].tolist(), ["Buyer"])
        self.assertEqual(result["Shares"].tolist(), [1000])
        self.assertEqual(result["Value"].tolist(), [12500])

    def test_revenue_acceleration_reason_requires_concrete_company_event(self) -> None:
        developments = pd.DataFrame(
            {
                "Date": pd.to_datetime(
                    ["2026-08-19", "2026-08-18", "2026-08-17"]
                ),
                "Title": [
                    "Moderna Announces Positive Phase 3 Trial Met Primary Endpoint",
                    "Former Moderna Executive Joins Another Biotechnology Company",
                    "Moderna Prepares for Multiple Product Launches",
                ],
                "Summary": [
                    "The Phase 3 study met its primary endpoint.",
                    "The executive will lead the other company.",
                    "Products are expected to reach the commercial market later.",
                ],
                "Provider": ["Business Wire", "PR Newswire", "ACCESS Newswire"],
                "URL": [
                    "https://example.com/trial",
                    "https://example.com/job",
                    "https://example.com/plans",
                ],
            }
        )

        result = generate_revenue_acceleration_reasons(
            {
                "symbol": "MRNA",
                "longName": "Moderna, Inc.",
                "sector": "Healthcare",
                "industry": "Biotechnology",
            },
            developments,
            as_of=pd.Timestamp("2026-08-20"),
        )

        self.assertEqual(len(result), 1)
        self.assertIn("pipeline", result[0]["Reason"].lower())
        self.assertEqual(result[0]["URL"], "https://example.com/trial")

    def test_revenue_acceleration_reason_detects_government_contract(self) -> None:
        developments = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-07-01"]),
                "Title": ["Acme Systems Awarded $500 Million U.S. Army Contract"],
                "Summary": ["The multi-year contract covers software delivery."],
                "Provider": ["Business Wire"],
                "URL": ["https://example.com/contract"],
            }
        )

        result = generate_revenue_acceleration_reasons(
            {
                "symbol": "ACME",
                "longName": "Acme Systems, Inc.",
                "sector": "Technology",
            },
            developments,
            as_of=pd.Timestamp("2026-08-20"),
        )

        self.assertEqual(len(result), 1)
        self.assertIn("contract", result[0]["Reason"].lower())

    def test_normalize_company_developments_handles_nested_news(self) -> None:
        result = normalize_company_developments(
            [
                {
                    "content": {
                        "title": "Acme Announces Contract",
                        "summary": "A customer agreement.",
                        "pubDate": "2026-08-19T10:00:00Z",
                        "provider": {"displayName": "Business Wire"},
                        "canonicalUrl": {"url": "https://example.com/acme"},
                    }
                }
            ]
        )

        self.assertEqual(result["Title"].tolist(), ["Acme Announces Contract"])
        self.assertEqual(result["Provider"].tolist(), ["Business Wire"])
        self.assertEqual(result["URL"].tolist(), ["https://example.com/acme"])

    def test_summarize_insider_buys_aggregates_transactions(self) -> None:
        buys = pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-08-01", "2026-07-01"]),
                "Shares": [1000.0, 250.0],
                "Value": [12500.0, 3000.0],
            }
        )

        result = summarize_insider_buys(buys)

        self.assertEqual(result["InsiderBuyCount"], 2)
        self.assertEqual(result["InsiderBuyShares"], 1250.0)
        self.assertEqual(result["InsiderBuyValue"], 15500.0)
        self.assertEqual(result["LatestInsiderBuy"], pd.Timestamp("2026-08-01"))

    def test_normalize_russell_holdings_filters_and_normalizes_equities(self) -> None:
        payload = {
            "componentsByNameMap": {
                "holdings": {
                    "containersByNameMap": {
                        "all": {
                            "dataPointsByNameMap": {
                                "ticker": {
                                    "value": ["BRKB", "BF B", "CASH", None]
                                },
                                "issueName": {
                                    "value": [
                                        "Berkshire",
                                        "Brown Forman",
                                        "Cash",
                                        "Missing",
                                    ]
                                },
                                "assetClass": {
                                    "value": ["Equity", "Equity", "Cash", "Equity"]
                                },
                                "exchange": {"value": ["NYSE", "NYSE", "-", "-"]},
                                "holdingPercent": {
                                    "value": [0.25, 0.15, 1.5, 0.0]
                                },
                                "asOfDate": {"value": "20260401"},
                            }
                        }
                    }
                }
            }
        }

        result = normalize_russell_holdings(payload)

        self.assertEqual(result["Symbol"].tolist(), ["BRK-B", "BF-B"])
        self.assertEqual(result["Name"].tolist(), ["Berkshire", "Brown Forman"])
        self.assertEqual(result["Weight"].tolist(), [0.0025, 0.0015])
        self.assertEqual(str(result.iloc[0]["AsOfDate"]), "2026-04-01")
        sp500_result = normalize_sp500_holdings(payload)
        self.assertEqual(sp500_result["Symbol"].tolist(), ["BRK-B", "BF-B"])

    def test_normalize_european_holdings_maps_local_exchange_symbols(self) -> None:
        holdings = pd.DataFrame(
            [
                {
                    "Ticker": "RR.",
                    "Name": "Rolls-Royce",
                    "Sector": "Industrials",
                    "Asset Class": "Equity",
                    "Weight (%)": "1.05",
                    "Location": "United Kingdom",
                    "Exchange": "London Stock Exchange",
                },
                {
                    "Ticker": "NOVO B",
                    "Name": "Novo Nordisk",
                    "Sector": "Health Care",
                    "Asset Class": "Equity",
                    "Weight (%)": "0.92",
                    "Location": "Denmark",
                    "Exchange": "Omx Nordic Exchange Copenhagen A/S",
                },
                {
                    "Ticker": "EUR",
                    "Name": "Euro cash",
                    "Sector": "Cash",
                    "Asset Class": "Cash",
                    "Weight (%)": "0.10",
                    "Location": "European Union",
                    "Exchange": "-",
                },
            ]
        )

        result = normalize_european_holdings(holdings, "Aug 24, 2026")

        self.assertEqual(result["Symbol"].tolist(), ["RR.L", "NOVO-B.CO"])
        self.assertEqual(result["Country"].tolist(), ["United Kingdom", "Denmark"])
        self.assertEqual(result["Weight"].tolist(), [0.0105, 0.0092])
        self.assertEqual(str(result.iloc[0]["AsOfDate"]), "2026-08-24")

    def test_revenue_growth_summary_labels_provider_period(self) -> None:
        result = revenue_growth_summary(
            {
                "revenueGrowth": 0.143,
                "mostRecentQuarter": 1_767_139_200,
                "totalRevenue": 500_000_000,
            }
        )

        self.assertEqual(result["RevenueGrowth"], 0.143)
        self.assertEqual(
            result["RevenuePeriod"],
            "Provider reference: 2025-12-31",
        )
        self.assertEqual(result["TotalRevenue"], 500_000_000)

    def test_statement_growth_uses_rolling_four_quarter_yoy(self) -> None:
        quarterly = pd.DataFrame(
            {
                "Period": pd.date_range("2024-03-31", periods=10, freq="QE"),
                "Revenue": [100, 100, 100, 100, 102, 104, 108, 114, 122, 132],
            }
        )
        annual = pd.DataFrame(
            {
                "Period": pd.to_datetime(["2024-12-31", "2025-12-31"]),
                "Revenue": [30.0, 24.0],
                "Growth": [pd.NA, -0.2],
            }
        )

        result = statement_revenue_growth_summary(quarterly, annual)

        self.assertAlmostEqual(result["RevenueGrowth"], 476 / 406 - 1)
        self.assertEqual(
            result["RevenuePeriod"],
            "Four quarters ended 2026-06-30 (YoY)",
        )
        self.assertEqual(result["TotalRevenue"], 476.0)
        self.assertTrue(result["RevenueAccelerating"])
        self.assertEqual(result["RevenueGrowthTrend"], "7.0% -> 11.4% -> 17.2%")
        chart_history = result["RevenueGrowthHistory"]
        self.assertEqual(len(chart_history), 3)
        self.assertEqual(chart_history[-1]["Period"], pd.Timestamp("2026-06-30"))
        self.assertEqual(chart_history[-1]["RevenueGrowth"], result["RevenueGrowth"])
        self.assertEqual(chart_history[-1]["RollingRevenue"], result["TotalRevenue"])

    def test_statement_growth_falls_back_to_latest_annual_yoy(self) -> None:
        quarterly = pd.DataFrame(
            {
                "Period": pd.to_datetime(["2026-03-31", "2026-06-30"]),
                "Revenue": [10.0, 12.0],
                "Growth": [pd.NA, 0.2],
            }
        )
        annual = pd.DataFrame(
            {
                "Period": pd.to_datetime(["2024-12-31", "2025-12-31"]),
                "Revenue": [20.0, 25.0],
                "Growth": [pd.NA, 0.25],
            }
        )

        result = statement_revenue_growth_summary(quarterly, annual)

        self.assertEqual(result["RevenueGrowth"], 0.25)
        self.assertEqual(
            result["RevenuePeriod"],
            "Fiscal year ended 2025-12-31 (YoY)",
        )
        self.assertEqual(result["TotalRevenue"], 25.0)
        self.assertFalse(result["RevenueAccelerating"])
        self.assertEqual(result["RevenueGrowthHistory"], [])

    def test_sec_revenue_uses_current_tag_not_largest_obsolete_series(self) -> None:
        def fact(start, end, value):
            return {"start": start, "end": end, "val": value, "form": "10-Q",
                    "fy": 2026, "fp": "Q2", "filed": "2026-08-01"}
        old = fact("2013-04-01", "2013-06-30", 10)
        current = fact("2026-04-01", "2026-06-30", 20)
        payload = {"facts": {"us-gaap": {
            "SalesRevenueNet": {"units": {"USD": [old] * 10}},
            "Revenues": {"units": {"USD": [current]}},
        }}}
        result = normalize_sec_quarterly_revenue(payload)
        self.assertEqual(result["Period"].tolist(), [pd.Timestamp("2026-06-30")])
        self.assertEqual(result["Revenue"].tolist(), [20.0])

    def test_sec_comparative_facts_use_actual_dates_and_latest_restatement(self) -> None:
        facts = [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 10,
             "filed": "2025-05-01", "fy": 2025},
            {"start": "2025-01-01", "end": "2025-03-31", "val": 11,
             "filed": "2026-05-01", "fy": 2026},
            {"start": "2026-01-01", "end": "2026-03-31", "val": 12,
             "filed": "2026-05-01", "fy": 2026},
        ]
        for fact in facts:
            fact.update({"form": "10-Q", "fp": "Q1"})
        result = normalize_sec_quarterly_revenue(
            {"facts": {"us-gaap": {"Revenues": {"units": {"USD": facts}}}}}
        )
        self.assertEqual(result["Revenue"].tolist(), [11.0, 12.0])
        self.assertEqual(result["Period"].dt.year.tolist(), [2025, 2026])

    def test_sec_fourth_quarter_uses_matching_actual_fiscal_year(self) -> None:
        facts = [
            {"start": "2024-07-01", "end": "2025-03-31", "val": 30},
            {"start": "2024-07-01", "end": "2025-06-30", "val": 45},
            {"start": "2025-07-01", "end": "2026-03-31", "val": 40},
            {"start": "2025-07-01", "end": "2026-06-30", "val": 60},
        ]
        for fact in facts:
            fact.update({"form": "10-K", "filed": "2026-08-01", "fy": 2026, "fp": "FY"})
        result = normalize_sec_quarterly_revenue(
            {"facts": {"us-gaap": {"Revenues": {"units": {"USD": facts}}}}}
        )
        self.assertEqual(result["Revenue"].tolist(), [15.0, 20.0])
        self.assertEqual(result["Period"].dt.year.tolist(), [2025, 2026])

    def test_sec_fourth_quarter_reconstruction_requires_contiguous_quarters(self) -> None:
        facts = [
            {"start": "2025-01-01", "end": "2025-03-31", "val": 10},
            {"start": "2025-04-01", "end": "2025-06-30", "val": 20},
            {"start": "2025-07-01", "end": "2025-09-30", "val": 30},
            {"start": "2025-01-01", "end": "2025-12-31", "val": 100},
        ]
        for fact in facts:
            fact.update({"form": "10-K", "filed": "2026-02-01", "fy": 2025, "fp": "FY"})
        payload = {"facts": {"us-gaap": {"Revenues": {"units": {"USD": facts}}}}}
        self.assertEqual(normalize_sec_quarterly_revenue(payload)["Revenue"].tolist(),
                         [10.0, 20.0, 30.0, 40.0])
        facts.pop(1)
        self.assertEqual(normalize_sec_quarterly_revenue(payload)["Revenue"].tolist(),
                         [10.0, 30.0])

    def test_merge_quarters_aligns_fiscal_weekends_without_double_counting(self) -> None:
        historical = pd.DataFrame({
            "Period": pd.to_datetime(["2025-03-30", "2025-06-29", "2025-09-28"]),
            "Revenue": [10.0, 20.0, 30.0],
        })
        recent = pd.DataFrame({
            "Period": pd.to_datetime(["2025-06-30", "2025-09-30"]),
            "Revenue": [21.0, 31.0],
        })
        result = merge_quarterly_revenue_histories(historical, recent)
        self.assertEqual(result["Revenue"].tolist(), [10.0, 21.0, 31.0])
        self.assertEqual(result["Period"].tolist(),
                         list(pd.to_datetime(["2025-03-30", "2025-06-30", "2025-09-30"])))

    def test_rolling_growth_does_not_bridge_years_of_missing_quarters(self) -> None:
        quarterly = pd.DataFrame({
            "Period": list(pd.date_range("2012-03-31", periods=8, freq="QE"))
                      + list(pd.date_range("2025-06-30", periods=5, freq="QE")),
            "Revenue": [10.0] * 8 + [20.0] * 5,
        })
        result = rolling_revenue_growth_history(quarterly)
        self.assertTrue(result["RevenueGrowth"].tail(5).isna().all())
        self.assertTrue(result["RollingRevenue"].iloc[8:11].isna().all())
        self.assertEqual(result["RollingRevenue"].iloc[-1], 80.0)
        summary = statement_revenue_growth_summary(quarterly, pd.DataFrame())
        self.assertIsNone(summary["RevenueGrowth"])
        self.assertFalse(summary["RevenueAccelerating"])

    def test_rolling_growth_rejects_one_missing_or_duplicate_quarter(self) -> None:
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-03-31", periods=10, freq="QE"),
            "Revenue": range(10, 20),
        })
        for frame in (
            quarterly.drop(index=5),
            pd.concat([quarterly, pd.DataFrame({
                "Period": [pd.Timestamp("2025-06-29")], "Revenue": [15],
            })], ignore_index=True),
        ):
            with self.subTest(periods=frame["Period"].tolist()):
                result = statement_revenue_growth_summary(frame, pd.DataFrame())
                self.assertIsNone(result["RevenueGrowth"])
                self.assertFalse(result["RevenueAccelerating"])

    def test_rolling_growth_requires_positive_prior_revenue(self) -> None:
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-03-31", periods=8, freq="QE"),
            "Revenue": [0.0] * 4 + [10.0] * 4,
        })
        result = statement_revenue_growth_summary(quarterly, pd.DataFrame())
        self.assertIsNone(result["RevenueGrowth"])

    def test_statement_growth_reports_unavailable_without_annual_data(self) -> None:
        for annual in (
            pd.DataFrame(),
            pd.DataFrame(columns=["Period", "Revenue", "Growth"]),
            pd.DataFrame({
                "Period": pd.to_datetime(["2025-12-31"]),
                "Revenue": [20.0],
                "Growth": [float("nan")],
            }),
        ):
            for quarterly in (
                pd.DataFrame(),
                pd.DataFrame({
                    "Period": pd.date_range("2025-03-31", periods=4, freq="QE"),
                    "Revenue": [10.0, 11.0, 12.0, 13.0],
                }),
            ):
                with self.subTest(annual=annual.shape, quarterly=quarterly.shape):
                    result = statement_revenue_growth_summary(quarterly, annual)
                    self.assertIsNone(result["RevenueGrowth"])
                    self.assertIsNone(result["TotalRevenue"])
                    self.assertFalse(result["RevenueAccelerating"])
                    self.assertEqual(result["RevenuePeriod"], "Statement growth unavailable")
                    self.assertEqual(result["RevenueGrowthTrend"], "Unavailable")

    def test_statement_growth_uses_quarters_without_annual_data(self) -> None:
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-03-31", periods=8, freq="QE"),
            "Revenue": [10.0] * 4 + [12.0] * 4,
        })
        result = statement_revenue_growth_summary(quarterly, pd.DataFrame())
        self.assertAlmostEqual(result["RevenueGrowth"], 0.2)
        self.assertEqual(result["TotalRevenue"], 48.0)

    @patch("stock_data.get_financial_history")
    @patch("stock_data.get_sec_quarterly_revenue")
    def test_revenue_scan_continues_after_unavailable_statements(
        self, sec_history, financial_history,
    ) -> None:
        sec_history.side_effect = StockDataError("SEC unavailable")
        financial_history.side_effect = [
            StockDataError("Quarterly unavailable"),
            StockDataError("Annual unavailable"),
            pd.DataFrame(),
            pd.DataFrame({
                "Period": pd.to_datetime(["2025-12-31"]),
                "Revenue": [25.0],
                "Growth": [0.25],
            }),
        ]

        result = get_revenue_growth_scan(["MISSING", "VALID"]).set_index("Symbol")

        self.assertTrue(pd.isna(result.loc["MISSING", "RevenueGrowth"]))
        self.assertEqual(result.loc["MISSING", "RevenuePeriod"], "Statement growth unavailable")
        self.assertFalse(result.loc["MISSING", "RevenueAccelerating"])
        self.assertEqual(result.loc["VALID", "RevenueGrowth"], 0.25)
        self.assertEqual(financial_history.call_count, 4)

    def test_extract_revenue_history_sorts_periods_and_calculates_growth(self) -> None:
        statement = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [120.0],
                pd.Timestamp("2023-12-31"): [100.0],
                pd.Timestamp("2022-12-31"): [80.0],
            },
            index=["Total Revenue"],
        )

        result = extract_revenue_history(statement)

        self.assertEqual(
            result["Period"].tolist(),
            [
                pd.Timestamp("2022-12-31"),
                pd.Timestamp("2023-12-31"),
                pd.Timestamp("2024-12-31"),
            ],
        )
        self.assertEqual(result["Revenue"].tolist(), [80.0, 100.0, 120.0])
        self.assertTrue(pd.isna(result["Growth"].iloc[0]))
        self.assertAlmostEqual(result["Growth"].iloc[1], 0.25)
        self.assertAlmostEqual(result["Growth"].iloc[2], 0.20)

    def test_extract_revenue_history_falls_back_to_operating_revenue(self) -> None:
        statement = pd.DataFrame(
            {pd.Timestamp("2024-03-31"): [50.0]},
            index=["Operating Revenue"],
        )

        result = extract_revenue_history(statement)

        self.assertEqual(result["Revenue"].tolist(), [50.0])

    def test_extract_revenue_history_handles_missing_revenue(self) -> None:
        statement = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [10.0]},
            index=["Net Income"],
        )

        result = extract_revenue_history(statement)

        self.assertTrue(result.empty)
        self.assertEqual(result.columns.tolist(), ["Period", "Revenue", "Growth"])

    def test_extract_financial_history_calculates_cost_percentage(self) -> None:
        statement = pd.DataFrame(
            {
                pd.Timestamp("2024-12-31"): [200.0, 80.0, 120.0],
                pd.Timestamp("2023-12-31"): [160.0, 72.0, 88.0],
            },
            index=["Total Revenue", "Cost Of Revenue", "Gross Profit"],
        )

        result = extract_financial_history(statement)

        self.assertEqual(result["CostOfRevenue"].tolist(), [72.0, 80.0])
        self.assertAlmostEqual(result["CostOfRevenuePercent"].iloc[0], 0.45)
        self.assertAlmostEqual(result["CostOfRevenuePercent"].iloc[1], 0.40)

    def test_extract_financial_history_rejects_unreconciled_cost(self) -> None:
        statement = pd.DataFrame(
            {pd.Timestamp("2024-12-31"): [200.0, 80.0, 100.0]},
            index=["Total Revenue", "Cost Of Revenue", "Gross Profit"],
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "Cost of revenue does not reconcile",
        ):
            extract_financial_history(statement)

    def test_extract_financial_history_preserves_reported_cost_credits(self) -> None:
        for cost_label in ("Cost Of Revenue", "Reconciled Cost Of Revenue"):
            with self.subTest(cost_label=cost_label):
                statement = pd.DataFrame(
                    {
                        pd.Timestamp("2025-06-30"): [1_031_000.0, 11_000.0, 1_020_000.0],
                        pd.Timestamp("2025-09-30"): [-65_000.0, -11_000.0, -54_000.0],
                        pd.Timestamp("2025-12-31"): [100_000.0, -5_000.0, 105_000.0],
                    },
                    index=["Total Revenue", cost_label, "Gross Profit"],
                )
                result = extract_financial_history(statement)
                self.assertEqual(result["Revenue"].tolist(), [1_031_000.0, -65_000.0, 100_000.0])
                self.assertEqual(result["CostOfRevenue"].tolist(), [11_000.0, -11_000.0, -5_000.0])
                self.assertAlmostEqual(result["CostOfRevenuePercent"].iloc[1], 11 / 65)
                self.assertAlmostEqual(result["CostOfRevenuePercent"].iloc[2], -0.05)

    def test_oabi_rolling_growth_is_positive_despite_negative_fiscal_year(self) -> None:
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-09-30", periods=8, freq="QE"),
            "Revenue": [4_172_000, 10_804_000, 4_154_000, 3_897_000,
                        2_239_000, 8_376_000, 14_427_000, 13_415_000],
        })
        annual = pd.DataFrame({
            "Period": pd.to_datetime(["2024-12-31", "2025-12-31"]),
            "Revenue": [26_391_000, 18_666_000],
            "Growth": [float("nan"), 18_666_000 / 26_391_000 - 1],
        })
        result = statement_revenue_growth_summary(quarterly, annual)
        self.assertLess(annual["Growth"].iloc[-1], 0)
        self.assertEqual(result["RevenueBasis"], "Rolling four quarters")
        self.assertEqual(result["TotalRevenue"], 38_457_000)
        self.assertEqual(result["PriorRollingRevenue"], 23_027_000)
        self.assertEqual(result["PriorRollingPeriod"], "2025-06-30")
        self.assertEqual(result["RevenuePeriod"], "Four quarters ended 2026-06-30 (YoY)")
        self.assertAlmostEqual(result["RevenueGrowth"], 0.6700829461067443)

    def test_key_metric_sections_omits_unavailable_values(self) -> None:
        sections = key_metric_sections(
            {
                "currency": "USD",
                "marketCap": 2_000_000_000,
                "enterpriseToRevenue": 4.125,
                "profitMargins": 0.125,
                "debtToEquity": 78.445,
                "forwardPE": None,
            }
        )

        self.assertEqual(
            sections["Valuation"],
            [
                {"Metric": "Market cap", "Value": "USD 2.00B"},
                {"Metric": "EV / Revenue", "Value": "4.13"},
            ],
        )
        self.assertEqual(
            sections["Profitability"],
            [{"Metric": "Profit margin", "Value": "12.50%"}],
        )
        self.assertIn(
            {"Metric": "Debt / equity", "Value": "78.45%"},
            sections["Financial health"],
        )

    def test_key_metric_sections_normalizes_dividend_yield_points(self) -> None:
        sections = key_metric_sections(
            {
                "dividendYield": 0.36,
                "payoutRatio": 0.1204,
            }
        )

        self.assertEqual(
            sections["Shareholder and trading"],
            [
                {"Metric": "Dividend yield (forward)", "Value": "0.36%"},
                {"Metric": "Payout ratio", "Value": "12.04%"},
            ],
        )

    def test_key_metrics_distinguish_statement_and_provider_growth(self) -> None:
        annual = pd.DataFrame(
            {
                "Period": [pd.Timestamp("2025-12-31")],
                "Growth": [0.148384],
            }
        )

        sections = key_metric_sections(
            {
                "revenueGrowth": 0.043,
                "mostRecentQuarter": datetime(
                    2026,
                    6,
                    30,
                    tzinfo=timezone.utc,
                ).timestamp(),
            },
            annual_financials=annual,
        )

        self.assertEqual(
            sections["Growth"],
            [
                {
                    "Metric": "Reported annual revenue growth (2025 vs. 2024)",
                    "Value": "14.84%",
                },
                {
                    "Metric": (
                        "Provider summary revenue growth "
                        "(provider reference: 2026-06-30)"
                    ),
                    "Value": "4.30%",
                },
            ],
        )

    def test_extract_shareholder_yield_combines_dividends_and_net_buybacks(self) -> None:
        cashflow = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): [-10.0, -30.0],
                pd.Timestamp("2025-09-30"): [-10.0, -20.0],
                pd.Timestamp("2025-06-30"): [-10.0, 5.0],
                pd.Timestamp("2025-03-31"): [-10.0, -15.0],
            },
            index=["Common Stock Dividend Paid", "Net Common Stock Issuance"],
        )

        result = extract_shareholder_yield(cashflow, 1_000.0, 4, "TTM")

        self.assertIsNotNone(result)
        self.assertEqual(result["Dividends"], 40.0)
        self.assertEqual(result["NetBuybacks"], 60.0)
        self.assertEqual(result["TotalReturned"], 100.0)
        self.assertAlmostEqual(result["ShareholderYield"], 0.10)

    def test_prepare_price_history_calculates_ma200_before_trimming(self) -> None:
        index = pd.date_range("2024-01-01", periods=260, freq="D")
        history = pd.DataFrame(
            {
                "Open": range(260),
                "High": range(260),
                "Low": range(260),
                "Close": range(1, 261),
                "Volume": [100] * 260,
            },
            index=index,
        )

        result = prepare_price_history(history, "1mo")

        self.assertLess(len(result), 260)
        self.assertTrue(result["MA200"].notna().all())
        self.assertAlmostEqual(result["MA200"].iloc[-1], 160.5)

    def test_get_price_history_falls_back_to_batch_download(self) -> None:
        index = pd.bdate_range("2024-01-01", periods=260)
        downloaded = pd.DataFrame(
            {
                ("Open", "TEST"): range(260),
                ("High", "TEST"): range(1, 261),
                ("Low", "TEST"): range(260),
                ("Close", "TEST"): range(1, 261),
                ("Volume", "TEST"): [100] * 260,
            },
            index=index,
        )

        with (
            patch("stock_data.yf.Ticker") as ticker,
            patch("stock_data.yf.download", return_value=downloaded) as download,
        ):
            ticker.return_value.history.return_value = pd.DataFrame()
            result = get_price_history("TEST", "1mo", "1d")

        download.assert_called_once()
        self.assertFalse(result.empty)
        self.assertEqual(result["Close"].iloc[-1], 260)

    def test_get_price_history_reports_when_both_endpoints_are_empty(self) -> None:
        with (
            patch("stock_data.yf.Ticker") as ticker,
            patch("stock_data.yf.download", return_value=pd.DataFrame()),
        ):
            ticker.return_value.history.return_value = pd.DataFrame()
            with self.assertRaisesRegex(StockDataError, "either Yahoo price endpoint"):
                get_price_history("TEST", "5y", "1d")

    def test_get_company_info_converts_transport_timeout(self) -> None:
        with patch("stock_data.yf.Ticker", side_effect=Timeout("timed out")):
            with self.assertRaisesRegex(
                StockDataError, "Company information for TEST could not be loaded"
            ):
                get_company_info("TEST")

    def test_summarize_price_history_calculates_etf_statistics(self) -> None:
        index = pd.date_range("2020-01-01", "2025-01-01", periods=253)
        history = pd.DataFrame(
            {
                "Close": [100 + (index * 0.5) for index in range(253)],
                "MA200": [None] * 199 + [150.0] * 54,
            },
            index=index,
        )

        result = summarize_price_history(history)

        self.assertAlmostEqual(result["TotalReturn"], 1.26)
        self.assertAlmostEqual(result["LatestClose"], 226.0)
        self.assertAlmostEqual(result["LatestMA200"], 150.0)
        self.assertLess(result["MaxDrawdown"], 0.001)

    def test_summarize_price_history_requires_two_numeric_closes(self) -> None:
        for closes in ([], [100.0], [None, None], ["unavailable", "100"]):
            with self.subTest(closes=closes):
                history = pd.DataFrame(
                    {"Close": closes}, index=pd.date_range("2026-09-01", periods=len(closes)),
                )
                with self.assertRaisesRegex(StockDataError, "At least two closing prices"):
                    summarize_price_history(history)

    def test_summarize_price_history_reports_missing_close_column(self) -> None:
        with self.assertRaisesRegex(StockDataError, "missing: Close"):
            summarize_price_history(pd.DataFrame())

    def test_summarize_price_history_allows_an_unavailable_ma200(self) -> None:
        for moving_average in ({}, {"MA200": [None, None]}):
            with self.subTest(moving_average=moving_average):
                history = pd.DataFrame(
                    {"Close": [100.0, 110.0], **moving_average},
                    index=pd.to_datetime(["2025-09-01", "2026-09-01"]),
                )
                result = summarize_price_history(history)
                self.assertAlmostEqual(result["TotalReturn"], 0.1)
                self.assertEqual(result["LatestClose"], 110.0)
                self.assertIsNone(result["LatestMA200"])
                self.assertIsNone(result["AnnualizedVolatility"])

    def test_analyze_etf_inflection_detects_recovery(self) -> None:
        index = pd.bdate_range("2023-01-01", periods=620)
        close = (
            [100.0] * 180
            + [100.0 - index * 0.5 for index in range(50)]
            + [75.0 + ((index % 20) - 10) * 0.1 for index in range(280)]
            + [76.0 + index * 0.12 for index in range(110)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        result = analyze_etf_inflection(history)

        self.assertIsNotNone(result)
        self.assertGreater(result["20DReturn"], 0)
        self.assertGreater(result["60DReturn"], 0)
        self.assertGreaterEqual(result["BaseSpan"], 180)
        self.assertGreater(result["ReboundFromLow"], 0.10)
        self.assertGreater(result["RecoveryProgress"], 0.08)
        self.assertGreaterEqual(result["HigherLow"], -0.03)
        self.assertLessEqual(result["PriorDecline"], -0.15)
        self.assertLessEqual(result["DistanceToPeak"], -0.10)

    def test_analyze_etf_inflection_rejects_persistent_decline(self) -> None:
        index = pd.bdate_range("2023-01-01", periods=620)
        history = pd.DataFrame(
            {"Close": [400.0 - index * 0.5 for index in range(620)]},
            index=index,
        )

        self.assertIsNone(analyze_etf_inflection(history))
        self.assertIsNone(analyze_etf_inflection(history, include_near_misses=True))

    def test_analyze_etf_inflection_allows_orderly_right_side_pullback(self) -> None:
        index = pd.bdate_range("2022-01-03", periods=800)
        close = (
            [100.0] * 120
            + [100.0 - step for step in range(80)]
            + [20.0 + (step % 20) * 0.2 for step in range(480)]
            + [24.0 + step * 0.26 for step in range(100)]
            + [50.0 - step * 0.1 for step in range(20)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        result = analyze_etf_inflection(history)

        self.assertIsNotNone(result)
        self.assertLess(result["20DReturn"], 0)
        self.assertGreater(result["60DReturn"], 0)
        self.assertEqual(result["Signal"], "Right side developing")

    def test_analyze_etf_inflection_allows_mild_sixty_day_pullback(self) -> None:
        index = pd.bdate_range("2022-01-03", periods=800)
        close = (
            [100.0] * 120
            + [100.0 - step for step in range(80)]
            + [20.0 + (step % 20) * 0.2 for step in range(480)]
            + [24.0 + step * 0.5 for step in range(40)]
            + [44.0 + step * 0.3 for step in range(20)]
            + [50.0]
            + [45.0 + step * (4.0 / 58) for step in range(59)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        result = analyze_etf_inflection(history)

        self.assertIsNotNone(result)
        self.assertGreaterEqual(result["60DReturn"], -0.03)
        self.assertLess(result["60DReturn"], 0)

    def test_analyze_etf_inflection_allows_recent_early_reversal(self) -> None:
        index = pd.bdate_range("2023-01-02", periods=900)
        close = (
            [100.0] * 100
            + [100.0 - step * 0.12 for step in range(600)]
            + [28.0 - step * 0.2 for step in range(90)]
            + [10.0 + step * 0.055 for step in range(110)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        result = analyze_etf_inflection(history)

        self.assertIsNotNone(result)
        self.assertLess(result["RecoveryProgress"], 0.08)
        self.assertLess(result["OneYearReturn"], 0)
        self.assertGreater(result["60DReturn"], 0.10)

    def test_analyze_etf_inflection_rejects_countertrend_rally(self) -> None:
        index = pd.bdate_range("2021-01-04", periods=900)
        close = (
            [100.0] * 100
            + [100.0 - step for step in range(80)]
            + [20.0 + (step % 20) * 0.2 for step in range(400)]
            + [20.0 + step * 0.2 for step in range(100)]
            + [40.0 - step * 0.09375 for step in range(160)]
            + [25.0 + step * 0.1167 for step in range(60)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        self.assertLess(close[-1] / close[-253] - 1, 0)
        self.assertIsNone(analyze_etf_inflection(history))
        self.assertIsNone(analyze_etf_inflection(history, include_near_misses=True))

    def test_analyze_etf_inflection_rejects_failed_late_recovery_cycle(self) -> None:
        index = pd.bdate_range("2021-01-04", periods=900)
        close = (
            [100.0] * 120
            + [100.0 - step * 0.4 for step in range(175)]
            + [30.0] * 160
            + [30.0 + step * 0.55 for step in range(100)]
            + [84.45 - step * 0.55 for step in range(100)]
            + [30.0] * 100
            + [30.0 + step * 0.25 for step in range(145)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        self.assertEqual(len(close), len(index))
        self.assertIsNone(analyze_etf_inflection(history))
        self.assertIsNone(analyze_etf_inflection(history, include_near_misses=True))

    def test_analyze_etf_inflection_rejects_completed_earlier_cycle(self) -> None:
        index = pd.bdate_range("2023-01-02", periods=900)
        close = (
            [100.0] * 100
            + [100.0 - step * 0.5 for step in range(70)]
            + [65.0 + step * 0.225 for step in range(200)]
            + [110.0 - step * 0.5 for step in range(100)]
            + [60.0 + (step % 20) * 0.05 for step in range(320)]
            + [61.0 + step * 0.22 for step in range(110)]
        )
        history = pd.DataFrame({"Close": close}, index=index)

        self.assertEqual(len(close), len(index))
        self.assertIsNone(analyze_etf_inflection(history))
        self.assertIsNone(analyze_etf_inflection(history, include_near_misses=True))

    def test_extract_shareholder_yield_requires_complete_periods(self) -> None:
        cashflow = pd.DataFrame(
            {pd.Timestamp("2025-12-31"): [-10.0, -20.0]},
            index=["Common Stock Dividend Paid", "Net Common Stock Issuance"],
        )

        self.assertIsNone(
            extract_shareholder_yield(cashflow, 1_000.0, 4, "TTM")
        )

    def test_extract_share_count_history_calculates_trend(self) -> None:
        statement = pd.DataFrame(
            {
                pd.Timestamp("2025-12-31"): [90.0],
                pd.Timestamp("2024-12-31"): [100.0],
            },
            index=["Ordinary Shares Number"],
        )

        result = extract_share_count_history(statement)

        self.assertEqual(result["Shares"].tolist(), [100.0, 90.0])
        self.assertTrue(pd.isna(result["Change"].iloc[0]))
        self.assertAlmostEqual(result["Change"].iloc[1], -0.10)

    def test_key_metrics_include_shareholder_yield_period(self) -> None:
        sections = key_metric_sections(
            {},
            {
                "Period": "TTM ending 2025-12-31",
                "ShareholderYield": 0.05,
            },
        )

        self.assertEqual(
            sections["Shareholder and trading"],
            [
                {
                    "Metric": "Shareholder yield (TTM ending 2025-12-31)",
                    "Value": "5.00%",
                }
            ],
        )

    def test_generate_stock_drivers_uses_business_context(self) -> None:
        annual = pd.DataFrame(
            {
                "Growth": [None, 0.10],
                "CostOfRevenuePercent": [0.60, 0.55],
            }
        )
        quarterly = pd.DataFrame(
            {
                "Revenue": [100.0, 105.0, 110.0, 115.0, 130.0],
                "Growth": [None, 0.05, 0.048, 0.045, 0.13],
            }
        )

        drivers = generate_stock_drivers(
            {
                "industry": "Consumer Electronics",
                "sector": "Technology",
                "country": "United States",
            },
            annual,
            quarterly,
            {
                "Industry": {
                    "Name": "Consumer Electronics",
                    "MedianYTDReturn": -0.08,
                    "YTDCompanyCount": 5,
                    "MedianGrowthEstimate": None,
                    "GrowthEstimateCount": 2,
                },
                "Benchmarks": [
                    {
                        "Ticker": "XLK",
                        "Label": "US technology sector",
                        "Return": 0.20,
                        "RelativeToGlobal": 0.05,
                    }
                ],
            },
        )

        tailwind_titles = {item["Title"] for item in drivers["Tailwinds"]}
        headwind_titles = {item["Title"] for item in drivers["Headwinds"]}
        self.assertIn("Installed-base monetization", tailwind_titles)
        self.assertIn("Large innovation and consumption base", tailwind_titles)
        self.assertIn("Revenue growth is accelerating", tailwind_titles)
        self.assertIn("US technology sector momentum", tailwind_titles)
        self.assertIn("Mature replacement cycles", headwind_titles)
        self.assertIn("Weak industry market breadth", headwind_titles)

    def test_generate_cost_drivers_identifies_airline_fuel_exposure(self) -> None:
        drivers = generate_cost_drivers(
            {"industry": "Airlines", "sector": "Industrials"}
        )

        self.assertEqual(
            [driver["Driver"] for driver in drivers],
            [
                "Jet fuel",
                "Labor",
                "Aircraft ownership and maintenance",
                "Airport, navigation, and distribution fees",
            ],
        )
        self.assertIn("hedging", drivers[0]["Monitor"])

    def test_generate_cost_drivers_uses_sector_fallback(self) -> None:
        drivers = generate_cost_drivers(
            {"industry": "Specialty Industrial Machinery", "sector": "Industrials"}
        )

        self.assertEqual(drivers[0]["Driver"], "Materials and components")
        self.assertTrue(all(driver["Monitor"] for driver in drivers))

    def test_business_context_handles_missing_industry_overview(self) -> None:
        class IndustryWithoutOverview:
            name = "Utilities - Regulated Water"
            overview = None
            top_performing_companies = None
            top_growth_companies = None

        with (
            patch(
                "stock_data.yf.Industry",
                return_value=IndustryWithoutOverview(),
            ),
            patch("stock_data._one_year_return", return_value=None),
        ):
            result = get_business_context(
                "utilities-regulated-water",
                None,
                None,
            )

        self.assertEqual(
            result["Industry"]["Name"],
            "Utilities - Regulated Water",
        )
        self.assertIsNone(result["Industry"]["CompanyCount"])
        self.assertEqual(result["Industry"]["YTDCompanyCount"], 0)
        self.assertEqual(result["Industry"]["GrowthEstimateCount"], 0)

    def test_normalize_stock_catalyst_data_handles_sparse_frames(self) -> None:
        result = normalize_stock_catalyst_data(
            {
                "Earnings Date": [
                    datetime(2026, 10, 20, tzinfo=timezone.utc),
                ],
                "Ex-Dividend Date": datetime(
                    2026,
                    8,
                    10,
                    tzinfo=timezone.utc,
                ),
            },
            pd.DataFrame({"growth": [0.12]}, index=["0q"]),
            pd.DataFrame({"growth": [0.08]}, index=["0q"]),
            pd.DataFrame(
                {"current": [2.0], "30daysAgo": [1.8]},
                index=["0q"],
            ),
            pd.DataFrame(
                {"upLast30days": [4], "downLast30days": [1]},
                index=["0q"],
            ),
            pd.DataFrame(),
        )

        self.assertEqual(len(result["Events"]), 2)
        self.assertEqual(result["Expectations"][0]["RevenueGrowth"], 0.08)
        self.assertEqual(result["Expectations"][0]["RevisionsUp30Days"], 4.0)

    def test_generate_stock_catalysts_uses_estimate_revisions(self) -> None:
        catalysts = generate_stock_catalysts(
            {},
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "Events": [],
                "Expectations": [
                    {
                        "Period": "Current quarter",
                        "RevenueGrowth": 0.10,
                        "EarningsGrowth": 0.12,
                        "EPSCurrent": 2.0,
                        "EPS30DaysAgo": 1.8,
                        "RevisionsUp30Days": 4.0,
                        "RevisionsDown30Days": 1.0,
                    }
                ],
                "RatingActions": [],
            },
        )

        titles = {row["Catalyst"] for row in catalysts}
        self.assertIn("Improving earnings expectations", titles)
        self.assertIn("Consensus revenue acceleration", titles)

    def test_x_discussion_links_encode_cashtag_and_company_name(self) -> None:
        links = x_discussion_links("aapl", "Apple Inc.")

        self.assertEqual(
            links["Latest cashtag posts"],
            "https://x.com/search?q=%24AAPL&src=typed_query&f=live",
        )
        self.assertEqual(
            links["Top cashtag posts"],
            "https://x.com/search?q=%24AAPL&src=typed_query&f=top",
        )
        self.assertEqual(
            links["Company mentions"],
            "https://x.com/search?q=%22Apple+Inc.%22+stock&src=typed_query&f=live",
        )


if __name__ == "__main__":
    unittest.main()
