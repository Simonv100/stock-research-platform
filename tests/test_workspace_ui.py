import unittest
from contextlib import ExitStack
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

from stock_data import StockDataError


class WorkspaceUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.outlook_renderer = app.render_revenue_outlook_research
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.history = pd.DataFrame(
            {"Open": [10, 11], "High": [11, 12], "Low": [9, 10],
             "Close": [10, 11], "Volume": [100, 200]},
            index=pd.to_datetime(["2026-09-10", "2026-09-11"]),
        )
        self.info = {"longName": "Example Company", "currency": "USD",
                     "longBusinessSummary": "A public company description."}
        financials = pd.DataFrame({
            "Period": pd.to_datetime(["2025-12-31"]), "Revenue": [100],
            "Growth": [0.1], "CostOfRevenue": [40], "CostOfRevenuePercent": [0.4],
        })
        replacements = {
            "cached_history": self.history, "cached_info": self.info,
            "cached_shareholder_yield": None, "cached_share_count_history": pd.DataFrame(),
            "cached_financial_history": financials, "cached_business_context": {},
            "cached_catalyst_data": {}, "cached_company_developments": pd.DataFrame(),
            "cached_insider_buys": pd.DataFrame(), "price_chart": go.Figure(),
            "render_bookmark_button": None, "render_scanner_revenue_comparison": None,
            "render_revenue_history": None, "render_cost_of_revenue_history": None,
            "render_key_metrics": None, "render_stock_drivers": None,
            "render_stock_catalysts": None, "render_revenue_acceleration_reasons": None,
            "render_insider_buys": None, "render_shareholder_returns": None,
            "render_revenue_outlook_research": None,
            "generate_stock_drivers": {}, "generate_stock_catalysts": [],
            "generate_revenue_acceleration_reasons": [],
        }
        for name, result in replacements.items():
            self.stack.enter_context(patch.object(self.app, name, return_value=result))
        self.chat = self.stack.enter_context(patch.object(self.app, "render_stock_assistant"))
        self.stack.enter_context(patch.dict("os.environ", {"OPENAI_API_KEY": ""}))

    def test_stock_workspace_keeps_all_research_sections_and_chat(self):
        ui = AppTest.from_string("from app import main\nmain()").run()
        self.assertFalse(ui.exception)
        labels = [tab.label for tab in ui.tabs]
        for label in (
            "Overview", "Financials", "Ownership", "Research", "Revenue",
            "Cost of revenue", "Key metrics", "Insider buys", "Shareholder returns",
            "Short interest", "Catalysts", "Revenue outlook", "Drivers & costs", "News sentiment", "X discussion",
        ):
            self.assertIn(label, labels)
        self.assertIn("Company profile & full description", [item.label for item in ui.expander])
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.chat.assert_called_once()
        self.assertEqual(self.chat.call_args.args[0], "AAPL")
        self.assertEqual(self.chat.call_args.args[1], "Example Company")
        self.assertEqual(sum(widget.label == "OpenAI API key" for widget in ui.text_input), 1)
        self.assertFalse(ui.button(key="refresh_individual").disabled)
        self.app.render_revenue_outlook_research.assert_called_once_with("AAPL", "Example Company")

    def test_revenue_outlook_remains_available_when_stock_prices_fail(self):
        self.app.cached_history.side_effect = StockDataError("No price history")
        ui = AppTest.from_string("from app import main\nmain()").run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No price history" in item.value for item in ui.error))
        self.app.render_revenue_outlook_research.assert_called_once_with("AAPL", "AAPL")

    def test_revenue_outlook_wrapper_uses_shared_key_without_loading_stock_context(self):
        with (
            patch.object(self.app, "render_revenue_outlook_research", self.outlook_renderer),
            patch("revenue_outlook_ui.render_revenue_outlook") as render,
            patch.dict("os.environ", {"OPENAI_REVENUE_MODEL": "gpt-4.1-mini"}),
        ):
            ui = AppTest.from_string(
                "import streamlit as st\n"
                "from app import render_revenue_outlook_research\n"
                "st.session_state['openai_session_key'] = 'test-only-key'\n"
                "render_revenue_outlook_research('GN.CO', 'GN Store Nord')"
            ).run()
        self.assertFalse(ui.exception)
        render.assert_called_once_with("GN.CO", "GN Store Nord", "test-only-key", "gpt-4.1-mini")
        self.app.cached_info.assert_not_called()
        self.app.cached_history.assert_not_called()

    def test_api_key_survives_switching_research_views(self):
        ui = AppTest.from_string("from app import main\nmain()").run()
        key_field = next(widget for widget in ui.text_input if widget.label == "OpenAI API key")
        key_field.input("test-only-key").run()
        self.assertEqual(ui.session_state["openai_session_key"], "test-only-key")
        ui.radio(key="research_area").set_value("Volatility strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["openai_session_key"], "test-only-key")
        ui.radio(key="research_area").set_value("Individual stocks").run()
        self.assertFalse(ui.exception)
        self.assertEqual(sum(widget.label == "OpenAI API key" for widget in ui.text_input), 1)

    def test_revenue_charts_render_only_when_their_tabs_are_open(self):
        ui = AppTest.from_string("from app import main\nmain()")

        def render(workspace="Overview", financials="Revenue", period="Annual"):
            # AppTest does not serialize stateful tab selections between runs.
            ui.session_state["stock_workspace_tab"] = workspace
            ui.session_state["stock_financials_tab"] = financials
            ui.session_state["stock_revenue_period"] = period
            ui.run()

        render()
        self.assertFalse(ui.exception)
        self.app.render_revenue_history.assert_not_called()
        self.app.render_scanner_revenue_comparison.assert_not_called()
        render("Financials")
        self.assertFalse(ui.exception)
        self.app.render_scanner_revenue_comparison.assert_called_once_with("AAPL", "USD")
        self.assertEqual(self.app.render_revenue_history.call_args.args[2], "annual")
        self.app.render_revenue_history.reset_mock()
        render("Financials", period="Quarterly")
        self.assertFalse(ui.exception)
        self.app.render_revenue_history.assert_called_once()
        self.assertEqual(self.app.render_revenue_history.call_args.args[2], "quarterly")
        for workspace, financials in (("Financials", "Cost of revenue"), ("Overview", "Revenue")):
            self.app.render_revenue_history.reset_mock()
            self.app.render_scanner_revenue_comparison.reset_mock()
            render(workspace, financials, "Quarterly")
            self.assertFalse(ui.exception)
            self.app.render_revenue_history.assert_not_called()
            self.app.render_scanner_revenue_comparison.assert_not_called()
        render("Financials", period="Quarterly")
        self.assertFalse(ui.exception)
        self.assertEqual(self.app.render_revenue_history.call_args.args[2], "quarterly")

    def test_druckenmiller_portfolio_placeholder_routes_without_loading_data(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "Druckenmiller-like portfolio"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Druckenmiller-like portfolio")
        self.assertTrue(any("Placeholder only" in item.value for item in ui.info))
        self.assertTrue(any("not a representation" in item.value for item in ui.caption))
        self.assertFalse(ui.get("plotly_chart"))
        self.app.cached_info.assert_not_called()
        self.app.cached_history.assert_not_called()
        self.chat.assert_not_called()
        ui.radio(key="research_area").set_value("ITPM strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "ITPM Strategy")
        ui.radio(key="research_area").set_value("Druckenmiller-like portfolio").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Druckenmiller-like portfolio")

    def test_biotech_placeholder_routes_without_market_data_or_ai_assessments(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "Biotech strategy"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertIn("Biotech strategy", ui.radio(key="research_area").options)
        self.assertEqual(ui.title[0].value, "Biotech Strategy")
        self.assertTrue(any("AI would assess biotech companies" in item.value for item in ui.caption))
        self.assertTrue(any("Planned stock sources: PFC filings and Substack." in item.value for item in ui.caption))
        self.assertTrue(any("Placeholder only" in item.value for item in ui.info))
        self.assertTrue(any("No AI assessments or data requests" in item.value for item in ui.info))
        self.assertFalse(ui.get("plotly_chart"))
        ui.radio(key="research_area").set_value("ITPM strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "ITPM Strategy")
        ui.radio(key="research_area").set_value("Biotech strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Biotech Strategy")
        self.app.cached_info.assert_not_called()
        self.app.cached_history.assert_not_called()
        self.chat.assert_not_called()

    def test_yellow_bricks_placeholder_routes_without_market_data_or_ai(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "Yellow Bricks strategy"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertIn("Yellow Bricks strategy", ui.radio(key="research_area").options)
        self.assertEqual(ui.title[0].value, "Yellow Bricks Strategy")
        self.assertTrue(any("Planned basis: Yellow Bricks." in item.value for item in ui.caption))
        self.assertTrue(any("Placeholder only" in item.value for item in ui.info))
        self.assertTrue(any("No analysis or data requests" in item.value for item in ui.info))
        self.assertFalse(ui.get("plotly_chart"))
        ui.radio(key="research_area").set_value("Biotech strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Biotech Strategy")
        self.assertTrue(any("PFC filings and Substack" in item.value for item in ui.caption))
        ui.radio(key="research_area").set_value("Yellow Bricks strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Yellow Bricks Strategy")
        self.app.cached_info.assert_not_called()
        self.app.cached_history.assert_not_called()
        self.chat.assert_not_called()

    def test_tax_loss_harvesting_placeholder_routes_without_market_data_or_ai(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "Tax loss harvesting strategy"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertIn("Tax loss harvesting strategy", ui.radio(key="research_area").options)
        self.assertEqual(ui.title[0].value, "Tax Loss Harvesting Strategy")
        self.assertTrue(any("Placeholder only" in item.value for item in ui.info))
        self.assertTrue(any("Tax jurisdiction" in item.value for item in ui.info))
        self.assertTrue(any("No tax calculations" in item.value for item in ui.info))
        self.assertFalse(ui.get("plotly_chart"))
        ui.radio(key="research_area").set_value("Yellow Bricks strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Yellow Bricks Strategy")
        ui.radio(key="research_area").set_value("Tax loss harvesting strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Tax Loss Harvesting Strategy")
        self.app.cached_info.assert_not_called()
        self.app.cached_history.assert_not_called()
        self.chat.assert_not_called()

    def test_early_breakout_route_is_on_demand_and_preserves_existing_navigation(self):
        with (
            patch.object(self.app, "load_breakout_scan") as scan,
            patch.object(self.app, "cached_breakout_history") as history,
            patch.object(self.app, "cached_breakout_reference_history") as reference,
        ):
            ui = AppTest.from_string("from app import main\nmain()")
            ui.session_state["research_area"] = "Early breakout strategy"
            ui.run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.title[0].value, "Early breakout strategy")
            self.assertIn("U-recovery scanner", ui.radio(key="research_area").options)
            self.assertTrue(any(button.label == "Run breakout scan" for button in ui.button))
            scan.assert_not_called()
            history.assert_not_called()
            reference.assert_not_called()
            self.chat.assert_not_called()
            ui.radio(key="research_area").set_value("Tax loss harvesting strategy").run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.title[0].value, "Tax Loss Harvesting Strategy")
            ui.radio(key="research_area").set_value("Early breakout strategy").run()
            self.assertFalse(ui.exception)
            scan.assert_not_called()

    def test_ip_strategy_routes_without_data_then_hands_off_to_individual_stock(self):
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["research_area"] = "IP-backed turnarounds"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "IP-backed turnarounds")
        self.assertIn("Income strategies", ui.radio(key="research_area").options)
        self.assertIn("U-recovery scanner", ui.radio(key="research_area").options)
        self.app.cached_history.assert_not_called()
        self.app.cached_info.assert_not_called()
        self.chat.assert_not_called()
        ui.selectbox(key="ip_turnaround_symbol").select("GN.CO").run()
        ui.button(key="ip_turnaround_open_research").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "Global Stock Research")
        self.assertEqual(ui.radio(key="research_area").value, "Individual stocks")
        self.assertEqual(ui.session_state["stock_query"], "GN.CO")
        self.assertEqual(
            ui.session_state["stock_research_queue"], ["SSYS", "GN.CO", "OLED", "KLIC", "PACB"],
        )
        self.assertEqual(self.chat.call_args.args[0], "GN.CO")
        ui.radio(key="research_area").set_value("IP-backed turnarounds").run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.dataframe[0].value), 5)
        ui.radio(key="research_area").set_value("ITPM strategy").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "ITPM Strategy")

    def test_chart_layout_includes_the_correct_stock_and_evidence(self):
        ui = AppTest.from_string(
            "import pandas as pd\n"
            "from app import render_chart_and_assistant\n"
            "render_chart_and_assistant('BMW.DE', 'BMW', {}, pd.DataFrame(), {'Signal': 'Test'})"
        ).run()
        self.assertFalse(ui.exception)
        self.chat.assert_called_once()
        self.assertEqual(self.chat.call_args.args[0], "BMW.DE")
        self.assertEqual(self.chat.call_args.args[-1], {"Signal": "Test"})

    def test_strategy_research_selection_and_handoff_preserve_stock_identity(self):
        ui = AppTest.from_string(
            "import pandas as pd\n"
            "from app import render_strategy_candidate_research\n"
            "render_strategy_candidate_research(pd.DataFrame(["
            "{'Symbol':'AAA', 'Name':'Company A'},"
            "{'Symbol':'BBB.L', 'Name':'Company B'}]), 'example', 'Example candidates')"
        ).run()
        self.assertFalse(ui.exception)
        ui.selectbox(key="example_research_symbol").select("BBB.L").run()
        self.assertFalse(ui.exception)
        self.assertEqual(self.chat.call_args.args[0], "BBB.L")
        ui.button(key="example_open_research").click().run()
        self.assertEqual(ui.session_state["stock_research_queue"], ["AAA", "BBB.L"])
        self.assertEqual(ui.session_state["stock_query"], "BBB.L")
        self.assertEqual(ui.session_state["stock_research_queue_label"], "Example candidates")


