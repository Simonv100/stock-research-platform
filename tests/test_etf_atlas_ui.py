import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from streamlit.testing.v1 import AppTest

import bookmarks
from bookmarks import BookmarkError, add_bookmark, list_bookmarks
from etf_catalog import etf_catalog
from stock_data import StockDataError


class EtfAtlasUITests(unittest.TestCase):
    def setUp(self):
        import app

        self.app = app
        self.render_chart_and_assistant = app.render_chart_and_assistant
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(
            bookmarks, "BOOKMARKS_PATH", Path(folder) / "bookmarks.sqlite3",
        ))
        self.catalog = etf_catalog()
        self.history = self.stack.enter_context(patch.object(
            app, "cached_history", return_value=pd.DataFrame(
                {"Close": [100.0, 110.0], "Volume": [100, 200], "MA200": [95.0, 96.0]},
                index=pd.to_datetime(["2026-09-10", "2026-09-11"]),
            ),
        ))
        self.info = self.stack.enter_context(patch.object(app, "cached_info", return_value={}))
        self.chart = self.stack.enter_context(patch.object(app, "render_chart_and_assistant"))
        self.stack.enter_context(patch.object(app, "render_etf_holdings"))

    def ui(self, entry=None):
        ui = AppTest.from_string("from app import render_etf_explorer\nrender_etf_explorer()")
        if entry:
            ui.session_state["atlas_entry"] = entry
        return ui.run()

    @staticmethod
    def selectbox(ui, label):
        return next(widget for widget in ui.selectbox if widget.label == label)

    @staticmethod
    def queue(ui):
        return next(frame.value for frame in ui.dataframe if "Symbol" in frame.value.columns)

    def test_country_selector_queue_and_filters_only_use_mapped_etfs(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        mapped = [row for row in self.catalog if row["Universe"] == "Country markets" and row["Symbol"]]
        self.assertEqual(self.queue(ui)["Symbol"].tolist(), [row["Symbol"] for row in mapped])
        self.assertEqual(len(self.selectbox(ui, "Market category").options), len(mapped))
        self.assertFalse(any("no ETF proxy" in option for option in self.selectbox(ui, "Market category").options))
        self.assertNotIn("Zimbabwe", self.queue(ui)["Category"].tolist())
        self.assertEqual(
            self.selectbox(ui, "Market group").options,
            ["All"] + sorted({row["Market group"] for row in mapped}),
        )
        self.assertTrue(any("without a mapped ETF are hidden" in item.value for item in ui.caption))
        self.assertFalse(ui.button(key="refresh_etf_atlas").disabled)

    def test_old_unmapped_selection_is_repaired_and_navigation_wraps_over_mapped_only(self):
        ui = self.ui("Country markets|Zimbabwe")
        mapped = [row for row in self.catalog if row["Universe"] == "Country markets" and row["Symbol"]]
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["atlas_entry"], mapped[0]["Entry ID"])
        next(button for button in ui.button if button.label == "←").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["atlas_entry"], mapped[-1]["Entry ID"])
        self.history.assert_called_with(mapped[-1]["Symbol"], "5y", "1d")
        next(button for button in ui.button if button.label == "→").click().run()
        self.assertEqual(ui.session_state["atlas_entry"], mapped[0]["Entry ID"])

    def test_country_geographic_filters_still_combine(self):
        ui = self.ui()
        self.selectbox(ui, "Market group").select("Developed").run()
        self.selectbox(ui, "Region").select("Europe").run()
        self.assertFalse(ui.exception)
        queue = self.queue(ui)
        self.assertTrue(queue["Symbol"].notna().all())
        self.assertTrue(queue["Market group"].eq("Developed").all())
        self.assertTrue(queue["Region"].eq("Europe").all())

    def test_empty_filter_has_main_page_explanation_and_does_not_fetch(self):
        template = next(row for row in self.catalog if row["Universe"] == "Country markets")
        catalog = [
            {**template, "Entry ID": "Country markets|A", "Category": "A",
             "Symbol": "AAA", "Market group": "Developed", "Region": "Europe"},
            {**template, "Entry ID": "Country markets|B", "Category": "B",
             "Symbol": "BBB", "Market group": "Emerging", "Region": "Americas"},
        ]
        with patch.object(self.app, "etf_catalog", return_value=catalog):
            ui = self.ui()
            self.selectbox(ui, "Market group").select("Developed").run()
            self.history.reset_mock()
            self.selectbox(ui, "Region").select("Americas").run()
            self.assertFalse(ui.exception)
            self.assertTrue(any("No countries with a mapped ETF" in item.value for item in ui.main.info))
            self.assertFalse(any(widget.label == "Market category" for widget in ui.selectbox))
            self.history.assert_not_called()
            self.assertFalse(ui.button(key="refresh_etf_atlas").disabled)
            self.selectbox(ui, "Region").select("Europe").run()
            self.assertFalse(ui.exception)
            self.assertEqual(ui.session_state["atlas_entry"], "Country markets|A")

    def test_no_mapped_countries_is_safe_and_source_catalog_is_not_modified(self):
        template = next(row for row in self.catalog if row["Universe"] == "Country markets")
        catalog = [{**template, "Symbol": symbol} for symbol in (None, "", "   ")]
        with patch.object(self.app, "etf_catalog", return_value=catalog):
            ui = self.ui("Country markets|Zimbabwe")
        self.assertFalse(ui.exception)
        self.assertTrue(any("No countries with a mapped ETF" in item.value for item in ui.main.info))
        self.assertEqual([row["Symbol"] for row in catalog], [None, "", "   "])
        self.history.assert_not_called()
        self.assertTrue(any(row["Country"] == "Zimbabwe" for row in etf_catalog()))
        self.assertFalse(any(button.key and button.key.startswith("bookmark_toggle_") for button in ui.button))

    def test_full_gics_hierarchy_keeps_unmapped_entries(self):
        ui = self.ui()
        next(widget for widget in ui.radio if widget.label == "Taxonomy view").set_value("Full GICS hierarchy").run()
        self.assertFalse(ui.exception)
        entries = [row for row in self.catalog if row["Universe"] == "Full GICS hierarchy"]
        self.assertEqual(len(self.selectbox(ui, "Market category").options), len(entries))
        unmapped = next(row for row in entries if not row["Symbol"])
        self.selectbox(ui, "Market category").select(unmapped["Entry ID"]).run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("No suitable active ETF proxy" in item.value for item in ui.info))
        self.assertFalse(any(button.key and button.key.startswith("bookmark_toggle_") for button in ui.button))

    def test_temporarily_unavailable_prices_do_not_hide_a_mapped_etf(self):
        self.history.side_effect = StockDataError("Provider temporarily unavailable")
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertIn("EWA", self.selectbox(ui, "Market category").options[0])
        self.assertTrue(any("temporarily unavailable" in item.value for item in ui.error))
        self.assertFalse(ui.button(key="refresh_etf_atlas").disabled)

    def test_incomplete_price_history_keeps_selection_navigation_and_refresh(self):
        valid = self.history.return_value.copy()
        cases = (
            pd.DataFrame(),
            valid.iloc[:0],
            valid.iloc[:1],
            valid.assign(Close=[None, None]),
            valid.assign(Close=["unavailable", "110"]),
        )
        for history in cases:
            with self.subTest(history=history.to_dict()):
                self.history.return_value = history
                ui = self.ui()
                self.assertFalse(ui.exception)
                self.assertTrue(any("EWA" in item.value for item in ui.error))
                self.assertTrue(any("Refresh data" in item.value for item in ui.error))
                self.assertEqual(ui.session_state["atlas_entry"], "Country markets|Australia")
                self.assertFalse(self.selectbox(ui, "Market category").disabled)
                self.assertFalse(ui.button(key="refresh_etf_atlas").disabled)
                navigation = [button for button in ui.button if button.label in ("←", "→")]
                self.assertEqual(len(navigation), 2)
                self.assertTrue(all(not button.disabled for button in navigation))
                self.assertFalse(ui.metric)
                self.chart.assert_not_called()
                self.info.assert_not_called()

    def test_navigation_and_refresh_can_recover_from_incomplete_history(self):
        valid = self.history.return_value.copy()
        self.history.side_effect = [valid.iloc[:1], valid, valid.iloc[:1], valid]
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        next(button for button in ui.button if button.label == "→").click().run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.error)
        self.assertTrue(ui.metric)
        next(button for button in ui.button if button.label == "←").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(ui.error)
        selected = ui.session_state["atlas_entry"]
        ui.button(key="refresh_etf_atlas").click().run()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.error)
        self.assertEqual(ui.session_state["atlas_entry"], selected)
        self.assertTrue(ui.metric)
        self.assertEqual(self.chart.call_count, 2)

    def test_short_history_without_ma200_shows_unavailable_ma_not_an_exception(self):
        self.history.return_value = self.history.return_value.assign(MA200=float("nan"))
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertFalse(ui.error)
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "vs. 200-day MA").value, "N/A")
        self.assertEqual(next(metric for metric in ui.metric if metric.label == "Period return").value, "10.0%")
        self.chart.assert_called_once()

    def test_etf_bookmark_persists_and_can_be_browsed_and_removed_in_bookmarks(self):
        ui = self.ui()
        button = ui.button(key="bookmark_toggle_EWA")
        self.assertEqual(button.label, "Bookmark ETF")
        button.click().run()
        self.assertFalse(ui.exception)
        fund = next(row["Fund"] for row in self.catalog if row["Symbol"] == "EWA")
        saved = list_bookmarks()
        self.assertEqual([(row["symbol"], row["name"]) for row in saved], [("EWA", fund)])
        fresh_ui = self.ui()
        self.assertEqual(fresh_ui.button(key="bookmark_toggle_EWA").label, "Remove bookmark")
        self.assertEqual(list_bookmarks(), saved)

        saved_ui = AppTest.from_string("from app import render_bookmarks\nrender_bookmarks()").run()
        self.assertFalse(saved_ui.exception)
        self.assertEqual(saved_ui.selectbox(key="bookmark_symbol").value, "EWA")
        self.assertEqual(saved_ui.dataframe[0].value["Symbol"].tolist(), ["EWA"])
        self.assertEqual(self.chart.call_args.args[:2], ("EWA", fund))
        saved_ui.button(key="bookmark_toggle_EWA").click().run()
        self.assertFalse(saved_ui.exception)
        self.assertEqual(list_bookmarks(), [])
        ui.run()
        self.assertEqual(ui.button(key="bookmark_toggle_EWA").label, "Bookmark ETF")

    def test_etf_can_be_saved_and_removed_when_price_history_is_unavailable(self):
        self.history.return_value = self.history.return_value.iloc[:1]
        for provider_error in (StockDataError("Provider unavailable"), None):
            with self.subTest(provider_error=provider_error):
                self.history.side_effect = provider_error
                ui = self.ui()
                self.assertFalse(ui.exception)
                self.assertTrue(ui.error)
                ui.button(key="bookmark_toggle_EWA").click().run()
                self.assertFalse(ui.exception)
                self.assertEqual([row["symbol"] for row in list_bookmarks()], ["EWA"])
                self.assertEqual(ui.button(key="bookmark_toggle_EWA").label, "Remove bookmark")
                ui.button(key="bookmark_toggle_EWA").click().run()
                self.assertEqual(list_bookmarks(), [])
                self.assertTrue(ui.error)

    def test_metadata_failure_does_not_prevent_saving_the_catalog_fund_name(self):
        self.info.side_effect = StockDataError("No metadata")
        ui = self.ui()
        ui.button(key="bookmark_toggle_EWA").click().run()
        self.assertFalse(ui.exception)
        fund = next(row["Fund"] for row in self.catalog if row["Symbol"] == "EWA")
        self.assertEqual(list_bookmarks()[0]["name"], fund)
        self.assertTrue(any("No metadata" in warning.value for warning in ui.warning))

    def test_atlas_bookmarks_preserve_international_listing_suffixes(self):
        entry = next(
            row for row in self.catalog
            if row["Universe"] == "Commodity ETFs" and row["Symbol"].endswith(".L")
        )
        unsuffixed = entry["Symbol"].removesuffix(".L")
        add_bookmark(unsuffixed, "Different listing")
        ui = self.ui()
        next(widget for widget in ui.radio if widget.label == "Taxonomy view").set_value("Commodity ETFs").run()
        self.selectbox(ui, "Market category").select(entry["Entry ID"]).run()
        ui.button(key=f"bookmark_toggle_{entry['Symbol']}").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual({row["symbol"] for row in list_bookmarks()}, {unsuffixed, entry["Symbol"]})

    def test_failed_bookmark_save_is_reported_without_claiming_success(self):
        ui = self.ui()
        with patch.object(self.app, "add_bookmark", side_effect=BookmarkError("Disk full")):
            ui.button(key="bookmark_toggle_EWA").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Disk full" in error.value for error in ui.error))
        self.assertEqual(list_bookmarks(), [])
        self.assertEqual(ui.button(key="bookmark_toggle_EWA").label, "Bookmark ETF")

    def test_former_edoc_selection_moves_to_heal_without_rewriting_bookmarks(self):
        old_entry = "Thematic ETFs|Aging & Health Innovation|EDOC"
        heal_entry = "Thematic ETFs|Aging & Health Innovation|HEAL"
        old_catalog = [
            {**row, "Symbol": "EDOC", "Entry ID": old_entry}
            if row["Symbol"] == "HEAL" else row for row in self.catalog
        ]
        add_bookmark("EDOC", "Previously saved EDOC")
        original_bookmarks = list_bookmarks()
        with patch.object(self.app, "etf_catalog", return_value=old_catalog):
            ui = self.ui()
            next(widget for widget in ui.radio if widget.label == "Taxonomy view").set_value("Thematic ETFs").run()
            self.selectbox(ui, "Market category").select(old_entry).run()
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["atlas_entry"], heal_entry)
        self.history.assert_called_with("HEAL", "5y", "1d")
        self.assertEqual(ui.button(key="bookmark_toggle_HEAL").label, "Bookmark ETF")
        self.assertEqual(list_bookmarks(), original_bookmarks)
        self.assertNotIn("EDOC", self.queue(ui)["Symbol"].tolist())

    def test_healthtech_chart_shows_the_source_backed_history_disclosure(self):
        with (
            patch.object(self.app, "render_chart_and_assistant", self.render_chart_and_assistant),
            patch.object(self.app, "render_stock_assistant"),
        ):
            ui = self.ui()
            next(widget for widget in ui.radio if widget.label == "Taxonomy view").set_value("Thematic ETFs").run()
            self.selectbox(ui, "Market category").select(
                "Thematic ETFs|Aging & Health Innovation|HEAL",
            ).run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("EDOC became HEAL" in info.value for info in ui.info))
        self.assertTrue(any("Issuer explanation" in info.value for info in ui.info))
        self.assertEqual(len(ui.get("plotly_chart")), 1)

    def test_bwet_freight_filter_loads_chart_disclosure_and_bookmark(self):
        with (
            patch.object(self.app, "render_chart_and_assistant", self.render_chart_and_assistant),
            patch.object(self.app, "render_stock_assistant") as assistant,
        ):
            ui = self.ui()
            next(widget for widget in ui.radio if widget.label == "Taxonomy view").set_value("Commodity ETFs").run()
            self.selectbox(ui, "Commodity group").select("Freight").run()
            self.assertFalse(ui.exception)
            self.assertEqual(self.queue(ui)["Symbol"].tolist(), ["BWET"])
            self.assertEqual(ui.session_state["atlas_entry"], "Commodity ETFs|Freight|BWET")
            self.history.assert_called_with("BWET", "5y", "1d")
            self.assertEqual(len(ui.get("plotly_chart")), 1)
            self.assertTrue(any("tanker freight futures" in item.value for item in ui.info))
            self.assertTrue(any("https://amplifyetfs.com/bwet/" in item.value for item in ui.info))
            self.assertEqual(assistant.call_args.args[0], "BWET")
            self.assertIn("commodity pool", assistant.call_args.args[-1]["ResearchNotes"])
            ui.button(key="bookmark_toggle_BWET").click().run()
            self.assertFalse(ui.exception)
            self.assertEqual(
                [(row["symbol"], row["name"]) for row in list_bookmarks()],
                [("BWET", "Breakwave Tanker Shipping ETF")],
            )

    def test_healthtech_chat_context_includes_the_mandate_change_without_existing_evidence(self):
        with (
            patch.object(self.app, "cached_financial_history", return_value=pd.DataFrame()),
            patch.object(self.app, "cached_stock_revenue_growth", return_value={}),
            patch.object(self.app, "cached_company_news", return_value={"articles": []}),
        ):
            context = self.app.load_stock_chat_context(
                "HEAL", "Global X HealthTech ETF", {"quoteType": "ETF"},
                self.history.return_value,
            )
        self.assertIn("EDOC became HEAL", str(context))
        self.assertIn("2025-04-01", str(context))
        self.assertIn("https://www.globalxetfs.com/articles/why-healthtech-why-heal", str(context))


if __name__ == "__main__":
    unittest.main()
