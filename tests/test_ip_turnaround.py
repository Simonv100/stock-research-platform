import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch
from urllib.parse import urlparse

from streamlit.testing.v1 import AppTest

from ip_turnaround import (
    IP_EVALUATION_CHECKLIST,
    IP_RESEARCH_AS_OF,
    IP_RESEARCH_QUEUE_LABEL,
    IP_RESEARCH_TIERS,
    IP_TURNAROUND_CANDIDATES,
)


class IPTurnaroundCatalogTests(unittest.TestCase):
    def test_shortlist_has_distinct_research_categories_not_a_sonos_position(self):
        candidates = {candidate.symbol: candidate for candidate in IP_TURNAROUND_CANDIDATES}
        self.assertEqual(len(candidates), len(IP_TURNAROUND_CANDIDATES))
        self.assertEqual(set(candidates), {"SSYS", "GN.CO", "OLED", "KLIC", "PACB"})
        self.assertEqual(
            {candidate.symbol for candidate in candidates.values()
             if candidate.tier == "Core research candidate"},
            {"SSYS", "GN.CO", "OLED"},
        )
        self.assertEqual(candidates["KLIC"].tier, "More-confirmed recovery")
        self.assertEqual(candidates["PACB"].tier, "High-risk watchlist")

    def test_every_candidate_has_dated_primary_sources_and_complete_research(self):
        research_date = date.fromisoformat(IP_RESEARCH_AS_OF)
        self.assertEqual(research_date, date(2026, 9, 25))
        for candidate in IP_TURNAROUND_CANDIDATES:
            with self.subTest(symbol=candidate.symbol):
                self.assertIn(candidate.tier, IP_RESEARCH_TIERS)
                for field in (
                    "name", "sector", "ip_case", "recovery_case",
                    "financial_evidence", "risks", "watch_for",
                ):
                    self.assertTrue(getattr(candidate, field).strip())
                self.assertGreaterEqual(len(candidate.sources), 2)
                for source in candidate.sources:
                    self.assertTrue(source.label)
                    self.assertLessEqual(date.fromisoformat(source.date), research_date)
                    url = urlparse(source.url)
                    self.assertEqual(url.scheme, "https")
                    self.assertTrue(url.hostname)

    def test_material_caveats_and_non_scored_evaluation_are_preserved(self):
        candidates = {candidate.symbol: candidate for candidate in IP_TURNAROUND_CANDIDATES}
        self.assertIn("hearing-product IP leave", candidates["GN.CO"].risks)
        self.assertIn("pending $42.5m", candidates["SSYS"].risks)
        self.assertIn("catch-up", candidates["OLED"].risks)
        self.assertIn("2028", candidates["PACB"].risks)
        self.assertIn("$641m", candidates["PACB"].financial_evidence)
        self.assertEqual(len(IP_EVALUATION_CHECKLIST), 6)
        checklist = " ".join(text for item in IP_EVALUATION_CHECKLIST for text in item)
        self.assertIn("need not already be visible", checklist)
        self.assertIn("guaranteed patent-value floor", checklist)
        self.assertIn("An exact U-shape is not required", checklist)


class IPTurnaroundUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.bookmark = self.stack.enter_context(patch.object(app, "render_bookmark_button"))
        self.no_fetch = []
        for name in ("cached_history", "cached_info", "render_stock_assistant", "get_inflection_scan"):
            self.no_fetch.append(self.stack.enter_context(patch.object(
                app, name, side_effect=AssertionError("Curated page must not fetch or call AI"),
            )))

    def ui(self):
        return AppTest.from_string(
            "from app import render_ip_turnaround_strategy\nrender_ip_turnaround_strategy()"
        ).run()

    def test_initial_page_shows_all_research_without_loading_prices_or_ai(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.title[0].value, "IP-backed turnarounds")
        self.assertEqual(
            ui.dataframe[0].value["Symbol"].tolist(), ["SSYS", "GN.CO", "OLED", "KLIC", "PACB"],
        )
        self.assertTrue(any("not an automated screener" in item.value for item in ui.info))
        self.assertTrue(any(IP_RESEARCH_AS_OF in item.value for item in ui.caption))
        self.assertEqual(len(ui.get("link_button")), 3)
        self.assertEqual(len(ui.get("plotly_chart")), 0)
        self.assertEqual(len(ui.checkbox), 0)
        self.bookmark.assert_called_once_with("SSYS", "Stratasys")
        for loader in self.no_fetch:
            loader.assert_not_called()

    def test_category_and_sector_filters_intersect_and_handle_no_matches(self):
        ui = self.ui()
        ui.selectbox(key="ip_turnaround_category").select("Core research candidate").run()
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["SSYS", "GN.CO", "OLED"])
        ui.selectbox(key="ip_turnaround_sector").select("Life-science instruments").run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No researched companies" in item.value for item in ui.info))
        self.assertFalse(ui.dataframe)
        self.assertFalse(any(button.key == "ip_turnaround_open_research" for button in ui.button))
        ui.selectbox(key="ip_turnaround_category").select("All categories").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["PACB"])
        self.assertEqual(ui.selectbox(key="ip_turnaround_symbol").value, "PACB")

    def test_currency_evidence_is_not_interpreted_as_inline_math(self):
        ui = self.ui()
        evidence = next(item.value for item in ui.markdown if "Q2 2026 revenue was" in item.value)
        self.assertIn(r"\$137.6m", evidence)
        self.assertIn(r"\$138.1m", evidence)
        self.assertIn(r"\$212.5m", evidence)
        self.assertIn(r"\$18.7m", evidence)
        self.assertNotIn("$", evidence.replace(r"\$", ""))

    def test_selection_uses_correct_evidence_sources_and_bookmark(self):
        ui = self.ui()
        ui.selectbox(key="ip_turnaround_symbol").select("GN.CO").run()
        self.assertFalse(ui.exception)
        self.assertIn("GN Store Nord (GN.CO)", [item.value for item in ui.subheader])
        self.assertTrue(any("hearing-product IP leave" in item.value for item in ui.markdown))
        self.assertEqual(len(ui.get("link_button")), 3)
        self.bookmark.assert_called_with("GN.CO", "GN Store Nord")
        ui.selectbox(key="ip_turnaround_sector").select("Display materials and technology").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="ip_turnaround_symbol").value, "OLED")
        self.assertEqual(len(ui.get("link_button")), 2)

    def test_high_risk_case_is_explicit_and_not_promoted_to_core(self):
        ui = self.ui()
        ui.selectbox(key="ip_turnaround_category").select("High-risk watchlist").run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.dataframe[0].value["Symbol"].tolist(), ["PACB"])
        self.assertTrue(any("2028" in item.value and "dilution" in item.value for item in ui.warning))
        self.assertTrue(any("High-risk watchlist" in item.value for item in ui.caption))

    def test_handoff_reuses_filtered_queue_without_changing_it_on_browsing(self):
        ui = self.ui()
        ui.session_state["stock_research_queue"] = ["EXISTING"]
        ui.session_state["stock_research_queue_label"] = "Existing research"
        ui.session_state["search_results"] = ["old search"]
        ui.selectbox(key="ip_turnaround_category").select("Core research candidate").run()
        ui.selectbox(key="ip_turnaround_symbol").select("GN.CO").run()
        self.assertEqual(ui.session_state["stock_research_queue"], ["EXISTING"])
        ui.button(key="ip_turnaround_open_research").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["research_area"], "Individual stocks")
        self.assertEqual(ui.session_state["stock_query"], "GN.CO")
        self.assertEqual(ui.session_state["stock_research_symbol"], "GN.CO")
        self.assertEqual(ui.session_state["stock_research_queue"], ["SSYS", "GN.CO", "OLED"])
        self.assertEqual(ui.session_state["stock_research_queue_label"], IP_RESEARCH_QUEUE_LABEL)
        self.assertNotIn("search_results", ui.session_state)

    def test_stale_selection_is_repaired_and_refresh_does_not_redate_research(self):
        ui = AppTest.from_string(
            "from app import render_ip_turnaround_strategy\nrender_ip_turnaround_strategy()"
        )
        ui.session_state["ip_turnaround_symbol"] = "NOT_IN_SHORTLIST"
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox(key="ip_turnaround_symbol").value, "SSYS")
        with patch.object(self.app.st.cache_data, "clear") as clear:
            ui.button(key="refresh_ip_turnarounds").click().run()
        clear.assert_called_once()
        self.assertFalse(ui.exception)
        self.assertTrue(any(
            f"Research as of {IP_RESEARCH_AS_OF}" in item.value for item in ui.caption
        ))
        for loader in self.no_fetch:
            loader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
