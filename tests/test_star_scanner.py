import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError
from strategy_catalog import build_star_research_universe


def review(symbol="AAA", region="US"):
    return {
        "Symbol": symbol, "Name": f"Company {symbol}", "Region": region,
        "Niche": "Example niche", "ReviewStatus": "Near miss",
        "LeadershipEvidence": "Leadership supported", "LeadershipSource": "https://example.com/lead",
        "GrowthEvidence": "", "GrowthSource": "", "GrowthRate": None,
        "GrowthPeriod": "", "EvidenceAsOf": "2026-09-06",
        "MissingEvidence": "Exact niche growth not established",
    }


class StarUniverseTests(unittest.TestCase):
    def test_overlap_is_deduplicated_and_unreviewed_is_not_a_failure(self):
        holdings = [
            {"Symbol": "AAA", "Name": "Company A", "Region": "US"},
            {"Symbol": "AAA", "Name": "Company A", "Region": "US"},
            {"Symbol": "BBB.L", "Name": "Company B", "Region": "Europe"},
        ]
        rows = build_star_research_universe(holdings, [review()])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["ReviewStatus"], "Near miss")
        self.assertEqual(rows[1]["ReviewStatus"], "Unreviewed")
        self.assertIsNone(rows[1]["GrowthRate"])
        self.assertIn("not a failed", rows[1]["MissingEvidence"])


class StarScannerUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(
            app, "star_principle_catalog", return_value=[review(), review("BBB.L", "Europe")],
        ))
        self.history = self.stack.enter_context(patch.object(
            app, "cached_history", return_value=pd.DataFrame({"Close": [10, 11]}),
        ))
        self.stack.enter_context(patch.object(app, "cached_info", return_value={}))
        self.stack.enter_context(patch.object(app, "price_chart", return_value=go.Figure()))
        self.bookmark = self.stack.enter_context(patch.object(app, "render_bookmark_button"))
        self.stack.enter_context(patch.object(app, "render_company_news"))

    def ui(self):
        return AppTest.from_string(
            "from app import render_star_principle_strategy\nrender_star_principle_strategy()"
        ).run()

    def select(self, ui, label):
        return next(widget for widget in ui.selectbox if widget.label == label)

    def test_near_misses_have_charts_navigation_bookmarks_and_research_handoff(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.assertEqual(ui.metric[2].value, "0")
        self.bookmark.assert_called_with("AAA", "Company AAA")
        next(button for button in ui.button if button.label == "Next").click().run()
        self.assertEqual(self.select(ui, "Star candidate").value, "BBB.L")
        next(button for button in ui.button if button.label == "Next").click().run()
        self.assertEqual(self.select(ui, "Star candidate").value, "AAA")
        next(button for button in ui.button if button.label == "Open in Individual Stocks").click().run()
        self.assertEqual(ui.session_state["stock_research_queue_label"], "Star Principle candidates")
        self.assertEqual(ui.session_state["stock_research_queue"], ["AAA", "BBB.L"])
        self.assertEqual(ui.session_state["research_area"], "Individual stocks")

    def test_region_status_and_empty_filters_do_not_break_navigation(self):
        ui = self.ui()
        self.select(ui, "Star region").select("Europe").run()
        self.assertFalse(ui.exception)
        self.assertEqual(self.select(ui, "Star candidate").value, "BBB.L")
        self.assertTrue(next(button for button in ui.button if button.label == "Next").disabled)
        self.select(ui, "Evidence status").select("Evidence-qualified").run()
        self.assertFalse(ui.exception)
        self.assertIn("No stocks match", ui.info[0].value)
        self.assertEqual(len(ui.get("plotly_chart")), 0)

    def test_universe_loading_shows_unreviewed_and_does_not_claim_full_coverage(self):
        us = pd.DataFrame({"Symbol": ["AAA", "NEW"], "Name": ["Company A", "New company"]})
        eu = pd.DataFrame({"Symbol": ["BBB.L"], "Name": ["Company B"]})
        with patch.object(self.app, "cached_sp500_holdings", return_value=us):
            with patch.object(self.app, "cached_russell_holdings", return_value=us):
                with patch.object(self.app, "cached_european_holdings", return_value=eu):
                    ui = self.ui()
                    self.select(ui, "Star universe").select("US and European stock universe").run()
                    self.assertFalse(ui.exception)
                    self.assertEqual(ui.metric[0].value, "3")
                    self.assertEqual(ui.metric[1].value, "2")
                    self.select(ui, "Evidence status").select("Unreviewed").run()
                    self.assertEqual(self.select(ui, "Star candidate").value, "NEW")
                    self.assertTrue(any("not all IBKR" in item.value for item in ui.caption))

    def test_price_failure_preserves_evidence_and_bookmark_controls(self):
        self.history.side_effect = StockDataError("Prices unavailable")
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.dataframe), 1)
        self.bookmark.assert_called_once()
        self.assertIn("bookmark controls remain", ui.warning[0].value)
        self.assertFalse(ui.button(key="refresh_star").disabled)

    def test_refresh_keeps_selection_and_does_not_relabel_curated_research(self):
        ui = self.ui()
        self.select(ui, "Star region").select("Europe").run()
        initial = ui.dataframe[0].value.copy()
        self.history.reset_mock()
        with patch.object(self.app.st.cache_data, "clear") as clear:
            ui.button(key="refresh_star").click().run()
        self.assertFalse(ui.exception)
        clear.assert_called_once()
        self.history.assert_called_once_with("BBB.L", "5y", "1d")
        self.assertEqual(self.select(ui, "Star candidate").value, "BBB.L")
        self.assertEqual(self.select(ui, "Star region").value, "Europe")
        pd.testing.assert_frame_equal(ui.dataframe[0].value, initial)
        self.assertTrue(any("curated research" in item.value for item in ui.caption))
        self.assertFalse(ui.button(key="refresh_star").disabled)

    def test_refresh_is_visible_when_no_stocks_match(self):
        ui = self.ui()
        self.select(ui, "Evidence status").select("Evidence-qualified").run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.button(key="refresh_star").disabled)


if __name__ == "__main__":
    unittest.main()
