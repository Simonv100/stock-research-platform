import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import trade_checklist as store
from trade_checklist import ChecklistError


class ChecklistTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        folder = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(folder) / "trade_checklist.sqlite3"
        self.stack.enter_context(patch.object(store, "CHECKLIST_PATH", self.path))


class ChecklistStorageTests(ChecklistTestCase):
    def test_first_item_is_seeded_once_as_an_unverified_paraphrase(self):
        first = store.list_checklist_items()
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["title"], store.DEFAULT_TITLE)
        self.assertIn("thesis", first[0]["note"])
        self.assertIn("trend", first[0]["note"])
        self.assertIn("not a verified quotation", first[0]["attribution"])
        self.assertFalse(first[0]["checked"])
        self.assertEqual(store.list_checklist_items(), first)

    def test_add_edit_check_reset_and_confirmed_removal_preserve_other_items(self):
        first = store.list_checklist_items()[0]
        store.add_checklist_item("  Position size  ", "Keep risk acceptable.", "My rule", "https://example.com/rule")
        second = store.list_checklist_items()[1]
        self.assertEqual(second["title"], "Position size")
        store.set_checklist_checked(first["id"], first["revision"], True)
        store.set_checklist_checked(second["id"], second["revision"], True)
        store.update_checklist_item(second["id"], second["revision"], "Recheck position size")
        items = store.list_checklist_items()
        self.assertTrue(items[0]["checked"])
        self.assertFalse(items[1]["checked"])
        store.reset_checklist_checks()
        self.assertTrue(all(not row["checked"] for row in store.list_checklist_items()))
        with self.assertRaisesRegex(ChecklistError, "Confirm removal"):
            store.delete_checklist_item(first["id"], first["revision"])
        store.delete_checklist_item(first["id"], first["revision"], confirmed=True)
        self.assertEqual(store.list_checklist_items()[0]["title"], "Recheck position size")

    def test_deleting_all_items_does_not_reseed_the_default(self):
        item = store.list_checklist_items()[0]
        store.delete_checklist_item(item["id"], item["revision"], confirmed=True)
        self.assertEqual(store.list_checklist_items(), [])
        store.reset_checklist_checks()
        self.assertEqual(store.list_checklist_items(), [])
        store.add_checklist_item("My new first item")
        self.assertEqual(len(store.list_checklist_items()), 1)

    def test_items_and_checks_survive_a_new_process(self):
        item = store.list_checklist_items()[0]
        store.set_checklist_checked(item["id"], item["revision"], True)
        code = (
            "import json; from pathlib import Path; import trade_checklist as s; "
            f"s.CHECKLIST_PATH=Path({str(self.path)!r}); print(json.dumps(s.list_checklist_items()))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], check=True, capture_output=True, text=True,
            cwd=Path(store.__file__).parent,
        )
        self.assertEqual(json.loads(result.stdout), store.list_checklist_items())

    def test_stale_edits_deletes_and_review_marks_cannot_overwrite_changed_content(self):
        original = store.list_checklist_items()[0]
        store.update_checklist_item(original["id"], original["revision"], "New version")
        operations = (
            lambda: store.update_checklist_item(original["id"], original["revision"], "Stale overwrite"),
            lambda: store.delete_checklist_item(original["id"], original["revision"], confirmed=True),
            lambda: store.set_checklist_checked(original["id"], original["revision"], True),
        )
        for operation in operations:
            with self.subTest(operation=operation), self.assertRaisesRegex(ChecklistError, "changed"):
                operation()
        item = store.list_checklist_items()[0]
        self.assertEqual(item["title"], "New version")
        self.assertFalse(item["checked"])

    def test_invalid_fields_do_not_change_the_store(self):
        original = store.list_checklist_items()
        for fields in (
            {"title": ""}, {"title": " "}, {"title": "x" * 161},
            {"title": "Test", "note": "x" * 4001},
            {"title": "Test", "source_url": "javascript:alert(1)"},
            {"title": "Test", "source_url": "https://user:secret@example.com"},
            {"title": "Test", "source_url": "https://[broken"},
        ):
            with self.subTest(fields=fields), self.assertRaises(ChecklistError):
                store.add_checklist_item(**fields)
        self.assertEqual(store.list_checklist_items(), original)

    def test_storage_failure_is_explicit_and_corrupt_file_is_not_replaced(self):
        with patch("trade_checklist.sqlite3.connect", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaisesRegex(ChecklistError, "locked"):
                store.list_checklist_items()
        self.path.write_bytes(b"not a database")
        with self.assertRaises(ChecklistError):
            store.list_checklist_items()
        self.assertEqual(self.path.read_bytes(), b"not a database")


class ChecklistUITests(ChecklistTestCase):
    def ui(self):
        return AppTest.from_string(
            "from trade_checklist_ui import render_trade_checklist\nrender_trade_checklist()"
        ).run()

    def review_checkbox(self, ui):
        return next(widget for widget in ui.checkbox if widget.key.startswith("trade_item_") and "_checked_" in widget.key)

    def test_first_item_check_reset_and_fresh_session(self):
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.metric[0].value, "0 / 1")
        self.assertTrue(any("Stanley Druckenmiller" in text.value for text in ui.text))
        self.assertTrue(any("not a verified quotation" in text.value for text in ui.text))
        self.assertTrue(ui.button(key="trade_checklist_reset").disabled)
        self.review_checkbox(ui).check().run()
        self.assertFalse(ui.exception)
        self.assertTrue(store.list_checklist_items()[0]["checked"])
        self.assertEqual(ui.metric[0].value, "1 / 1")
        fresh = self.ui()
        self.assertTrue(self.review_checkbox(fresh).value)
        ui.button(key="trade_checklist_reset").click().run()
        self.assertFalse(ui.exception)
        self.assertFalse(self.review_checkbox(ui).value)
        self.assertEqual(ui.metric[0].value, "0 / 1")
        self.assertEqual(store.list_checklist_items()[0]["note"], store.DEFAULT_NOTE)
        self.review_checkbox(ui).check().run()
        self.review_checkbox(ui).uncheck().run()
        self.assertFalse(store.list_checklist_items()[0]["checked"])

    def test_add_edit_and_remove_item(self):
        ui = self.ui()
        ui.text_input(key="trade_add_0_title").input("Position sizing")
        ui.text_area(key="trade_add_0_note").input("Review the position size.")
        ui.button(key="trade_add_0_submit").click().run()
        self.assertFalse(ui.exception)
        item = store.list_checklist_items()[1]
        edit_key = f"trade_edit_{item['id']}_{item['revision']}_0"
        ui.text_input(key=f"{edit_key}_title").input("Size and liquidity")
        ui.button(key=f"{edit_key}_save").click().run()
        self.assertFalse(ui.exception)
        item = store.list_checklist_items()[1]
        self.assertEqual(item["title"], "Size and liquidity")
        key = f"trade_item_{item['id']}_{item['revision']}"
        self.assertTrue(ui.button(key=f"{key}_delete").disabled)
        ui.checkbox(key=f"{key}_confirm").check().run()
        ui.button(key=f"{key}_delete").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(len(store.list_checklist_items()), 1)

    def test_add_form_is_visible_before_existing_items_and_saves_title_only(self):
        first = store.list_checklist_items()[0]
        store.set_checklist_checked(first["id"], first["revision"], True)
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.text_input[0].key, "trade_add_0_title")
        self.assertNotIn("Add checklist item", [item.label for item in ui.expander])
        self.assertEqual([item.value for item in ui.subheader][:2], ["Add checklist item", "Your checklist"])
        ui.text_input(key="trade_add_0_title").input("Check position liquidity")
        ui.button(key="trade_add_0_submit").click().run()
        self.assertFalse(ui.exception)
        items = store.list_checklist_items()
        self.assertEqual(len(items), 2)
        self.assertTrue(items[0]["checked"])
        self.assertEqual(items[1]["title"], "Check position liquidity")
        self.assertFalse(items[1]["checked"])
        self.assertEqual(items[1]["note"], "")
        self.assertEqual(ui.text_input(key="trade_add_1_title").value, "")
        self.assertEqual(ui.metric[0].value, "1 / 2")
        self.assertTrue(any("Checklist item added" in item.value for item in ui.success))
        fresh = self.ui()
        self.assertEqual(fresh.metric[0].value, "1 / 2")
        self.assertEqual(store.list_checklist_items(), items)

    def test_failed_add_keeps_draft_without_claiming_success(self):
        ui = self.ui()
        ui.text_input(key="trade_add_0_title").input("My new point")
        with patch("trade_checklist_ui.add_checklist_item", side_effect=ChecklistError("Disk unavailable")):
            ui.button(key="trade_add_0_submit").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(ui.text_input(key="trade_add_0_title").value, "My new point")
        self.assertTrue(any("Disk unavailable" in item.value for item in ui.error))
        self.assertFalse(ui.success)
        self.assertEqual(len(store.list_checklist_items()), 1)

    def test_empty_checklist_can_be_populated_from_top_form(self):
        first = store.list_checklist_items()[0]
        store.delete_checklist_item(first["id"], first["revision"], confirmed=True)
        ui = self.ui()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Add your first item above" in item.value for item in ui.info))
        ui.text_input(key="trade_add_0_title").input("My first point")
        ui.button(key="trade_add_0_submit").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual([item["title"] for item in store.list_checklist_items()], ["My first point"])

    def test_invalid_add_preserves_draft_and_shows_error(self):
        ui = self.ui()
        ui.text_area(key="trade_add_0_note").input("Unsaved draft")
        ui.button(key="trade_add_0_submit").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Enter a checklist item title" in error.value for error in ui.error))
        self.assertEqual(ui.text_area(key="trade_add_0_note").value, "Unsaved draft")
        self.assertEqual(len(store.list_checklist_items()), 1)

    def test_conflicting_edit_preserves_draft_and_requires_reload(self):
        ui = self.ui()
        original = store.list_checklist_items()[0]
        key = f"trade_edit_{original['id']}_{original['revision']}_0"
        ui.text_input(key=f"{key}_title").input("My draft")
        store.update_checklist_item(original["id"], original["revision"], "Other editor")
        ui.button(key=f"{key}_save").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("changed" in error.value for error in ui.error))
        self.assertEqual(ui.text_input(key=f"{key}_title").value, "My draft")
        self.assertEqual(store.list_checklist_items()[0]["title"], "Other editor")
        ui.button(key=f"trade_reload_{original['id']}").click().run()
        item = store.list_checklist_items()[0]
        new_key = f"trade_edit_{item['id']}_{item['revision']}_1"
        self.assertEqual(ui.text_input(key=f"{new_key}_title").value, "Other editor")

    def test_storage_and_checkbox_write_failures_are_visible(self):
        ui = self.ui()
        with patch("trade_checklist_ui.set_checklist_checked", side_effect=ChecklistError("Disk unavailable")):
            self.review_checkbox(ui).check().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Disk unavailable" in error.value for error in ui.error))
        self.assertFalse(self.review_checkbox(ui).value)
        self.assertFalse(store.list_checklist_items()[0]["checked"])
        with patch("trade_checklist_ui.list_checklist_items", side_effect=ChecklistError("Cannot read checklist")):
            ui.run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Cannot read checklist" in error.value for error in ui.error))
        self.assertFalse(ui.button(key="trade_checklist_reload").disabled)

    def test_sidebar_route_does_not_fetch_market_data_or_call_ai(self):
        import app
        with (
            patch.object(app, "cached_info", side_effect=AssertionError("No market request")),
            patch.object(app, "cached_history", side_effect=AssertionError("No price request")),
            patch.object(app, "render_stock_assistant", side_effect=AssertionError("No AI")),
        ):
            ui = AppTest.from_string("from app import main\nmain()")
            ui.session_state["research_area"] = "Trade checklist"
            ui.run()
        self.assertFalse(ui.exception)
        self.assertIn("Trade checklist", ui.radio(key="research_area").options)
        self.assertEqual(ui.metric[0].value, "0 / 1")


if __name__ == "__main__":
    unittest.main()
