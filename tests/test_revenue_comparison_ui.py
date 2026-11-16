import json
import unittest
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError, statement_revenue_growth_summary


def rolling_summary():
    return {
        "Symbol": "OABI", "RevenueGrowth": 38_457_000 / 23_027_000 - 1,
        "RevenuePeriod": "Four quarters ended 2026-06-30 (YoY)",
        "RevenueBasis": "Rolling four quarters",
        "TotalRevenue": 38_457_000, "PriorRollingRevenue": 23_027_000,
        "PriorRollingPeriod": "2025-06-30", "RevenueAccelerating": True,
        "RevenueGrowthTrend": "-29.3% -> 8.2% -> 67.0%",
        "RevenueGrowthHistory": [
            {"Period": pd.Timestamp("2025-12-31"), "RollingRevenue": 18_666_000, "RevenueGrowth": -0.293},
            {"Period": pd.Timestamp("2026-03-31"), "RollingRevenue": 27_000_000, "RevenueGrowth": 0.082},
            {"Period": pd.Timestamp("2026-06-30"), "RollingRevenue": 38_457_000,
             "RevenueGrowth": 38_457_000 / 23_027_000 - 1},
        ],
    }


class RevenueComparisonUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        app.cached_stock_revenue_growth.clear()
        app.cached_revenue_growth_scan.clear()

    def tearDown(self):
        self.app.cached_stock_revenue_growth.clear()
        self.app.cached_revenue_growth_scan.clear()

    def ui(self):
        return AppTest.from_string(
            "from app import render_scanner_revenue_comparison\n"
            "render_scanner_revenue_comparison('OABI', 'USD')"
        ).run()

    def test_oabi_comparison_displays_amounts_dates_and_growth(self):
        with patch.object(self.app, "get_revenue_growth_scan",
                          return_value=pd.DataFrame([rolling_summary()])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual([metric.value for metric in ui.metric],
                         ["USD 38.46M", "67.01%", "USD 23.03M"])
        self.assertIn("2025-06-30", ui.metric[2].label)
        self.assertTrue(any("2026-06-30" in item.value for item in ui.caption))
        self.assertTrue(any("fiscal year's growth" in item.value for item in ui.caption))
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        chart = json.loads(ui.get("plotly_chart")[0].proto.spec)
        self.assertEqual(chart["data"][0]["name"], "Rolling four-quarter revenue")
        self.assertEqual(chart["data"][1]["name"], "Rolling revenue YoY growth")
        self.assertEqual(chart["data"][0]["x"], ["2025-12-31", "2026-03-31", "2026-06-30"])
        self.assertFalse(chart["data"][1]["connectgaps"])
        self.assertIn("Accelerating-growth criterion: passes", ui.caption[-1].value)
        self.assertEqual(ui.dataframe[0].value.iloc[-1]["Rolling revenue"], 38_457_000)

    def test_stock_screen_reuses_scanner_cache_and_other_universes_reuse_symbols(self):
        with patch.object(self.app, "get_revenue_growth_scan",
                          return_value=pd.DataFrame([rolling_summary()])) as fetch:
            version = self.app.REVENUE_MODEL_VERSION
            scan = self.app.cached_revenue_growth_scan(("OABI",), version)
            ui = self.ui()
            ui.run()
            self.assertFalse(ui.exception)
            self.assertEqual(scan.iloc[0]["RevenueGrowth"], rolling_summary()["RevenueGrowth"])
            fetch.assert_called_once_with(
                ["OABI"], sec_loader=self.app.cached_sec_quarterly_revenue,
                financial_loader=self.app.cached_financial_history,
            )
            self.app.cached_revenue_growth_scan(("OABI", "OABI"), version)
            fetch.assert_called_once()

    def test_annual_fallback_is_not_mislabeled_as_rolling(self):
        annual = pd.DataFrame({
            "Period": pd.to_datetime(["2025-12-31"]),
            "Revenue": [18_666_000], "Growth": [-0.2927],
        })
        summary = statement_revenue_growth_summary(pd.DataFrame(), annual)
        with patch.object(self.app, "get_revenue_growth_scan", return_value=pd.DataFrame([summary])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.metric), 2)
        self.assertEqual(ui.metric[0].label, "Latest fiscal-year revenue")
        self.assertIn("Fiscal-year fallback", ui.warning[0].value)
        self.assertTrue(any("does not pass" in item.value for item in ui.caption))
        self.assertFalse(ui.get("plotly_chart"))

    def test_unavailable_comparison_is_not_positive_and_errors_are_visible(self):
        summary = statement_revenue_growth_summary(pd.DataFrame(), pd.DataFrame())
        with patch.object(self.app, "get_revenue_growth_scan", return_value=pd.DataFrame([summary])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.metric), 0)
        self.assertIn("not positive growth", ui.info[0].value)
        self.assertFalse(ui.get("plotly_chart"))
        self.app.cached_stock_revenue_growth.clear()
        with patch.object(self.app, "get_revenue_growth_scan", side_effect=StockDataError("Feed unavailable")):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertIn("Feed unavailable", ui.warning[0].value)
        self.assertFalse(ui.get("plotly_chart"))

    def test_anik_chart_matches_the_scanners_three_rolling_periods_not_annual_decline(self):
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-03-31", periods=10, freq="QE"),
            "Revenue": [29_022_000, 30_724_000, 29_559_000, 30_602_000, 26_168_000,
                        28_219_000, 27_817_000, 30_615_000, 29_612_000, 32_610_000],
        })
        summary = statement_revenue_growth_summary(quarterly, pd.DataFrame())
        with patch.object(self.app, "get_revenue_growth_scan", return_value=pd.DataFrame([summary])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        chart_data = ui.dataframe[0].value
        self.assertEqual(chart_data["Rolling revenue"].tolist(), [112_819_000, 116_263_000, 120_654_000])
        self.assertEqual(
            [round(value * 100, 2) for value in chart_data["YoY growth"]],
            [-5.91, -0.67, 5.33],
        )
        self.assertEqual(chart_data["YoY growth"].iloc[-1], summary["RevenueGrowth"])
        self.assertEqual(chart_data["Rolling revenue"].iloc[-1], summary["TotalRevenue"])

    def test_missing_chart_data_is_explicit_not_a_blank_or_fabricated_chart(self):
        summary = {**rolling_summary(), "RevenueGrowthHistory": []}
        with patch.object(self.app, "get_revenue_growth_scan", return_value=pd.DataFrame([summary])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.get("plotly_chart"))
        self.assertIn("chart is unavailable", ui.warning[0].value)

    def test_chart_preserves_missing_growth_and_shows_non_acceleration(self):
        quarterly = pd.DataFrame({
            "Period": pd.date_range("2024-03-31", periods=8, freq="QE"),
            "Revenue": [100] * 4 + [110] * 4,
        })
        summary = statement_revenue_growth_summary(quarterly, pd.DataFrame())
        with patch.object(self.app, "get_revenue_growth_scan", return_value=pd.DataFrame([summary])):
            ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.assertTrue(ui.dataframe[0].value["YoY growth"].iloc[:2].isna().all())
        self.assertIn("Accelerating-growth criterion: does not pass", ui.caption[-1].value)

    def test_annual_and_quarterly_chart_labels_and_values_are_unchanged(self):
        revenue = pd.DataFrame({
            "Period": pd.to_datetime(["2025-12-31", "2026-03-31"]),
            "Revenue": [100, 105], "Growth": [float("nan"), 0.05],
        })
        for frequency, expected, growth_label in (
            ("annual", ["2025", "2026"], "Year-over-year growth"),
            ("quarterly", ["2025 Q4", "2026 Q1"], "Quarter-over-quarter growth"),
        ):
            with self.subTest(frequency=frequency):
                figure = self.app.revenue_chart(revenue, "USD", frequency, growth_label)
                self.assertEqual(list(figure.data[0].x), expected)
                self.assertEqual(list(figure.data[0].y), [100, 105])
                self.assertEqual(figure.data[0].name, "Revenue")
                self.assertEqual(figure.data[1].name, growth_label)


if __name__ == "__main__":
    unittest.main()
