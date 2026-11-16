import json
import shutil
import socket
import sqlite3
import subprocess
import sys
import unittest
from contextlib import ExitStack, closing
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from streamlit.testing.v1 import AppTest

import management_evidence as evidence
import management_evidence_ui as evidence_ui
from management_evidence import (
    ManagementEvidenceError,
    get_management_evidence,
    list_management_evidence,
    management_search_links,
    reset_management_evidence,
    save_management_evidence,
)


TODAY = date(2026, 9, 13)


def favorable_fields():
    return {
        "ManagementCompanyName": "Example Company",
        "ManagementManualAssessment": "Favorable",
        "ManagementReviewDate": TODAY.isoformat(),
        "ManagementCEOName": "Example CEO",
        "ManagementCEOAppointmentDate": "2026-02-01",
        "ManagementCEOBackground": "Prior operating role; outcomes need continued monitoring.",
        "ManagementCEOOrigin": "External",
        "ManagementCEOMandate": "Improve cash conversion and simplify the product portfolio.",
        "ManagementIncentiveChangeDate": "2026-03-01",
        "ManagementOldMetrics": "Revenue and adjusted operating profit",
        "ManagementNewMetrics": "Cash conversion and relative TSR",
        "ManagementPriceHurdles": "No absolute price hurdle disclosed",
        "ManagementRelativeTSRHurdles": "Median peer TSR to vest; upper quartile for maximum",
        "ManagementMeasurementPeriod": "Three fiscal years",
        "ManagementHoldingPeriod": "Two years after vesting",
        "ManagementDilutionSafeguards": "Capped award size; annual share usage disclosed",
        "ManagementResetSafeguards": "No repricing without shareholder approval",
        "ManagementExecutionProgress": "One milestone delivered; margin recovery not yet demonstrated",
        "ManagementNarrative": "My judgment favors cash discipline, with material execution risk.",
        "ManagementCEOSourceURL": "https://issuer.example/ceo-announcement",
        "ManagementCEOSourceDate": "2026-01-20",
        "ManagementIncentiveSourceURL": "https://issuer.example/annual-remuneration-report",
        "ManagementIncentiveSourceDate": "2026-03-15",
        "ManagementSourcesConfirmedPrimary": True,
    }


class LocalEvidenceTestCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(evidence.__file__).parent / f".management-test-{uuid4().hex}"
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.folder)
        self.path = self.folder / "data" / "management_evidence.sqlite3"
        self.stack.enter_context(patch.object(evidence, "MANAGEMENT_EVIDENCE_PATH", self.path))
        self.stack.enter_context(patch.object(evidence, "_today", return_value=TODAY))
        self.network = self.stack.enter_context(patch.object(
            socket.socket, "connect", side_effect=AssertionError("Tests must not use a network"),
        ))
        self.ai = self.stack.enter_context(patch(
            "openai_transport.request_openai_response",
            side_effect=AssertionError("Management evidence must not call AI"),
        ))


