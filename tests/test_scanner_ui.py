import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest


class ScannerScoreUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.cached_company_info = app.cached_info
        self.cached_revenue_per_stock = app.cached_stock_revenue_growth
        self.cached_shape_scan = app.cached_stock_inflection_scan
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        scan = pd.DataFrame({
            "Symbol": ["AAA", "BBB", "CCC"],
            "Score": [14, 14, 12],
            "Signal": ["Early right side", "Right side developing", "Early right side"],
            "AsOf": pd.to_datetime(["2026-09-06"] * 3),
            "MA200CrossDays": [5, 10, 15],
            "LowAge": [80, 90, 100],
            "BaseSpan": [150, 160, 170],
            "BaseDays": [60, 70, 80],
            "ShapeMatch": ["Strict U-shape"] * 3,
            "ShapeMissCount": [0] * 3,
            "ShapeMissedRules": ["None - all strict rules met."] * 3,
        })
        for column in (
            "20DReturn", "60DReturn", "OneYearReturn", "ReboundFromLow",
            "RecoveryProgress", "BestPriorRecovery", "RecoveryGiveback",
            "PriorDecline", "DistanceToPeak", "MA50Slope20D", "HigherLow", "VsMA50", "VsMA200",
        ):
            scan[column] = 0.1
        holdings = pd.DataFrame({
            "Symbol": ["AAA", "BBB", "CCC"],
            "Name": ["Company A", "Company B", "Company C"],
        })
        self.scan = scan
        self.holdings = holdings
        revenue = pd.DataFrame({
            "Symbol": ["AAA", "BBB", "CCC"],
            "RevenueGrowth": [0.2, -0.1, 0.3],
            "RevenueAccelerating": [True, False, True],
            "RevenueGrowthTrend": ["Increasing", "Decreasing", "Increasing"],
            "RevenuePeriod": ["Test period"] * 3,
        })
        self.revenue = revenue
        replacements = {
            "cached_russell_holdings": holdings,
            "cached_stock_inflection_scan": scan,
            "cached_history": pd.DataFrame(),
            "price_chart": go.Figure(),
            "render_company_news": None,
            "render_bookmark_button": None,
            "render_recovery_research": None,
            "render_revenue_outlook_research": None,
        }
        self.buyback_assessments = {
            symbol: {
                "BuybackStatus": "Pass" if symbol in ("AAA", "CCC") else "Fail",
                "NetBuybacks": 1_000_000.0 if symbol in ("AAA", "CCC") else -500_000.0,
                "BuybackCurrency": "USD", "BuybackPeriod": "TTM ending 2026-06-30",
                "BuybackPeriodBasis": "TTM", "BuybackPeriodEnd": "2026-06-30",
                "BuybackMethod": "Repurchases minus cash issuance.", "BuybackReason": "Cash-flow comparison.",
                "BuybackSourceURL": f"https://finance.yahoo.com/quote/{symbol}/cash-flow/",
            } for symbol in ("AAA", "BBB", "CCC")
        }
        self.buybacks = self.stack.enter_context(patch.object(
            app, "cached_net_buyback_assessment", side_effect=lambda symbol: self.buyback_assessments[symbol],
        ))
        for name, value in replacements.items():
            self.stack.enter_context(patch.object(app, name, return_value=value))
        self.stack.enter_context(patch.object(
            app, "cached_stock_revenue_growth",
            side_effect=lambda symbol, _: self.revenue.set_index("Symbol").loc[symbol].to_dict(),
        ))
        self.company_info = {
            symbol: {
                "shortPercentOfFloat": 0.2 if symbol in ("AAA", "BBB") else 0.05,
                "floatShares": {"AAA": 2_500_000, "BBB": 1_000_000, "CCC": 5_000_000}[symbol],
                "sharesOutstanding": 10_000_000,
                "trailingPE": {"AAA": 12.5, "BBB": -2.0, "CCC": 0.0}[symbol],
                "enterpriseToRevenue": 3.0,
            } for symbol in ("AAA", "BBB", "CCC")
        }
        self.stack.enter_context(patch.object(
            app, "cached_info", side_effect=lambda symbol: self.company_info[symbol],
        ))
        self.ui = AppTest.from_string(
            "from app import render_inflection_scanner\nrender_inflection_scanner()"
        ).run()

    def checkbox(self, label):
        return next(widget for widget in self.ui.checkbox if widget.label == label)

    def selectbox(self, label):
        return next(widget for widget in self.ui.selectbox if widget.label == label)

    def test_equal_scores_and_single_candidate_after_combining_filters(self):
        self.assertFalse(self.ui.exception)
        self.checkbox("High short interest (≥10% of float)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(len(self.ui.slider), 0)
        self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
        self.assertTrue(any("14/16" in item.value for item in self.ui.caption))

        self.checkbox("Positive rolling revenue growth").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.selectbox("Chart candidate").value, "AAA")
        self.assertEqual(len(self.selectbox("Chart candidate").options), 1)

        self.checkbox("High short interest (≥10% of float)").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.slider[0].min, 12)
        self.assertEqual(self.ui.slider[0].max, 14)
        self.assertEqual(len(self.selectbox("Chart candidate").options), 2)

    def test_score_slider_still_filters_mixed_scores(self):
        self.ui.slider[0].set_value(14).run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
        self.assertNotIn("CCC", self.ui.session_state["stock_research_queue"])

    def test_expected_growth_placeholder_is_disabled_and_does_not_filter_or_fetch(self):
        placeholder = self.ui.checkbox(key="expected_revenue_growth_placeholder")
        self.assertEqual(placeholder.label, "Expected positive revenue growth (placeholder)")
        self.assertTrue(placeholder.disabled)
        self.assertFalse(placeholder.value)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])
        self.app.cached_stock_revenue_growth.assert_not_called()

        self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])
        self.app.cached_stock_revenue_growth.assert_not_called()
        self.checkbox("Positive rolling revenue growth").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "CCC"])
        self.assertTrue(self.ui.checkbox(key="expected_revenue_growth_placeholder").disabled)
        self.assertFalse(self.ui.checkbox(key="expected_revenue_growth_placeholder").value)

    def test_signal_stage_still_filters_equal_scores(self):
        self.checkbox("High short interest (≥10% of float)").check().run()
        self.assertFalse(self.ui.exception)
        self.selectbox("Signal stage").select("Right side developing").run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.selectbox("Chart candidate").value, "BBB")
        self.assertEqual(len(self.selectbox("Chart candidate").options), 1)

    def test_net_buyback_filter_is_optional_and_independent_from_insiders_and_dividends(self):
        self.assertFalse(self.ui.checkbox(key="require_net_buybacks").value)
        self.buybacks.assert_not_called()
        with patch.object(self.app, "load_recovery_signals") as recovery:
            self.ui.checkbox(key="require_net_buybacks").check().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "CCC"])
            recovery.assert_not_called()
        table = next(item.value for item in self.ui.dataframe if "Score" in item.value)
        self.assertEqual(table["Net buybacks"].tolist(), ["1,000,000.00"] * 2)
        self.assertEqual(table["Buyback currency"].tolist(), ["USD"] * 2)
        self.assertEqual(table["Buyback period"].tolist(), ["TTM ending 2026-06-30"] * 2)
        self.assertTrue(any(metric.label == "Net buybacks" and metric.value == "USD 1.00M" for metric in self.ui.metric))
        self.assertFalse(self.checkbox("Open-market insider buys").value)
        self.ui.checkbox(key="require_net_buybacks").uncheck().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])

    def test_buybacks_combine_with_other_filters_and_preserve_near_only_handoff(self):
        self.mixed_shapes()
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.ui.checkbox(key="require_net_buybacks").check().run()
        self.checkbox("Positive rolling revenue growth").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["CCC"])
        next(button for button in self.ui.button if button.label == "Open in Individual Stocks").click().run()
        self.assertEqual(self.ui.session_state["stock_query"], "CCC")
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["CCC"])
        self.checkbox("High short interest (≥10% of float)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_buyback_unknowns_and_failures_stay_in_audit_without_results(self):
        for symbol in self.buyback_assessments:
            self.buyback_assessments[symbol]["BuybackStatus"] = "Unknown"
            self.buyback_assessments[symbol]["NetBuybacks"] = None
            self.buyback_assessments[symbol]["BuybackReason"] = "No current complete cash-flow period."
        self.ui.checkbox(key="require_net_buybacks").check().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Unknown: 3" in item.value for item in self.ui.caption))
        self.assertTrue(any("Buyback filter audit" in item.label for item in self.ui.expander))
        self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_buyback_amount_and_source_survive_chart_failure(self):
        from stock_data import StockDataError
        self.buyback_assessments["AAA"]["BuybackPeriod"] = "Fiscal year ending 2025-12-31"
        self.buyback_assessments["AAA"]["BuybackPeriodBasis"] = "Fiscal year"
        self.ui.checkbox(key="require_net_buybacks").check().run()
        with patch.object(self.app, "cached_history", side_effect=StockDataError("Price feed unavailable")), \
                patch.object(self.app, "render_stock_assistant") as chat:
            self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Price feed unavailable" in item.value for item in self.ui.error))
        self.assertTrue(any("Fiscal year ending 2025-12-31" in item.value for item in self.ui.caption))
        self.assertEqual(chat.call_args.args[-1]["NetBuybacks"], 1_000_000)
        self.assertEqual(chat.call_args.args[-1]["BuybackPeriodBasis"], "Fiscal year")

    def test_float_and_pe_are_optional_and_do_not_fetch_all_company_metadata_when_off(self):
        self.assertFalse(self.ui.checkbox(key="require_low_float").value)
        self.assertFalse(self.ui.checkbox(key="require_positive_pe").value)
        self.assertEqual(self.ui.number_input(key="maximum_float_percent").value, 25.0)
        self.assertTrue(self.ui.number_input(key="maximum_float_percent").disabled)
        self.app.cached_info.reset_mock()
        self.ui.run()
        self.app.cached_info.assert_called_once_with("AAA")
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])
        table = next(item.value for item in self.ui.dataframe if "Score" in item.value)
        self.assertNotIn("Public float (shares)", table)
        self.assertNotIn("Trailing P/E", table)

    def test_float_limit_includes_exact_boundary_and_displays_both_units(self):
        self.company_info["BBB"]["floatShares"] = 2_500_001
        self.ui.checkbox(key="require_low_float").check().run()
        self.assertFalse(self.ui.exception)
        self.assertFalse(self.ui.number_input(key="maximum_float_percent").disabled)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
        table = next(item.value for item in self.ui.dataframe if "Score" in item.value)
        self.assertEqual(table["Public float (% of outstanding)"].tolist(), ["25.00%"])
        self.assertEqual(table["Public float (shares)"].tolist(), ["2,500,000"])
        self.assertTrue(any(item.label == "Public float (shares)" and item.value == "2,500,000"
                            for item in self.ui.metric))
        self.assertTrue(any(item.label == "Public float (% of outstanding)" and item.value == "25.00%"
                            for item in self.ui.metric))
        audit = next(item.value for item in self.ui.dataframe if "Status" in item.value)
        self.assertEqual(audit["Status"].tolist(), ["Pass", "Fail", "Fail"])
        self.ui.number_input(key="maximum_float_percent").set_value(50.0).run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])
        self.ui.number_input(key="maximum_float_percent").set_value(0.0).run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("within the selected limit" in item.value for item in self.ui.info))
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_float_unknowns_never_pass_even_with_maximum_100_percent(self):
        self.company_info["AAA"].pop("floatShares")
        self.company_info["BBB"]["floatShares"] = 10_000_001
        self.company_info["CCC"]["sharesOutstanding"] = 0
        self.ui.checkbox(key="require_low_float").check().run()
        self.ui.number_input(key="maximum_float_percent").set_value(100.0).run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Unavailable or inconsistent data: 3" in item.value for item in self.ui.caption))
        audit = next(item.value for item in self.ui.dataframe if "Status" in item.value)
        self.assertEqual(audit["Status"].tolist(), ["Unknown"] * 3)
        self.assertIn("exceeds", audit.iloc[1]["Evidence / limitations"])
        self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))

    def test_positive_pe_strict_zero_boundary_and_no_upper_limit(self):
        for symbol, pe in (("AAA", -1.0), ("BBB", 0.0), ("CCC", 0.000001)):
            self.company_info[symbol]["trailingPE"] = pe
        self.ui.checkbox(key="require_positive_pe").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["CCC"])
        table = next(item.value for item in self.ui.dataframe if "Score" in item.value)
        self.assertEqual(float(table.iloc[0]["Trailing P/E"]), 0.000001)
        self.assertTrue(any(item.label == "Trailing P/E" and float(item.value) == 0.000001
                            for item in self.ui.metric))
        self.company_info["CCC"]["trailingPE"] = 1e9
        self.ui.run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["CCC"])
        self.company_info["CCC"]["trailingPE"] = 0
        self.ui.run()
        self.assertTrue(any("P/E above 0" in item.value for item in self.ui.info))
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_missing_or_nonfinite_pe_does_not_use_forward_estimates(self):
        self.company_info["AAA"].pop("trailingPE")
        self.company_info["AAA"]["forwardPE"] = 20
        self.company_info["BBB"]["trailingPE"] = float("inf")
        self.company_info["CCC"]["trailingPE"] = float("nan")
        self.ui.checkbox(key="require_positive_pe").check().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Unavailable or invalid P/E: 3" in item.value for item in self.ui.caption))
        self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))

    def test_filters_combine_and_reuse_the_same_company_snapshot_for_chart(self):
        self.ui.checkbox(key="require_low_float").check().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB"])
        self.ui.checkbox(key="require_positive_pe").check().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
        self.checkbox("High short interest (≥10% of float)").check().run()
        self.checkbox("EV / Revenue below 10").check().run()
        self.app.cached_info.reset_mock()
        with patch.object(self.app, "render_chart_and_assistant") as chart:
            self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.app.cached_info.call_count, 3)
        evidence = chart.call_args.args[-1]
        self.assertEqual(evidence["FloatShares"], 2_500_000)
        self.assertEqual(evidence["FloatPercentOfSharesOutstanding"], 0.25)
        self.assertEqual(evidence["FloatPercentLimit"], 0.25)
        self.assertEqual(evidence["TrailingPE"], 12.5)
        self.assertEqual(evidence["ShortPercentOfFloat"], 0.2)
        self.checkbox("Positive rolling revenue growth").check().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
        self.ui.checkbox(key="require_positive_pe").uncheck().run()
        self.checkbox("Positive rolling revenue growth").uncheck().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB"])

    def test_provider_failure_is_unknown_and_price_failure_preserves_float_and_pe_evidence(self):
        from stock_data import StockDataError

        def info(symbol):
            if symbol == "BBB":
                raise StockDataError("Test metadata unavailable")
            return self.company_info[symbol]

        self.app.cached_info.side_effect = info
        self.ui.checkbox(key="require_low_float").check().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Unavailable or inconsistent data: 1" in item.value for item in self.ui.caption))
        audit = next(item.value for item in self.ui.dataframe if "Status" in item.value)
        self.assertEqual(audit.set_index("Symbol").loc["BBB", "Status"], "Unknown")
        self.ui.checkbox(key="require_positive_pe").check().run()
        with (
            patch.object(self.app, "cached_history", side_effect=StockDataError("Test chart failure")),
            patch.object(self.app, "render_stock_assistant") as assistant,
        ):
            self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Test chart failure" in item.value for item in self.ui.error))
        self.assertTrue(any(item.label == "Public float (shares)" for item in self.ui.metric))
        self.assertTrue(any(item.label == "Trailing P/E" for item in self.ui.metric))
        self.assertEqual(assistant.call_args.args[-1]["FloatPercentOfSharesOutstanding"], 0.25)

    def test_company_cache_survives_toggling_filters_and_changing_limit(self):
        self.cached_company_info.clear()
        self.addCleanup(self.cached_company_info.clear)
        with (
            patch.object(self.app, "cached_info", self.cached_company_info),
            patch.object(self.app, "get_company_info", side_effect=lambda symbol: self.company_info[symbol]) as provider,
        ):
            self.ui.run()
            self.assertEqual(provider.call_count, 1)
            self.ui.checkbox(key="require_low_float").check().run()
            self.assertEqual(provider.call_count, 3)
            self.ui.checkbox(key="require_positive_pe").check().run()
            self.ui.number_input(key="maximum_float_percent").set_value(50.0).run()
            self.checkbox("High short interest (≥10% of float)").check().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(provider.call_count, 3)
        self.assertEqual(self.cached_company_info._info.ttl, 86400)

    def test_fully_warm_checkbox_changes_make_no_new_provider_requests(self):
        for cache in (self.cached_company_info, self.cached_revenue_per_stock, self.cached_shape_scan):
            cache.clear()
            self.addCleanup(cache.clear)
        with (
            patch.object(self.app, "cached_info", self.cached_company_info),
            patch.object(self.app, "cached_stock_revenue_growth", self.cached_revenue_per_stock),
            patch.object(self.app, "cached_stock_inflection_scan", self.cached_shape_scan),
            patch.object(self.app, "get_company_info", side_effect=lambda symbol: self.company_info[symbol]) as info,
            patch.object(self.app, "get_revenue_growth_scan",
                         side_effect=lambda symbols, **kwargs: self.revenue.loc[self.revenue["Symbol"].isin(symbols)]) as revenue,
            patch.object(self.app, "get_inflection_scan", return_value=self.scan) as prices,
        ):
            self.ui.run()
            self.ui.checkbox(key="require_low_float").check().run()
            self.checkbox("Positive rolling revenue growth").check().run()
            initial = (info.call_count, revenue.call_count, prices.call_count)
            self.assertEqual(initial, (3, 3, 1))
            self.ui.checkbox(key="require_positive_pe").check().run()
            self.ui.number_input(key="maximum_float_percent").set_value(50.0).run()
            self.checkbox("High short interest (≥10% of float)").check().run()
            self.checkbox("EV / Revenue below 10").check().run()
            self.checkbox("Positive rolling revenue growth").uncheck().run()
            self.checkbox("Positive rolling revenue growth").check().run()
            self.app.cached_russell_holdings.return_value = self.holdings.iloc[::-1]
            self.ui.run()
            self.assertFalse(self.ui.exception)
            self.assertEqual((info.call_count, revenue.call_count, prices.call_count), initial)
            self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
            self.assertTrue(any("cached entries reused" in item.value for item in self.ui.caption))
            self.assertTrue(any("0 entries loaded/computed" in item.value for item in self.ui.caption))

    def test_unavailable_metadata_is_not_retried_until_explicit_refresh(self):
        from stock_data import StockDataError

        self.cached_company_info.clear()
        self.addCleanup(self.cached_company_info.clear)
        with (
            patch.object(self.app, "cached_info", self.cached_company_info),
            patch.object(self.app, "get_company_info", side_effect=StockDataError("Rate limited")) as provider,
        ):
            self.ui.checkbox(key="require_positive_pe").check().run()
            self.assertEqual(provider.call_count, 3)
            self.ui.checkbox(key="require_low_float").check().run()
            self.ui.number_input(key="maximum_float_percent").set_value(50.0).run()
            self.ui.run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(provider.call_count, 3)
            self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))
            self.assertTrue(any("Failed market requests" in item.value for item in self.ui.warning))
            self.ui.button(key="refresh_u_recovery").click().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(provider.call_count, 6)

    def test_float_and_pe_preserve_near_only_selection_and_research_handoff(self):
        self.mixed_shapes()
        self.company_info["BBB"]["trailingPE"] = 7.0
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.ui.checkbox(key="require_low_float").check().run()
        self.ui.checkbox(key="require_positive_pe").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB"])
        next(button for button in self.ui.button if button.label == "Open in Individual Stocks").click().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB"])
        self.assertEqual(self.ui.session_state["stock_query"], "BBB")

    def test_business_filters_combine_with_each_other_and_existing_criteria(self):
        import app

        def assessment(symbol, criteria):
            return {
                "ProfitabilityStatus": "Pass" if symbol in ("AAA", "BBB") else "Fail",
                "ProfitabilityReason": "Operating margin and cash comparison",
                "DeleveragingStatus": "Pass" if symbol in ("AAA", "CCC") else "Fail",
                "DeleveragingReason": "Gross debt, net debt and cash comparison",
                "SmallCapStatus": "Pass" if symbol == "AAA" else "Unknown",
                "SmallCapReason": "USD capitalization comparison",
                "MarketCapUSD": 1e9 if symbol == "AAA" else None,
                "SectorStrengthStatus": "Pass" if symbol == "AAA" else "Fail",
                "SectorStrengthReason": "Both USD return horizons",
                "SectorBenchmark": "IXN", "SectorExcess3M": 0.1, "SectorExcess6M": 0.2,
                "ManagementStatus": "Favorable" if symbol == "AAA" else "Unreviewed",
                "ManagementReason": "Source-backed manual review",
            }

        with patch.object(app, "load_recovery_signals", side_effect=assessment) as loader:
            self.ui.run()
            loader.assert_not_called()
            self.checkbox("Improving profitability and cash generation").check().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
            self.checkbox("Deleveraging turnaround").check().run()
            self.assertEqual(len(self.selectbox("Chart candidate").options), 1)
            self.assertEqual(self.selectbox("Chart candidate").value, "AAA")
            self.checkbox("Improving profitability and cash generation").uncheck().run()
            self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
            self.checkbox("High short interest (≥10% of float)").check().run()
            self.assertEqual(len(self.selectbox("Chart candidate").options), 1)
            for label in (
                "Market cap under $2B (USD)", "Stronger than its sector (3 and 6 months)",
                "Management & Incentives: favorable reviewed evidence",
            ):
                self.checkbox(label).check().run()
                self.assertFalse(self.ui.exception)
                self.assertEqual(self.selectbox("Chart candidate").value, "AAA")

    def test_unknown_business_evidence_does_not_pass_and_audit_remains_visible(self):
        import app

        with patch.object(app, "load_recovery_signals", return_value={
            "SmallCapStatus": "Unknown", "SmallCapReason": "FX is unavailable",
        }):
            self.checkbox("Market cap under $2B (USD)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("No U-pattern candidates meet every" in item.value for item in self.ui.info))
        self.assertTrue(any("Unknown: 3" in item.value for item in self.ui.caption))
        self.assertTrue(any("Business-filter audit" in item.label for item in self.ui.expander))
        self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))

    def test_financial_assessment_is_shared_by_profitability_and_deleveraging(self):
        import app

        with patch.object(app, "cached_financial_recovery", return_value={
            "ProfitabilityStatus": "Pass", "DeleveragingStatus": "Fail",
        }) as financial:
            result = app.load_recovery_signals("AAA", ("profitability", "deleveraging"))
        financial.assert_called_once_with("AAA", app.RECOVERY_MODEL_VERSION)
        self.assertEqual(result["ProfitabilityStatus"], "Pass")
        self.assertEqual(result["DeleveragingStatus"], "Fail")

    def test_shareholder_yield_is_optional_and_combines_with_revenue(self):
        import app

        def assessment(symbol, criteria):
            return {
                "ShareholderYieldStatus": "Pass" if symbol in ("AAA", "BBB") else "Fail",
                "ShareholderYieldReason": "Cash dividends and net buybacks",
                "ShareholderYield": 0.03 if symbol in ("AAA", "BBB") else -0.01,
                "ShareholderYieldPeriod": "TTM ending 2026-06-30",
            }

        with patch.object(app, "load_recovery_signals", side_effect=assessment) as loader:
            self.ui.run()
            loader.assert_not_called()
            self.checkbox("Positive shareholder yield (>0%)").check().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
            matching = next(frame.value for frame in self.ui.dataframe if "Score" in frame.value.columns)
            self.assertEqual(matching["Shareholder yield"].tolist(), ["3.00%", "3.00%"])
            self.assertEqual(matching["Shareholder yield period"].tolist(), ["TTM ending 2026-06-30"] * 2)
            self.assertTrue(any(metric.label == "Shareholder yield" and metric.value == "3.00%" for metric in self.ui.metric))
            self.checkbox("Positive rolling revenue growth").check().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(self.selectbox("Chart candidate").value, "AAA")
            self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
            self.checkbox("Positive shareholder yield (>0%)").uncheck().run()
            self.assertFalse(self.ui.exception)
            self.assertEqual(len(self.selectbox("Chart candidate").options), 2)

    def test_shareholder_yield_unknowns_remain_in_audit_not_results(self):
        import app

        with patch.object(app, "load_recovery_signals", return_value={
            "ShareholderYieldStatus": "Unknown", "ShareholderYieldReason": "Missing cash-flow data",
        }):
            self.checkbox("Positive shareholder yield (>0%)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Unknown: 3" in item.value for item in self.ui.caption))
        self.assertTrue(any("Business-filter audit" in item.label for item in self.ui.expander))
        self.assertFalse(any(item.label == "Chart candidate" for item in self.ui.selectbox))

    def test_company_yield_filter_is_not_offered_for_etf_universe(self):
        import app

        with patch.object(app, "cached_inflection_scan", return_value=pd.DataFrame()):
            next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value("ETF atlas").run()
        self.assertFalse(self.ui.exception)
        self.assertFalse(any(item.label == "Positive shareholder yield (>0%)" for item in self.ui.checkbox))

    def test_twst_is_a_separate_dated_reference_not_a_candidate(self):
        self.assertFalse(self.ui.exception)
        self.assertTrue(any(item.label == "Reference patterns" for item in self.ui.expander))
        self.assertTrue(any("TWST — Twist Bioscience" in item.value for item in self.ui.markdown))
        self.assertTrue(any("5–75% recovery" in item.value for item in self.ui.caption))
        self.assertNotIn("TWST", self.selectbox("Chart candidate").options)
        next(
            button for button in self.ui.button
            if button.label == "Open TWST reference in Individual Stocks"
        ).click().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["TWST"])
        self.assertEqual(self.ui.session_state["stock_research_queue_label"], "U-shape reference patterns")
        self.assertEqual(self.ui.session_state["stock_query"], "TWST")
        self.assertEqual(self.ui.session_state["research_area"], "Individual stocks")

    def test_twst_reference_remains_available_when_no_shape_group_is_selected(self):
        self.app.cached_russell_holdings.reset_mock()
        self.app.cached_stock_inflection_scan.reset_mock()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("TWST — Twist Bioscience" in item.value for item in self.ui.markdown))
        self.assertTrue(any("Select Strict U-shape matches" in message.value for message in self.ui.info))
        self.app.cached_russell_holdings.assert_not_called()
        self.app.cached_stock_inflection_scan.assert_not_called()

    def mixed_shapes(self):
        self.scan.loc[1:, "ShapeMatch"] = "Near miss"
        self.scan.loc[1:, "ShapeMissCount"] = [1, 2]
        self.scan.loc[1:, "ShapeMissedRules"] = ["Price vs. 50-day MA: -1%; needs > 0%", "Base span and low-zone days"]
        self.ui.run()

    def test_strict_near_both_and_neither_are_independent_selections(self):
        self.mixed_shapes()
        self.assertFalse(self.ui.exception)
        self.assertTrue(self.ui.checkbox(key="u_shape_strict").value)
        self.assertFalse(self.ui.checkbox(key="u_shape_near").value)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
        self.ui.checkbox(key="u_shape_near").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "BBB", "CCC"])
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB", "CCC"])
        table = next(frame.value for frame in self.ui.dataframe if "Shape match" in frame.value.columns)
        self.assertEqual(set(table["Shape match"]), {"Near miss"})
        self.assertIn("Why near miss", table)
        self.assertTrue(any("not a strict U-shape match" in warning.value for warning in self.ui.warning))
        self.app.cached_russell_holdings.reset_mock()
        self.app.cached_stock_inflection_scan.reset_mock()
        self.ui.checkbox(key="u_shape_near").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Select Strict U-shape matches" in message.value for message in self.ui.info))
        self.app.cached_russell_holdings.assert_not_called()
        self.app.cached_stock_inflection_scan.assert_not_called()
        self.assertNotIn("stock_research_queue", self.ui.session_state)
        self.assertFalse(any(widget.label == "Chart candidate" for widget in self.ui.selectbox))
        self.ui.checkbox(key="u_shape_strict").check().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])

    def test_near_misses_keep_financial_and_filters_and_research_handoff(self):
        self.mixed_shapes()
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        with patch.object(self.app, "render_chart_and_assistant") as chart:
            self.checkbox("Positive rolling revenue growth").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.selectbox("Chart candidate").value, "CCC")
        self.assertEqual(chart.call_args.args[-1]["ShapeMatch"], "Near miss")
        next(button for button in self.ui.button if button.label == "Open in Individual Stocks").click().run()
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["CCC"])
        self.assertEqual(self.ui.session_state["stock_query"], "CCC")
        self.checkbox("High short interest (≥10% of float)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertFalse(any(widget.label == "Chart candidate" for widget in self.ui.selectbox))
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_no_near_matches_does_not_fall_back_to_strict_matches(self):
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("No securities currently match" in info.value for info in self.ui.info))
        self.assertFalse(any(widget.label == "Chart candidate" for widget in self.ui.selectbox))
        self.assertNotIn("stock_research_queue", self.ui.session_state)

    def test_completed_intermediate_cycle_is_available_only_via_near_misses(self):
        from stock_data import analyze_etf_inflection
        from tests.test_u_shape_modes import intermediate_cycle_history

        near = analyze_etf_inflection(intermediate_cycle_history(), include_near_misses=True)
        self.app.cached_stock_inflection_scan.return_value = pd.DataFrame([
            {**self.scan.iloc[0].to_dict()},
            {"Symbol": "BBB", **near},
        ])
        self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
        self.ui.checkbox(key="u_shape_near").check().run()
        self.assertEqual(set(self.ui.session_state["stock_research_queue"]), {"AAA", "BBB"})
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB"])
        self.assertTrue(any("Completed intermediate cycle" in item.value for item in self.ui.warning))
        next(button for button in self.ui.button if button.label == "Open in Individual Stocks").click().run()
        self.assertEqual(self.ui.session_state["stock_query"], "BBB")
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB"])
    def test_business_filters_assess_only_selected_near_misses_and_reject_unknowns(self):
        self.mixed_shapes()
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        with patch.object(self.app, "load_recovery_signals", side_effect=lambda symbol, criteria: {
            "SmallCapStatus": "Pass" if symbol == "BBB" else "Unknown",
            "SmallCapReason": "Test cap" if symbol == "BBB" else "Unavailable cap",
            "MarketCapUSD": 1e9 if symbol == "BBB" else None,
        }) as loader:
            self.checkbox("Market cap under $2B (USD)").check().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual({call.args[0] for call in loader.call_args_list}, {"BBB", "CCC"})
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["BBB"])
        self.assertTrue(any("Unknown: 1" in caption.value for caption in self.ui.caption))

    def test_empty_shape_selection_preserves_another_pages_queue(self):
        self.ui.session_state["stock_research_queue"] = ["INCOME"]
        self.ui.session_state["stock_research_queue_label"] = "Income candidates"
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertFalse(self.ui.exception)
        self.assertEqual(self.ui.session_state["stock_research_queue"], ["INCOME"])
        self.assertEqual(self.ui.session_state["stock_research_queue_label"], "Income candidates")

    def test_near_reason_survives_chart_failure_and_navigation_wraps_within_group(self):
        from stock_data import StockDataError

        self.mixed_shapes()
        self.ui.checkbox(key="u_shape_near").check().run()
        self.ui.checkbox(key="u_shape_strict").uncheck().run()
        self.assertEqual(self.selectbox("Chart candidate").value, "BBB")
        next(button for button in self.ui.button if button.label == "→").click().run()
        self.assertEqual(self.selectbox("Chart candidate").value, "CCC")
        next(button for button in self.ui.button if button.label == "→").click().run()
        self.assertEqual(self.selectbox("Chart candidate").value, "BBB")
        with (
            patch.object(self.app, "cached_history", side_effect=StockDataError("Test history unavailable")),
            patch.object(self.app, "render_stock_assistant") as assistant,
        ):
            self.ui.run()
        self.assertFalse(self.ui.exception)
        self.assertTrue(any("Test history unavailable" in error.value for error in self.ui.error))
        self.assertTrue(any("Price vs. 50-day MA" in warning.value for warning in self.ui.warning))
        self.assertEqual(assistant.call_args.args[-1]["ShapeMatch"], "Near miss")
        self.app.render_revenue_outlook_research.assert_called_with("BBB", "Company B")

    def test_shape_modes_apply_to_all_stock_and_etf_universes(self):
        self.mixed_shapes()
        holdings = self.holdings.assign(Country="Example", Sector="Technology")
        with ExitStack() as stack:
            for loader in ("cached_sp500_holdings", "cached_european_holdings"):
                stack.enter_context(patch.object(self.app, loader, return_value=holdings))
            stack.enter_context(patch.object(self.app, "cached_inflection_scan", return_value=self.scan))
            stack.enter_context(patch.object(self.app, "render_etf_holdings"))
            stack.enter_context(patch.object(self.app, "etf_catalog", return_value=[
                {"Symbol": symbol, "Fund": f"Fund {symbol}", "Category": "Example"}
                for symbol in ("AAA", "BBB", "CCC")
            ]))
            self.ui.checkbox(key="u_shape_near").check().run()
            self.ui.checkbox(key="u_shape_strict").uncheck().run()
            for universe in ("S&P 500 stocks", "European stocks", "ETF atlas"):
                with self.subTest(universe=universe):
                    next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value(universe).run()
                    self.assertFalse(self.ui.exception)
                    self.assertEqual(len(self.selectbox("Chart candidate").options), 2)
                    self.assertTrue(self.ui.checkbox(key="u_shape_near").value)
                    self.assertFalse(self.ui.checkbox(key="u_shape_strict").value)
                    if universe == "ETF atlas":
                        self.assertFalse(any(
                            widget.key == "expected_revenue_growth_placeholder"
                            for widget in self.ui.checkbox
                        ))
                        self.assertFalse(any(
                            widget.key in ("require_low_float", "require_positive_pe", "require_net_buybacks")
                            for widget in self.ui.checkbox
                        ))
                        self.assertFalse(any(widget.key == "maximum_float_percent" for widget in self.ui.number_input))
                    else:
                        placeholder = self.ui.checkbox(key="expected_revenue_growth_placeholder")
                        self.assertTrue(placeholder.disabled)
                        self.assertFalse(placeholder.value)
                        self.assertFalse(self.ui.checkbox(key="require_low_float").value)
                        self.assertFalse(self.ui.checkbox(key="require_positive_pe").value)
                        self.assertFalse(self.ui.checkbox(key="require_net_buybacks").value)

    def test_float_and_pe_apply_in_all_stock_universes_but_not_etfs(self):
        holdings = self.holdings.assign(Country="Example", Sector="Technology")
        with (
            patch.object(self.app, "cached_sp500_holdings", return_value=holdings),
            patch.object(self.app, "cached_european_holdings", return_value=holdings),
            patch.object(self.app, "cached_inflection_scan", return_value=pd.DataFrame()),
        ):
            self.ui.checkbox(key="require_low_float").check().run()
            self.ui.checkbox(key="require_positive_pe").check().run()
            for universe in ("S&P 500 stocks", "European stocks"):
                next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value(universe).run()
                self.assertFalse(self.ui.exception)
                self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA"])
            self.app.cached_info.reset_mock()
            next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value("ETF atlas").run()
            self.assertFalse(self.ui.exception)
            self.app.cached_info.assert_not_called()

    def test_net_buybacks_apply_to_all_stock_universes_not_etfs(self):
        holdings = self.holdings.assign(Country="Example", Sector="Technology")
        with (
            patch.object(self.app, "cached_sp500_holdings", return_value=holdings),
            patch.object(self.app, "cached_european_holdings", return_value=holdings),
            patch.object(self.app, "cached_inflection_scan", return_value=pd.DataFrame()),
        ):
            self.ui.checkbox(key="require_net_buybacks").check().run()
            for universe in ("S&P 500 stocks", "European stocks"):
                next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value(universe).run()
                self.assertFalse(self.ui.exception)
                self.assertEqual(self.ui.session_state["stock_research_queue"], ["AAA", "CCC"])
            self.buybacks.reset_mock()
            next(widget for widget in self.ui.radio if widget.label == "Scanner universe").set_value("ETF atlas").run()
            self.assertFalse(self.ui.exception)
            self.buybacks.assert_not_called()


if __name__ == "__main__":
    unittest.main()