class ChatContextIntegrationTests(unittest.TestCase):
    def test_context_loads_cached_public_sections_and_reports_partial_data(self):
        import app
        history = pd.DataFrame({"Close": [10]}, index=pd.to_datetime(["2026-09-11"]))
        with ExitStack() as stack:
            stack.enter_context(patch.object(app, "cached_financial_history", return_value=pd.DataFrame({
                "Period": pd.to_datetime(["2025-12-31"]), "Revenue": [100], "Growth": [0.1],
            })))
            stack.enter_context(patch.object(app, "cached_stock_revenue_growth", return_value={
                "RevenueGrowth": 0.1, "RevenuePeriod": "Four quarters ended 2026-06-30",
            }))
            stack.enter_context(patch.object(app, "cached_company_news",
                                            side_effect=StockDataError("upstream detail")))
            builder = stack.enter_context(patch("stock_chat.build_stock_context", return_value={}))
            app.load_stock_chat_context("EX", "Example", {"currency": "USD"}, history,
                                        {"Signal": "Early right side"})
        args = builder.call_args.args
        self.assertEqual(args[0], "EX")
        sections = args[-1]
        self.assertEqual(sections["annual_financials"][0]["Revenue"], 100)
        self.assertEqual(sections["rolling_growth"]["RevenueGrowth"], 0.1)
        self.assertEqual(sections["research_view"]["Signal"], "Early right side")
        self.assertEqual(sections["unavailable"], ["news: provider data unavailable"])
        self.assertEqual(sections["data_cache_hours"], 24)


if __name__ == "__main__":
    unittest.main()