class ManagementEvidenceStorageTests(LocalEvidenceTestCase):
    def test_missing_listing_is_unreviewed_flat_json_and_not_inserted(self):
        record = get_management_evidence(" bmw.de ")
        self.assertEqual(record["ManagementSymbol"], "BMW.DE")
        self.assertEqual(record["ManagementStatus"], "Unreviewed")
        self.assertIn("Unresearched does not mean unfavorable", record["ManagementReason"])
        self.assertEqual(record["ManagementReviewFreshness"], "Unreviewed")
        self.assertFalse(record["ManagementFavorableFilterEligible"])
        self.assertFalse(record["ManagementNewCEO"])
        self.assertTrue(all(field.startswith("Management") for field in record))
        self.assertTrue(all(not isinstance(value, (dict, list)) for value in record.values()))
        self.assertEqual(json.loads(json.dumps(record)), record)
        self.assertEqual(list_management_evidence(), [])
        self.network.assert_not_called()
        self.ai.assert_not_called()

    def test_new_ceo_and_stock_linked_pay_do_not_imply_favorable(self):
        record = save_management_evidence("PFE", {
            "ManagementCEOName": "Example", "ManagementCEOAppointmentDate": "2026-09-01",
            "ManagementNewMetrics": "Stock price",
        })
        self.assertTrue(record["ManagementNewCEO"])
        self.assertEqual(record["ManagementStatus"], "Needs evidence")
        self.assertIn("Favorable still requires", record["ManagementReason"])
        self.assertEqual(record["ManagementManualAssessment"], "Unreviewed")
        self.assertFalse(record["ManagementFavorableFilterEligible"])

    def test_favorable_is_explicit_evidence_backed_manual_judgment(self):
        fields = favorable_fields()
        fields["ManagementManualAssessment"] = "Needs evidence"
        record = save_management_evidence("PFE", fields)
        self.assertFalse(record["ManagementFavorableFilterEligible"])
        record = save_management_evidence("pfe", {"ManagementManualAssessment": "Favorable"})
        self.assertEqual(record["ManagementStatus"], "Favorable")
        self.assertIn("Explicit favorable user judgment", record["ManagementReason"])
        self.assertEqual(record["ManagementEvidenceGaps"], "")
        self.assertTrue(record["ManagementFavorableFilterEligible"])
        self.assertTrue(record["ManagementNewCEO"])
        record = save_management_evidence("PFE", {"ManagementCEOAppointmentDate": "2018-01-01"})
        self.assertFalse(record["ManagementNewCEO"])
        self.assertTrue(record["ManagementFavorableFilterEligible"])

    def test_each_required_field_and_primary_confirmation_are_required(self):
        for field in evidence.FAVORABLE_REQUIRED_FIELDS:
            with self.subTest(field=field):
                fields = favorable_fields()
                fields[field] = ""
                with self.assertRaisesRegex(ManagementEvidenceError, "Favorable requires"):
                    save_management_evidence("PFE", fields)
        for update in (
            {"ManagementSourcesConfirmedPrimary": False},
            {"ManagementCEOOrigin": "Unknown"},
            {"ManagementExecutionSourceURL": "https://issuer.example/results"},
        ):
            with self.subTest(update=update), self.assertRaises(ManagementEvidenceError):
                save_management_evidence("PFE", {**favorable_fields(), **update})
        self.assertEqual(list_management_evidence(), [])

    def test_listing_identity_partial_updates_and_safe_explicit_reset(self):
        original = save_management_evidence(" bmw.de ", {"ManagementNarrative": "Keep this note"})
        save_management_evidence("BMW", {"ManagementNarrative": "Different listing"})
        save_management_evidence("7203.T", {})
        save_management_evidence("BRK-B", {})
        updated = save_management_evidence("BMW.DE", {"ManagementCEOName": "Example"})
        self.assertEqual(updated["ManagementNarrative"], "Keep this note")
        self.assertEqual(updated["ManagementCreatedAt"], original["ManagementCreatedAt"])
        self.assertEqual([row["ManagementSymbol"] for row in list_management_evidence()],
                         ["7203.T", "BMW", "BMW.DE", "BRK-B"])
        with self.assertRaisesRegex(ManagementEvidenceError, "Confirm"):
            reset_management_evidence("BMW.DE")
        with self.assertRaises(ManagementEvidenceError):
            reset_management_evidence("BMW.DE", confirmed="yes")
        self.assertEqual(get_management_evidence("BMW.DE"), updated)
        reset_management_evidence("bmw.de", confirmed=True)
        self.assertEqual(get_management_evidence("BMW.DE")["ManagementStatus"], "Unreviewed")
        self.assertEqual(get_management_evidence("BMW")["ManagementNarrative"], "Different listing")
        reset_management_evidence("BMW.DE", confirmed=True)

    def test_stale_review_preserves_manual_assessment_and_notes_but_excludes_filter(self):
        fields = favorable_fields()
        saved = save_management_evidence("PFE", fields)
        raw_before = self.path.read_bytes()
        with patch.object(evidence, "_today", return_value=TODAY + timedelta(days=365)):
            self.assertTrue(get_management_evidence("PFE")["ManagementFavorableFilterEligible"])
        with patch.object(evidence, "_today", return_value=TODAY + timedelta(days=366)):
            record = get_management_evidence("PFE")
            self.assertEqual(record["ManagementReviewFreshness"], "Stale")
            self.assertEqual(record["ManagementStatus"], "Needs evidence")
            self.assertIn("older than 365 days", record["ManagementReason"])
            self.assertEqual(record["ManagementManualAssessment"], "Favorable")
            self.assertEqual(record["ManagementNarrative"], saved["ManagementNarrative"])
            self.assertFalse(record["ManagementFavorableFilterEligible"])
            self.assertTrue(record["ManagementReviewStale"])
            self.assertEqual(self.path.read_bytes(), raw_before)
            with self.assertRaisesRegex(ManagementEvidenceError, "365 days"):
                save_management_evidence("PFE", {"ManagementCompanyName": "Updated name"})
            refreshed = save_management_evidence("PFE", {
                "ManagementReviewDate": (TODAY + timedelta(days=366)).isoformat(),
            })
            self.assertTrue(refreshed["ManagementFavorableFilterEligible"])

    def test_dates_types_urls_and_read_only_fields_validate_without_destroying_data(self):
        original = save_management_evidence("PFE", {"ManagementNarrative": "Preserve me"})
        invalid = [
            {"ManagementReviewDate": "2026-02-30"},
            {"ManagementReviewDate": "20260913"},
            {"ManagementCEOAppointmentDate": "2026-09-14"},
            {"ManagementIncentiveChangeDate": "2026-09-14"},
            {"ManagementCEOSourceDate": "2026-09-14"},
            {"ManagementReviewDate": "2026-09-14"},
            {"ManagementReviewDate": "2026-01-01", "ManagementCEOAppointmentDate": "2026-02-01"},
            {"ManagementReviewDate": "2026-01-01", "ManagementCEOSourceDate": "2026-02-01"},
            {"ManagementNarrative": None},
            {"ManagementSourcesConfirmedPrimary": "yes"},
            {"ManagementManualAssessment": "Buy"},
            {"ManagementCEOOrigin": "Probably external"},
            {"ManagementStatus": "Favorable"},
            {"ManagementCEOSourceURL": "javascript:alert(1)"},
            {"ManagementCEOSourceURL": "https://user:password@issuer.example/report"},
            {"ManagementCEOSourceURL": "https://issuer.example/a\nb"},
            {"ManagementCEOSourceURL": "https://"},
            {"ManagementCEOSourceURL": "https://issuer.example:bad/report"},
        ]
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ManagementEvidenceError):
                save_management_evidence("PFE", fields)
            self.assertEqual(get_management_evidence("PFE"), original)
        for symbol in ("", "two tickers", "<script>", None):
            with self.subTest(symbol=symbol), self.assertRaises(ManagementEvidenceError):
                get_management_evidence(symbol)

    def test_other_manual_assessments_require_current_date_for_effective_status(self):
        for manual in ("Mixed", "Unfavorable"):
            record = save_management_evidence("PFE", {"ManagementManualAssessment": manual})
            self.assertEqual(record["ManagementStatus"], "Needs evidence")
            record = save_management_evidence("PFE", {"ManagementReviewDate": TODAY.isoformat()})
            self.assertEqual(record["ManagementStatus"], manual)
            self.assertFalse(record["ManagementFavorableFilterEligible"])
            reset_management_evidence("PFE", confirmed=True)

    def test_concurrent_edits_and_reset_reject_stale_revision(self):
        original = save_management_evidence("PFE", {}, expected_updated_at="")
        updated = save_management_evidence("PFE", {
            "ManagementNarrative": "Another editor's work",
        }, expected_updated_at=original["ManagementUpdatedAt"])
        for operation in (
            lambda: save_management_evidence("PFE", {}, expected_updated_at=""),
            lambda: save_management_evidence("PFE", {}, expected_updated_at=original["ManagementUpdatedAt"]),
            lambda: reset_management_evidence(
                "PFE", confirmed=True, expected_updated_at=original["ManagementUpdatedAt"],
            ),
        ):
            with self.assertRaisesRegex(ManagementEvidenceError, "another editor"):
                operation()
        self.assertEqual(get_management_evidence("PFE"), updated)

    def test_persistence_survives_new_python_process_and_preserves_unrecognized_stored_fields(self):
        saved = save_management_evidence("BMW.DE", {"ManagementNarrative": "Durable local note"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            payload = json.loads(connection.execute("SELECT payload FROM management_evidence").fetchone()[0])
            payload["ManagementFutureField"] = "Preserve future schema data"
            connection.execute("UPDATE management_evidence SET payload = ?", (json.dumps(payload),))
        save_management_evidence("BMW.DE", {"ManagementCompanyName": "BMW"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            payload = json.loads(connection.execute("SELECT payload FROM management_evidence").fetchone()[0])
            self.assertEqual(payload["ManagementFutureField"], "Preserve future schema data")
        code = (
            "import json; from pathlib import Path; import management_evidence as m; "
            f"m.MANAGEMENT_EVIDENCE_PATH = Path({str(self.path)!r}); "
            "print(json.dumps(m.get_management_evidence('bmw.de')))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], check=True, capture_output=True, text=True,
            cwd=Path(evidence.__file__).parent,
        )
        self.assertEqual(json.loads(result.stdout)["ManagementNarrative"], saved["ManagementNarrative"])

    def test_locked_corrupt_database_and_payload_fail_without_replacement(self):
        with patch.object(evidence.sqlite3, "connect", side_effect=sqlite3.OperationalError("locked")):
            with self.assertRaisesRegex(ManagementEvidenceError, "locked"):
                list_management_evidence()
            with self.assertRaisesRegex(ManagementEvidenceError, "locked"):
                save_management_evidence("PFE", {})
        self.path.write_bytes(b"not a database")
        with self.assertRaises(ManagementEvidenceError):
            get_management_evidence("PFE")
        self.assertEqual(self.path.read_bytes(), b"not a database")
        self.path.unlink()
        save_management_evidence("PFE", {})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE management_evidence SET payload = ?", ("invalid JSON",))
        with self.assertRaisesRegex(ManagementEvidenceError, "not replaced"):
            save_management_evidence("PFE", {"ManagementNarrative": "Do not overwrite"})
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT payload FROM management_evidence").fetchone()[0],
                             "invalid JSON")

    def test_search_links_encode_identity_and_never_fetch(self):
        links = management_search_links("bmw.de", "BMW & Co / München")
        self.assertEqual(len(links), 5)
        for url in links.values():
            self.assertEqual(urlsplit(url).hostname, "www.google.com")
            query = parse_qs(urlsplit(url).query)
            self.assertEqual(set(query), {"q"})
            self.assertIn("BMW.DE BMW & Co / München", query["q"][0])
        self.assertIn("8-K", " ".join(links.values()))
        self.network.assert_not_called()
        self.ai.assert_not_called()


class ManagementEvidenceUITests(LocalEvidenceTestCase):
    def make_ui(self, tracker=False):
        # Reuse this checked-in script rather than writing AppTest scripts outside the project.
        ui = AppTest.from_file(str(Path(__file__).resolve()))
        ui.session_state["_management_test_tracker"] = tracker
        return ui.run()

    @staticmethod
    def item(elements, label):
        return next(item for item in elements if item.label == label)

    def save(self, ui):
        return self.item(ui.button, "Save management evidence").click().run()

    def test_unreviewed_render_is_collapsed_and_network_free_without_key(self):
        ui = self.make_ui()
        self.assertFalse(ui.exception)
        self.assertTrue(any("Unreviewed" in item.value for item in ui.text))
        self.assertTrue(all(not item.proto.expanded for item in ui.expander))
        self.assertEqual(len(ui.get("link_button")), 5)
        self.assertEqual(list_management_evidence(), [])
        self.network.assert_not_called()
        self.ai.assert_not_called()

    def test_save_update_reload_reset_and_other_listing_isolation(self):
        save_management_evidence("BMW.DE", {"ManagementNarrative": "Other listing's note"})
        ui = self.make_ui()
        self.item(ui.text_input, "CEO name").set_value("Example CEO")
        self.item(ui.text_input, "CEO appointment date").set_value("2026-08-01")
        self.item(ui.text_area, "Assessment narrative / rationale / risks").set_value("Initial note")
        self.save(ui)
        self.assertFalse(ui.exception)
        self.assertEqual(get_management_evidence("PFE")["ManagementNarrative"], "Initial note")
        self.assertTrue(any("NEW CEO" in item.value for item in ui.info))
        self.item(ui.text_area, "Assessment narrative / rationale / risks").set_value("Updated note")
        self.save(ui)
        self.assertFalse(ui.exception)
        fresh = self.make_ui()
        self.assertEqual(self.item(fresh.text_area, "Assessment narrative / rationale / risks").value, "Updated note")
        self.assertTrue(self.item(fresh.button, "Reset management evidence").disabled)
        self.item(fresh.checkbox, "Permanently remove the saved management evidence for PFE").check().run()
        self.item(fresh.button, "Reset management evidence").click().run()
        self.assertFalse(fresh.exception)
        self.assertEqual(get_management_evidence("PFE")["ManagementStatus"], "Unreviewed")
        self.assertEqual(self.item(fresh.text_input, "CEO name").value, "")
        self.assertEqual(self.item(fresh.text_area, "Assessment narrative / rationale / risks").value, "")
        self.assertEqual(get_management_evidence("BMW.DE")["ManagementNarrative"], "Other listing's note")

    def test_validation_error_preserves_draft_and_saved_data(self):
        saved = save_management_evidence("PFE", {"ManagementNarrative": "Saved note"})
        ui = self.make_ui()
        self.item(ui.selectbox, "Manual assessment").select("Favorable")
        self.item(ui.text_area, "Assessment narrative / rationale / risks").set_value("Unsaved assessment")
        self.save(ui)
        self.assertFalse(ui.exception)
        self.assertTrue(any("Favorable requires" in error.value for error in ui.error))
        self.assertEqual(self.item(ui.text_area, "Assessment narrative / rationale / risks").value,
                         "Unsaved assessment")
        self.assertEqual(get_management_evidence("PFE"), saved)
        self.item(ui.selectbox, "Manual assessment").select("Needs evidence")
        self.item(ui.text_input, "Review date").set_value("2026-09-14")
        self.save(ui)
        self.assertTrue(any("future" in error.value for error in ui.error))
        self.assertEqual(get_management_evidence("PFE"), saved)

    def test_favorable_sources_staleness_and_local_notes_are_plain_text(self):
        save_management_evidence("PFE", favorable_fields())
        ui = self.make_ui()
        self.assertFalse(ui.exception)
        self.assertEqual(len(ui.get("link_button")), 7)
        with patch.object(evidence, "_today", return_value=TODAY + timedelta(days=366)):
            ui.run()
            self.assertTrue(any("older than 365" in warning.value for warning in ui.warning))
            self.assertTrue(any("Needs evidence" in item.value for item in ui.text))
        save_management_evidence("PFE", {"ManagementNarrative": "![image](https://remote.example/pixel)"})
        ui.run()
        self.assertTrue(any("![image]" in item.value for item in ui.text))
        self.assertFalse(any("![image]" in item.value for item in ui.markdown))
        self.network.assert_not_called()
        self.ai.assert_not_called()

    def test_ui_favorable_is_deliberately_selected_and_saved(self):
        save_management_evidence("PFE", {
            **favorable_fields(), "ManagementManualAssessment": "Needs evidence",
        })
        ui = self.make_ui()
        self.item(ui.selectbox, "Manual assessment").select("Favorable")
        self.save(ui)
        self.assertFalse(ui.exception)
        self.assertTrue(get_management_evidence("PFE")["ManagementFavorableFilterEligible"])
        self.assertTrue(any("PFE · Favorable" in item.value for item in ui.text))

    def test_external_update_keeps_draft_and_requires_explicit_reload(self):
        save_management_evidence("PFE", {"ManagementNarrative": "Original"})
        ui = self.make_ui()
        self.item(ui.text_area, "Assessment narrative / rationale / risks").set_value("My unsaved draft")
        other = save_management_evidence("PFE", {"ManagementNarrative": "Other editor"})
        self.save(ui)
        self.assertFalse(ui.exception)
        self.assertTrue(any("another editor" in error.value for error in ui.error))
        self.assertEqual(get_management_evidence("PFE"), other)
        self.assertEqual(self.item(ui.text_area, "Assessment narrative / rationale / risks").value,
                         "My unsaved draft")
        self.item(ui.checkbox, "Permanently remove the saved management evidence for PFE").check().run()
        self.item(ui.button, "Reset management evidence").click().run()
        self.assertTrue(any("another editor" in error.value for error in ui.error))
        self.assertEqual(get_management_evidence("PFE"), other)
        self.item(ui.button, "Reload saved evidence (discard unsaved form)").click().run()
        self.assertFalse(ui.exception)
        self.assertEqual(self.item(ui.text_area, "Assessment narrative / rationale / risks").value,
                         "Other editor")

    def test_storage_errors_are_visible_on_read_save_and_reset(self):
        with patch.object(evidence_ui, "get_management_evidence",
                          side_effect=ManagementEvidenceError("Disk unavailable")):
            ui = self.make_ui()
            self.assertFalse(ui.exception)
            self.assertIn("Disk unavailable", ui.error[0].value)
        save_management_evidence("PFE", {"ManagementNarrative": "Retain me"})
        ui = self.make_ui()
        with patch.object(evidence_ui, "save_management_evidence",
                          side_effect=ManagementEvidenceError("Save locked")):
            self.save(ui)
            self.assertIn("Save locked", ui.error[0].value)
        self.item(ui.checkbox, "Permanently remove the saved management evidence for PFE").check().run()
        with patch.object(evidence_ui, "reset_management_evidence",
                          side_effect=ManagementEvidenceError("Reset locked")):
            self.item(ui.button, "Reset management evidence").click().run()
            self.assertIn("Reset locked", ui.error[0].value)
        self.assertEqual(get_management_evidence("PFE")["ManagementNarrative"], "Retain me")

    def test_tracker_browse_manual_filter_and_open_another_listing_without_routes(self):
        ui = self.make_ui(tracker=True)
        self.assertFalse(ui.exception)
        self.assertTrue(any("No management reviews yet" in item.value for item in ui.info))
        save_management_evidence("PFE", favorable_fields())
        save_management_evidence("BMW.DE", {"ManagementNarrative": "Needs work"})
        ui.run()
        self.item(ui.selectbox, "Saved review").select("BMW.DE").run()
        self.item(ui.checkbox, "Favorable manual reviews only (current evidence, not automatic alpha)").check().run()
        self.assertFalse(ui.exception)
        self.assertEqual(self.item(ui.selectbox, "Saved review").value, "")
        self.assertEqual(list(ui.dataframe[0].value["Symbol"]), ["PFE"])
        self.item(ui.selectbox, "Saved review").select("PFE").run()
        self.assertTrue(any("PFE · Favorable" in item.value for item in ui.text))
        self.item(ui.text_input, "Research another ticker").set_value("7203.T")
        self.item(ui.text_input, "Company name (optional)").set_value("Toyota")
        self.item(ui.button, "Open local management review").click().run()
        self.assertFalse(ui.exception)
        self.assertTrue(any("7203.T · Unreviewed" in item.value for item in ui.text))
        self.assertNotIn("research_area", ui.session_state)
        self.assertEqual(len(list_management_evidence()), 2)
        with patch.object(evidence_ui, "list_management_evidence",
                          side_effect=ManagementEvidenceError("Browse unavailable")):
            ui.run()
            self.assertIn("Browse unavailable", ui.error[0].value)


if __name__ == "__main__":
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    if get_script_run_ctx(suppress_warning=True) is not None:
        import streamlit as st

        if st.session_state.get("_management_test_tracker"):
            evidence_ui.render_management_tracker()
        else:
            evidence_ui.render_management_evidence("PFE", "Pfizer")
    else:
        unittest.main()
