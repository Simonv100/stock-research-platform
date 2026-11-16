import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import plotly.graph_objects as go
from streamlit.testing.v1 import AppTest

import bookmarks
from bookmarks import BookmarkError, add_bookmark, list_bookmarks, remove_bookmark
from stock_data import StockDataError


class BookmarkStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "data" / "bookmarks.sqlite3"
        patcher = patch.object(bookmarks, "BOOKMARKS_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_empty_store_add_remove_and_international_listing_identity(self):
        self.assertEqual(list_bookmarks(), [])
        add_bookmark(" bmw.de ", "BMW")
        add_bookmark("BMW", "Different listing")
        add_bookmark("7203.T", "Toyota")
        add_bookmark("BRK-B", "Berkshire")
        self.assertEqual([row["symbol"] for row in list_bookmarks()],
                         ["7203.T", "BMW", "BMW.DE", "BRK-B"])
        remove_bookmark("bmw.de")
        remove_bookmark("bmw.de")
        self.assertEqual([row["symbol"] for row in list_bookmarks()],
                         ["7203.T", "BMW", "BRK-B"])

    def test_duplicate_bookmark_preserves_original_date_and_name(self):
        add_bookmark("AAPL", "Apple")
        original = list_bookmarks()
        add_bookmark("aapl", "Apple Inc.")
        self.assertEqual(list_bookmarks(), original)

    def test_bookmarks_survive_a_new_python_process(self):
        add_bookmark("PFE", "Pfizer")
        code = (
            "import json; from pathlib import Path; import bookmarks; "
            f"bookmarks.BOOKMARKS_PATH = Path({str(self.path)!r}); "
            "print(json.dumps(bookmarks.list_bookmarks()))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], check=True, capture_output=True, text=True,
            cwd=Path(bookmarks.__file__).parent,
        )
        self.assertEqual(json.loads(result.stdout), list_bookmarks())

    def test_invalid_symbol_and_database_failure_are_explicit(self):
        for symbol in ("", "  ", "two tickers"):
            with self.subTest(symbol=symbol), self.assertRaises(BookmarkError):
                add_bookmark(symbol, "Invalid")
        with patch("bookmarks.sqlite3.connect", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaisesRegex(BookmarkError, "locked"):
                list_bookmarks()
            with self.assertRaisesRegex(BookmarkError, "locked"):
                add_bookmark("AAPL", "Apple")

    def test_corrupt_database_is_not_replaced_with_empty_store(self):
        self.path.parent.mkdir()
        self.path.write_bytes(b"not a database")
        with self.assertRaises(BookmarkError):
            list_bookmarks()
        self.assertEqual(self.path.read_bytes(), b"not a database")


class BookmarkUITests(unittest.TestCase):
    def setUp(self):
        import app
        self.app = app
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(
            bookmarks, "BOOKMARKS_PATH", Path(folder) / "bookmarks.sqlite3",
        ))
        self.history = self.stack.enter_context(patch.object(
            app, "cached_history", return_value=pd.DataFrame({"Close": [10.0, 11.0]}),
        ))
        self.stack.enter_context(patch.object(app, "cached_info", return_value={}))
        self.stack.enter_context(patch.object(app, "price_chart", return_value=go.Figure()))

    def make_ui(self):
        return AppTest.from_string(
            "from app import render_bookmarks\nrender_bookmarks()"
        ).run()

    def button(self, ui, label):
        return next(item for item in ui.button if item.label == label)

    def test_save_button_persists_and_toggles_without_duplicates(self):
        ui = AppTest.from_string(
            "from app import render_bookmark_button\n"
            "render_bookmark_button('PFE', 'Pfizer')"
        ).run()
        self.button(ui, "Bookmark stock").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(list_bookmarks()), 1)
        ui.run()
        self.assertEqual(len(list_bookmarks()), 1)
        self.button(ui, "Remove bookmark").click().run()
        self.assertEqual(list_bookmarks(), [])
        self.assertEqual(ui.button[0].label, "Bookmark stock")

    def test_empty_list_and_failed_storage_show_explicit_messages(self):
        ui = self.make_ui()
        self.assertFalse(ui.exception)
        self.assertIn("No bookmarks yet", ui.info[0].value)
        self.history.assert_not_called()
        with patch.object(self.app, "list_bookmarks", side_effect=BookmarkError("Disk unavailable")):
            ui.run()
            self.assertIn("Disk unavailable", ui.error[0].value)
            self.assertFalse(ui.exception)

    def test_browse_remove_and_open_full_research_with_bookmark_queue(self):
        add_bookmark("AAPL", "Apple")
        add_bookmark("PFE", "Pfizer")
        ui = self.make_ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox[0].value, "AAPL")
        self.assertEqual(len(ui.get("plotly_chart")), 1)
        self.button(ui, "Previous bookmark").click().run()
        self.assertEqual(ui.selectbox[0].value, "PFE")
        self.button(ui, "Next bookmark").click().run()
        self.assertEqual(ui.selectbox[0].value, "AAPL")
        self.button(ui, "Open in Individual Stocks").click().run()
        self.assertEqual(ui.session_state["research_area"], "Individual stocks")
        self.assertEqual(ui.session_state["stock_query"], "AAPL")
        self.assertEqual(ui.session_state["stock_research_queue"], ["AAPL", "PFE"])
        self.assertEqual(ui.session_state["stock_research_queue_label"], "Bookmarked stocks")
        self.button(ui, "Remove bookmark").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.selectbox[0].value, "PFE")
        self.assertTrue(self.button(ui, "Next bookmark").disabled)
        self.button(ui, "Remove bookmark").click().run()
        self.assertFalse(ui.exception)
        self.assertIn("No bookmarks yet", ui.info[0].value)

    def test_unavailable_prices_do_not_prevent_removal(self):
        add_bookmark("PFE", "Pfizer")
        self.history.side_effect = StockDataError("No prices")
        ui = self.make_ui()
        self.assertFalse(ui.exception)
        self.assertIn("bookmark is still saved", ui.warning[0].value)
        self.button(ui, "Remove bookmark").click().run()
        self.assertEqual(list_bookmarks(), [])

    def test_metadata_failure_preserves_chart(self):
        add_bookmark("PFE", "Pfizer")
        with patch.object(self.app, "cached_info", side_effect=StockDataError("No metadata")):
            ui = self.make_ui()
            self.assertFalse(ui.exception)
            self.assertEqual(len(ui.get("plotly_chart")), 1)
            self.assertIn("chart is still shown", ui.warning[0].value)

    def test_research_queue_tracks_removals_and_can_exit_to_search(self):
        add_bookmark("AAPL", "Apple")
        add_bookmark("PFE", "Pfizer")
        self.history.side_effect = StockDataError("Offline for test")
        ui = AppTest.from_string("from app import main\nmain()")
        ui.session_state["stock_research_queue_label"] = "Bookmarked stocks"
        ui.session_state["stock_research_symbol"] = "AAPL"
        ui.run()
        self.assertFalse(ui.exception)
        remove_bookmark("AAPL")
        ui.run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.session_state["stock_research_queue"], ["PFE"])
        self.assertEqual(ui.session_state["stock_query"], "PFE")
        with patch.object(self.app, "cached_search", return_value=[]):
            self.button(ui, "Search").click().run()
        ui.run()
        self.assertFalse(ui.exception)
        self.assertNotIn("stock_research_queue_label", ui.session_state)
        self.assertNotIn("stock_research_queue", ui.session_state)


if __name__ == "__main__":
    unittest.main()
