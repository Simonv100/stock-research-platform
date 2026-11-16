import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


class CacheControlsTests(unittest.TestCase):
    def test_all_streamlit_data_caches_use_24_hours(self):
        import app
        self.assertEqual(app.CACHE_TTL_SECONDS, 86400)
        cached_functions = [
            value for name, value in vars(app).items()
            if name.startswith("cached_") and hasattr(value, "_info")
        ]
        self.assertGreater(len(cached_functions), 20)
        for function in cached_functions:
            with self.subTest(function=function.__name__):
                self.assertEqual(function._info.ttl, 86400)

    def test_cache_hit_at_23_hours_expires_at_24_hours(self):
        import app
        import streamlit as st
        from streamlit.runtime.caching import cache_utils
        calls = []

        @st.cache_data(ttl=app.CACHE_TTL_SECONDS, show_spinner=False)
        def cached_probe():
            calls.append(True)
            return len(calls)

        with patch.object(cache_utils, "TTLCACHE_TIMER", return_value=0) as clock:
            try:
                self.assertEqual(cached_probe(), 1)
                clock.return_value = 23 * 3600
                self.assertEqual(cached_probe(), 1)
                clock.return_value = 24 * 3600 + 1
                self.assertEqual(cached_probe(), 2)
            finally:
                cached_probe.clear()

    def test_manual_refresh_is_available_even_with_a_recent_refresh(self):
        ui = AppTest.from_string(
            "from app import render_cache_controls\nrender_cache_controls()"
        )
        for hours in (0, 13, 23, 24):
            ui.session_state["manual_cache_refresh_at"] = datetime.now(timezone.utc) - timedelta(hours=hours)
            ui.run()
            self.assertFalse(ui.exception)
            self.assertFalse(ui.button(key="refresh_all_cached_data").disabled)
        ui.session_state["manual_cache_refresh_at"] = None
        ui.run()
        self.assertTrue(any("24 hours" in item.value for item in ui.caption))
        self.assertTrue(any("anytime" in item.value for item in ui.caption))

    def test_page_and_sidebar_refresh_really_bypass_cache_and_keep_session_data(self):
        import app
        app.cached_info.clear()
        self.addCleanup(app.cached_info.clear)
        script = (
            "import streamlit as st\n"
            "from app import render_cache_controls, render_page_header, cached_info\n"
            "with st.sidebar:\n"
            "    render_cache_controls()\n"
            "render_page_header('Test research', 'test')\n"
            "st.write(cached_info('CACHE-REFRESH-TEST')['longName'])"
        )
        with patch.object(app, "get_company_info", side_effect=[
            {"longName": "First fetch"}, {"longName": "Second fetch"}, {"longName": "Third fetch"},
        ]) as provider:
            ui = AppTest.from_string(script).run()
            self.assertFalse(ui.exception)
            self.assertEqual(provider.call_count, 1)
            ui.session_state["star_symbol"] = "BBB.L"
            ui.session_state["openai_session_key"] = "test-only-key"
            chat = {"BBB.L": {"messages": [{"role": "user", "content": "Explain the revenue"}]}}
            ui.session_state["_stock_chat_sessions"] = chat
            ui.run()
            self.assertEqual(provider.call_count, 1)
            for key, count, output in (
                ("refresh_test", 2, "Second fetch"),
                ("refresh_all_cached_data", 3, "Third fetch"),
            ):
                ui.button(key=key).click().run()
                self.assertFalse(ui.exception)
                self.assertEqual(provider.call_count, count)
                self.assertTrue(any(item.value == output for item in ui.markdown))
                self.assertFalse(ui.button(key=key).disabled)
                self.assertEqual(ui.session_state["star_symbol"], "BBB.L")
                self.assertEqual(ui.session_state["openai_session_key"], "test-only-key")
                self.assertEqual(ui.session_state["_stock_chat_sessions"], chat)
                self.assertTrue(any("Shared data caches cleared" in item.value for item in ui.info))
                ui.run()
                self.assertEqual(provider.call_count, count)

    def test_refresh_invalidates_aggregate_and_per_symbol_caches(self):
        import app
        import pandas as pd
        caches = (
            app.cached_stock_revenue_growth, app.cached_revenue_growth_scan,
            app.cached_adr_dividend, app.cached_adr_scan,
        )
        for cache in caches:
            cache.clear()
            self.addCleanup(cache.clear)
        with patch.object(app, "get_revenue_growth_scan", return_value=pd.DataFrame([
            {"Symbol": "EX", "RevenueGrowth": 0.1},
        ])) as revenue, patch.object(app, "get_adr_dividend", return_value={"TTMCash": 2}) as adr:
            for _ in range(2):
                app.cached_revenue_growth_scan(("EX",), app.REVENUE_MODEL_VERSION)
                app.cached_adr_scan(("EX",), "2026-09-15")
            self.assertEqual(revenue.call_count, 1)
            self.assertEqual(adr.call_count, 1)
            ui = AppTest.from_string(
                "from app import render_cache_controls\nrender_cache_controls()"
            ).run()
            ui.button(key="refresh_all_cached_data").click().run()
            self.assertFalse(ui.exception)
            app.cached_revenue_growth_scan(("EX",), app.REVENUE_MODEL_VERSION)
            app.cached_adr_scan(("EX",), "2026-09-15")
            self.assertEqual(revenue.call_count, 2)
            self.assertEqual(adr.call_count, 2)

    def test_refresh_does_not_trigger_paid_news_analysis(self):
        import app
        with ExitStack() as stack:
            news = stack.enter_context(patch.object(app, "cached_company_news"))
            paid = stack.enter_context(patch.object(app, "cached_news_assessment"))
            cleared = stack.enter_context(patch.object(app.st.cache_data, "clear"))
            ui = AppTest.from_string(
                "import streamlit as st\n"
                "from app import render_page_header, render_company_news\n"
                "render_page_header('Example', 'news_test')\n"
                "render_company_news('EX', 'Example')"
            ).run()
            ui.session_state["openai_session_key"] = "test-only-key"
            ui.session_state["news_auto_summary"] = True
            ui.session_state["news_loaded_requests"] = {("EX", "Example", "gpt-4.1-mini", app.NEWS_ANALYSIS_VERSION)}
            ui.button(key="refresh_news_test").click().run()
            self.assertFalse(ui.exception)
            cleared.assert_called_once()
            news.assert_not_called()
            paid.assert_not_called()
            self.assertFalse(ui.session_state["news_auto_summary"])
            self.assertEqual(ui.session_state["news_loaded_requests"], set())
            self.assertTrue(any("News summaries are paused" in item.value for item in ui.info))

    def test_all_data_page_headers_offer_refresh(self):
        import app
        from stock_data import StockDataError
        cases = (
            ("render_bookmarks", "bookmarks", "list_bookmarks"),
            ("render_inflection_scanner", "u_recovery", "cached_russell_holdings"),
            ("render_etf_explorer", "etf_atlas", "cached_history"),
            ("render_other_charts", "other_charts", "cached_sp500_holdings"),
            ("render_income_strategy", "income", "INFRASTRUCTURE_COMPANIES"),
            ("render_fashion_trend_strategy", "fashion", "FASHION_COMPANIES"),
        )
        # Stop after the header where possible; data failures must not hide Refresh.
        for function, key, dependency in cases:
            with self.subTest(page=function), ExitStack() as stack:
                if dependency in ("cached_russell_holdings", "cached_history", "adr_catalog"):
                    stack.enter_context(patch.object(app, dependency, side_effect=StockDataError("Unavailable")))
                elif dependency in ("FASHION_COMPANIES", "INFRASTRUCTURE_COMPANIES"):
                    stack.enter_context(patch.object(app, dependency, []))
                    if key == "income":
                        stack.enter_context(patch.object(app, "adr_catalog", side_effect=StockDataError("Unavailable")))
                else:
                    stack.enter_context(patch.object(app, dependency, return_value=[]))
                script = f"from app import {function}\n{function}()"
                ui = AppTest.from_string(script).run()
                self.assertFalse(ui.exception)
                self.assertFalse(ui.button(key=f"refresh_{key}").disabled)


if __name__ == "__main__":
    unittest.main()
