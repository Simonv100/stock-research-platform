import unittest
from io import StringIO
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError
from test_volatility_strategy import pilot_fixture


class VolatilityStrategyUITests(unittest.TestCase):
    def render(self):
        return AppTest.from_string(
            "from app import render_volatility_strategy\nrender_volatility_strategy()"
        ).run()

    def test_empty_workspace_has_explicit_run_button_and_no_download(self):
        with patch("volatility_strategy_ui.read_saved_prices", return_value=None), \
                patch("volatility_strategy_ui.refresh_saved_prices") as refresh:
            ui = self.render()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Volatility Strategy")
        self.assertTrue(any("first sector analysis" in item.value for item in ui.info))
        self.assertFalse(ui.button(key="volatility_refresh").disabled)
        refresh.assert_not_called()

    def test_saved_results_show_pockets_leads_charts_and_filter_without_download(self):
        with patch("volatility_strategy_ui.read_saved_prices", return_value=pilot_fixture()), \
                patch("volatility_strategy_ui.refresh_saved_prices") as refresh:
            ui = self.render()
            self.assertFalse(ui.exception)
            self.assertEqual([metric.value for metric in ui.metric], ["10/10", "2", "1", "2"])
            self.assertEqual(len(ui.get("plotly_chart")), 3)
            self.assertIn("ASML", ui.success[0].value)
            self.assertEqual(len(ui.dataframe[1].value), 10)
            ui.selectbox(key="volatility_pocket").select("Process control").run()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.dataframe[1].value), 3)
            self.assertTrue(any("No quiet-peer" in item.value for item in ui.info))
            refresh.assert_not_called()

    def test_refresh_fetches_once_and_reports_failure_without_fake_results(self):
        with patch("volatility_strategy_ui.read_saved_prices", return_value=None), \
                patch("volatility_strategy_ui.refresh_saved_prices", side_effect=StockDataError("Provider unavailable")) as refresh:
            ui = self.render()
            ui.button(key="volatility_refresh").click().run()
        self.assertFalse(ui.exception)
        refresh.assert_called_once()
        self.assertIn("Provider unavailable", ui.error[0].value)
        self.assertFalse(ui.dataframe)
        self.assertFalse(ui.button(key="volatility_refresh").disabled)

    def test_navigation_hands_selected_company_to_existing_research_workspace(self):
        import app
        with patch("volatility_strategy_ui.read_saved_prices", return_value=pilot_fixture()), \
                patch.object(app, "open_stock_research") as handoff:
            ui = self.render()
            ui.selectbox(key="volatility_symbol").select("ASML").run()
            ui.button(key="volatility_open_research").click().run()
        self.assertFalse(ui.exception)
        args = handoff.call_args.args
        self.assertEqual(args[0], "ASML")
        self.assertIn("ASML", args[1])
        self.assertEqual(args[2], "Semiconductor equipment pilot")

    def test_stale_snapshot_and_missing_coverage_are_visible(self):
        snapshot = pilot_fixture()
        snapshot.prices = snapshot.prices.drop(columns=["ASML"])
        with patch("volatility_strategy_ui.read_saved_prices", return_value=snapshot), \
                patch("volatility_strategy_ui.new_york_today", return_value=snapshot.prices.index[-1] + pd.Timedelta(days=20)):
            ui = self.render()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Historical snapshot" in item.value for item in ui.warning))
        self.assertTrue(any("Partial coverage" in item.value for item in ui.warning))

    def test_price_direction_labels_and_counts_are_visible_and_exported(self):
        with patch("volatility_strategy_ui.read_saved_prices", return_value=pilot_fixture(-1)), \
                patch("volatility_strategy_ui.st.download_button") as download:
            ui = self.render()
        self.assertFalse(ui.exception)
        stocks = ui.dataframe[1].value.set_index("Symbol")
        self.assertEqual(stocks.loc["AMAT", "PriceInformation"], "Negative (down)")
        self.assertLess(stocks.loc["AMAT", "Return5D"], 0)
        self.assertEqual(ui.dataframe[0].value.iloc[0]["NegativeUnusual"], 2)
        self.assertTrue(any("not verified good/bad news" in item.value for item in ui.caption))
        exported = pd.read_csv(StringIO(download.call_args.args[1].decode("utf-8"))).set_index("Symbol")
        self.assertEqual(exported.loc["AMAT", "PriceInformation"], "Negative (down)")
        self.assertAlmostEqual(exported.loc["AMAT", "Return5D"] * 100, stocks.loc["AMAT", "Return5D"])


if __name__ == "__main__":
    unittest.main()
