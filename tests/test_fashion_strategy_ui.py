import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest


class FashionStrategyUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        companies = [
            {
                "Symbol": symbol,
                "Name": name,
                "Region": "US",
                "SearchTerm": name,
            }
            for symbol, name in (("AAA", "Brand A"), ("BBB", "Brand B"))
        ]
        downtrend = pd.DataFrame({"Close": [100.0] * 150 + [80.0] * 50})
        self.stack.enter_context(patch.object(app, "FASHION_COMPANIES", companies))
        self.stack.enter_context(patch.object(
            app,
            "cached_google_trends_signal",
            return_value={
                "Available": True,
                "Momentum": -0.30,
                "CurrentInterest": 14,
                "PreviousInterest": 20,
            },
        ))
        self.stack.enter_context(patch.object(
            app,
            "cached_reddit_mention_signal",
            return_value={
                "Available": True,
                "Momentum": -0.50,
                "RecentCount": 3,
                "PreviousCount": 12,
            },
        ))
        self.stack.enter_context(patch.object(
            app,
            "cached_news_volume_signal",
            return_value={
                "Available": True,
                "Momentum": -0.50,
                "RecentCount": 3,
                "PreviousCount": 12,
            },
        ))
        self.stack.enter_context(
            patch.object(app, "cached_history", return_value=downtrend)
        )
        self.stack.enter_context(patch.object(app, "cached_info", return_value={}))
        self.stack.enter_context(
            patch.object(app, "price_chart", return_value=go.Figure())
        )
        self.stack.enter_context(patch.object(app, "render_bookmark_button"))
        self.stack.enter_context(patch.object(app, "render_stock_assistant"))

    @staticmethod
    def ui():
        return AppTest.from_string(
            "from app import render_fashion_trend_strategy\n"
            "render_fashion_trend_strategy()"
        ).run()

    @staticmethod
    def candidate_selector(ui):
        return next(
            widget for widget in ui.selectbox
            if widget.label == "Research a company"
        )

    def test_candidates_have_wraparound_chart_navigation(self):
        ui = self.ui()

        self.assertFalse(ui.exception)
        self.assertEqual(self.candidate_selector(ui).value, "AAA")
        ui.button(key="fashion_next_research").click().run()
        self.assertEqual(self.candidate_selector(ui).value, "BBB")
        ui.button(key="fashion_next_research").click().run()
        self.assertEqual(self.candidate_selector(ui).value, "AAA")
        ui.button(key="fashion_previous_research").click().run()
        self.assertEqual(self.candidate_selector(ui).value, "BBB")

    def test_single_candidate_disables_navigation(self):
        ui = self.ui()
        brands = next(
            widget for widget in ui.multiselect
            if widget.label == "Brands to compare (maximum 5)"
        )
        ui = brands.set_value(["AAA"]).run()

        self.assertFalse(ui.exception)
        self.assertTrue(ui.button(key="fashion_previous_research").disabled)
        self.assertTrue(ui.button(key="fashion_next_research").disabled)

    def test_no_qualifying_candidates_still_show_browser(self):
        accelerating = {
            "Available": True,
            "Momentum": 0.50,
            "RecentCount": 9,
            "PreviousCount": 12,
            "CurrentInterest": 30,
            "PreviousInterest": 20,
        }
        with patch.object(
            self.app, "cached_google_trends_signal", return_value=accelerating,
        ):
            with patch.object(
                self.app, "cached_reddit_mention_signal", return_value=accelerating,
            ):
                with patch.object(
                    self.app, "cached_news_volume_signal", return_value=accelerating,
                ):
                    ui = self.ui()

        self.assertFalse(ui.exception)
        self.assertTrue(any("still browse" in item.value for item in ui.info))
        self.assertEqual(self.candidate_selector(ui).value, "AAA")
        self.assertFalse(ui.button(key="fashion_next_research").disabled)
        self.assertEqual(len(ui.get("plotly_chart")), 1)

    def test_browser_excludes_stocks_that_are_not_in_chart_downtrends(self):
        downtrend = pd.DataFrame({"Close": [100.0] * 150 + [80.0] * 50})
        uptrend = pd.DataFrame({"Close": [80.0] * 150 + [100.0] * 50})

        def history(symbol, period, interval):
            return downtrend if symbol == "AAA" else uptrend

        with patch.object(self.app, "cached_history", side_effect=history):
            ui = self.ui()

        self.assertFalse(ui.exception)
        self.assertEqual(self.candidate_selector(ui).value, "AAA")
        self.assertTrue(ui.button(key="fashion_previous_research").disabled)
        self.assertTrue(ui.button(key="fashion_next_research").disabled)
        self.assertTrue(
            any("passes both chart-downtrend rules" in item.value for item in ui.caption)
        )

    def test_no_chart_downtrends_hides_browser(self):
        uptrend = pd.DataFrame({"Close": [80.0] * 150 + [100.0] * 50})
        with patch.object(self.app, "cached_history", return_value=uptrend):
            ui = self.ui()

        self.assertFalse(ui.exception)
        self.assertTrue(
            any("None of the selected companies" in item.value for item in ui.info)
        )
        self.assertFalse(
            any(widget.label == "Research a company" for widget in ui.selectbox)
        )
        self.assertEqual(len(ui.get("plotly_chart")), 0)


if __name__ == "__main__":
    unittest.main()
