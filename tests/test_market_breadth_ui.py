import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from market_breadth import BREADTH_MODEL_VERSION, BreadthSnapshot, calculate_market_breadth
from market_breadth_ui import breadth_comparison_chart, breadth_participation_chart
from stock_data import StockDataError


def snapshot():
    dates = pd.bdate_range("2025-09-01", periods=270)
    prices = pd.DataFrame({"AAA": range(1, 271), "BBB": range(2, 272)}, index=dates)
    daily, coverage = calculate_market_breadth(
        prices, pd.Series(range(100, 370), index=dates), as_of="2026-09-24",
    )
    return BreadthSnapshot(daily, coverage, "2026-09-24T07:00:00+00:00")


class MarketBreadthUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.snapshot = snapshot()
        self.holdings = self.stack.enter_context(patch.object(app, "cached_sp500_holdings", return_value=pd.DataFrame({
            "Symbol": ["AAA", "BBB"], "AsOfDate": [date(2026, 9, 23)] * 2,
        })))
        self.loader = self.stack.enter_context(patch.object(app, "cached_market_breadth", return_value=self.snapshot))
        self.chat = self.stack.enter_context(patch.object(app, "render_stock_assistant"))

    def ui(self):
        return AppTest.from_string("from app import render_other_charts\nrender_other_charts()").run()

    def test_initial_view_is_on_demand_then_displays_charts_dates_and_metrics(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.holdings.assert_not_called()
        self.loader.assert_not_called()
        self.assertFalse(ui.button(key="refresh_other_charts").disabled)
        ui.button(key="load_sp500_breadth").click().run()
        self.assertFalse(ui.exception)
        self.loader.assert_called_once_with(("AAA", "BBB"), BREADTH_MODEL_VERSION)
        self.assertEqual(len(ui.get("plotly_chart")), 2)
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "Advancing / declining").value, "2 / 0")
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "Stocks advancing").value, "100.0%")
        self.assertTrue(any("2026-09-23" in caption.value for caption in ui.caption))
        self.assertTrue(any("survivorship" in caption.value for caption in ui.caption))
        self.assertEqual(len(ui.get("download_button")), 1)
        self.chat.assert_not_called()

    def test_refresh_keeps_load_choice_and_retries_after_failure(self):
        self.loader.side_effect = StockDataError("Provider unavailable")
        ui = self.ui()
        ui.button(key="load_sp500_breadth").click().run()
        self.assertFalse(ui.exception)
        self.assertIn("Provider unavailable", ui.error[0].value)
        self.assertFalse(ui.button(key="refresh_other_charts").disabled)
        self.loader.side_effect = None
        with patch.object(self.app.st.cache_data, "clear") as clear:
            ui.button(key="refresh_other_charts").click().run()
        clear.assert_called_once()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.session_state["sp500_breadth_loaded"])
        self.assertEqual(len(ui.get("plotly_chart")), 2)
        self.assertFalse(ui.error)

    def test_empty_or_failed_holdings_do_not_call_price_loader(self):
        for error in (None, StockDataError("Holdings unavailable")):
            with self.subTest(error=error):
                self.holdings.return_value = pd.DataFrame()
                self.holdings.side_effect = error
                ui = self.ui()
                ui.button(key="load_sp500_breadth").click().run()
                self.assertFalse(ui.exception)
                self.assertTrue(ui.error)
                self.loader.assert_not_called()

    def test_insufficient_coverage_displays_na_and_gap_warning_not_bearish_zeros(self):
        latest = self.snapshot.daily.index[-1]
        for column in ("AdvancingPercent", "NetAdvances", "ADLine", "AboveMA50Percent", "AboveMA200Percent"):
            self.snapshot.daily.loc[latest, column] = float("nan")
        self.snapshot.daily.loc[latest, "ADCoverage"] = 0.5
        self.snapshot.daily.loc[latest, "ADComparable"] = 1
        ui = self.ui()
        ui.button(key="load_sp500_breadth").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "Advancing / declining").value, "N/A")
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "Above 200-day MA").value, "N/A")
        self.assertTrue(any("Partial daily breadth" in warning.value for warning in ui.warning))
        self.assertTrue(any("restarts after each gap" in warning.value for warning in ui.warning))

    def test_new_sidebar_route_preserves_existing_placeholders(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "Other charts"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertIn("Other charts", ui.radio(key="research_area").options)
        self.assertIn("Druckenmiller-like portfolio", ui.radio(key="research_area").options)
        self.assertEqual(ui.title[0].value, "Other charts")
        self.loader.assert_not_called()

    def test_figure_axes_units_and_missing_values_are_explicit(self):
        daily = self.snapshot.daily
        comparison = breadth_comparison_chart(daily)
        self.assertEqual(comparison.data[0].yaxis, "y")
        self.assertEqual(comparison.data[1].yaxis, "y2")
        self.assertFalse(comparison.data[1].connectgaps)
        self.assertIn("rebased", comparison.layout.yaxis.title.text)
        self.assertIn("net advancing", comparison.layout.yaxis2.title.text)
        participation = breadth_participation_chart(daily)
        self.assertEqual(tuple(participation.layout.yaxis.range), (0, 100))
        self.assertTrue(all(not trace.connectgaps for trace in participation.data))


class MarketBreadthCacheTests(unittest.TestCase):
    def test_cache_reuses_same_universe_and_separates_different_universes(self):
        import app
        app.cached_market_breadth.clear()
        self.addCleanup(app.cached_market_breadth.clear)
        with patch.object(app, "get_market_breadth", return_value=snapshot()) as loader:
            app.cached_market_breadth(("AAA", "BBB"), BREADTH_MODEL_VERSION)
            app.cached_market_breadth(("AAA", "BBB"), BREADTH_MODEL_VERSION)
            loader.assert_called_once()
            app.cached_market_breadth(("AAA",), BREADTH_MODEL_VERSION)
            self.assertEqual(loader.call_count, 2)
        self.assertEqual(app.cached_market_breadth._info.ttl, 86400)
        with self.assertRaises(ValueError):
            app.cached_market_breadth(("AAA",), "unsupported")


if __name__ == "__main__":
    unittest.main()
