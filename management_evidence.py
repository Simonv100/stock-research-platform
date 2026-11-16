"""Local, manually assessed management evidence. Never fetches sources or calls AI.

Only ``ManagementManualAssessment`` is editable; ``ManagementStatus`` and
``ManagementFavorableFilterEligible`` are evidence/freshness-aware display fields.
Returned notes must not enter an AI context without the user's explicit consent.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing, contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import urlencode, urlsplit

from stock_chat import canonical_symbol
from stock_data import StockDataError


MANAGEMENT_EVIDENCE_PATH = (
    Path(__file__).resolve().parent / "data" / "management_evidence.sqlite3"
)
MANAGEMENT_STATUSES = ("Unreviewed", "Needs evidence", "Favorable", "Mixed", "Unfavorable")
CEO_ORIGINS = ("Unknown", "Internal", "External")
REVIEW_MAX_AGE_DAYS = 365

TEXT_FIELDS = (
    "ManagementCompanyName", "ManagementCEOName", "ManagementCEOAppointmentDate",
    "ManagementCEOBackground", "ManagementCEOOrigin", "ManagementCEOMandate",
    "ManagementIncentiveChangeDate", "ManagementOldMetrics", "ManagementNewMetrics",
    "ManagementPriceHurdles", "ManagementRelativeTSRHurdles",
    "ManagementMeasurementPeriod", "ManagementHoldingPeriod",
    "ManagementDilutionSafeguards", "ManagementResetSafeguards",
    "ManagementExecutionProgress", "ManagementNarrative",
    "ManagementOwnershipEvidence", "ManagementInsiderPurchaseEvidence",
    "ManagementReviewDate", "ManagementManualAssessment",
    "ManagementCEOSourceURL", "ManagementCEOSourceDate",
    "ManagementIncentiveSourceURL", "ManagementIncentiveSourceDate",
    "ManagementExecutionSourceURL", "ManagementExecutionSourceDate",
)
EDITABLE_FIELDS = frozenset((*TEXT_FIELDS, "ManagementSourcesConfirmedPrimary"))
DATE_FIELDS = tuple(field for field in TEXT_FIELDS if field.endswith("Date"))
SOURCE_PREFIXES = ("ManagementCEO", "ManagementIncentive", "ManagementExecution")
FAVORABLE_REQUIRED_FIELDS = {
    "ManagementReviewDate": "review date",
    "ManagementCEOName": "CEO name",
    "ManagementCEOAppointmentDate": "CEO appointment date",
    "ManagementCEOBackground": "CEO background",
    "ManagementCEOMandate": "CEO mandate",
    "ManagementIncentiveChangeDate": "incentive change date",
    "ManagementOldMetrics": "old incentive metrics",
    "ManagementNewMetrics": "new incentive metrics",
    "ManagementPriceHurdles": "price hurdles (or explicitly none/not disclosed)",
    "ManagementRelativeTSRHurdles": "relative TSR hurdles (or none/not disclosed)",
    "ManagementMeasurementPeriod": "measurement period",
    "ManagementHoldingPeriod": "holding period (or none/not disclosed)",
    "ManagementDilutionSafeguards": "dilution safeguards (or none/not disclosed)",
    "ManagementResetSafeguards": "reset safeguards (or none/not disclosed)",
    "ManagementExecutionProgress": "execution progress, including uncertainties",
    "ManagementNarrative": "assessment narrative",
    "ManagementCEOSourceURL": "primary CEO source URL",
    "ManagementCEOSourceDate": "CEO source publication date",
    "ManagementIncentiveSourceURL": "primary incentive source URL",
    "ManagementIncentiveSourceDate": "incentive source publication date",
}


class ManagementEvidenceError(RuntimeError):
    """A validation or local storage error; existing evidence is left intact."""


def _today() -> date:
    return date.today()


def _symbol_key(symbol: str) -> str:
    try:
        return canonical_symbol(symbol)
    except StockDataError as exc:
        raise ManagementEvidenceError(str(exc)) from exc


def _defaults() -> dict:
    return {
        **dict.fromkeys(TEXT_FIELDS, ""),
        "ManagementCEOOrigin": "Unknown",
        "ManagementManualAssessment": "Unreviewed",
        "ManagementSourcesConfirmedPrimary": False,
    }


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    try:
        MANAGEMENT_EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(MANAGEMENT_EVIDENCE_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS management_evidence ("
                    "symbol TEXT PRIMARY KEY, payload TEXT NOT NULL, "
                    "created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
                )
                yield connection
    except (OSError, sqlite3.Error) as exc:
        raise ManagementEvidenceError(
            f"Local management evidence could not be accessed: {exc}"
        ) from exc


def _payload(row: sqlite3.Row | None) -> dict:
    if row is None:
        return _defaults()
    try:
        stored = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ManagementEvidenceError("Saved management evidence is unreadable; not replaced.") from exc
    if not isinstance(stored, dict):
        raise ManagementEvidenceError("Saved management evidence is unreadable; not replaced.")
    data = {**_defaults(), **stored}
    _validate(data)
    return data


def _parse_date(value: str, label: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ManagementEvidenceError(f"{label} must use YYYY-MM-DD.") from exc
    if parsed.isoformat() != value:
        raise ManagementEvidenceError(f"{label} must use YYYY-MM-DD.")
    if parsed > _today():
        raise ManagementEvidenceError(f"{label} cannot be in the future.")
    return parsed


def _validate_url(value: str) -> None:
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in ("http", "https") and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and not any(character.isspace() or ord(character) < 32 for character in value)
            and "\\" not in value and parsed.port != 0
        )
    except ValueError as exc:
        raise ManagementEvidenceError("Sources must be valid public http(s) URLs.") from exc
    if not valid:
        raise ManagementEvidenceError("Sources must be valid public http(s) URLs without credentials.")


def _validate(data: dict) -> None:
    for field in TEXT_FIELDS:
        if not isinstance(data[field], str):
            raise ManagementEvidenceError(f"{field} must be text.")
    if type(data["ManagementSourcesConfirmedPrimary"]) is not bool:
        raise ManagementEvidenceError("Primary-source confirmation must be true or false.")
    if data["ManagementManualAssessment"] not in MANAGEMENT_STATUSES:
        raise ManagementEvidenceError("Choose a valid manual assessment.")
    if data["ManagementCEOOrigin"] not in CEO_ORIGINS:
        raise ManagementEvidenceError("CEO origin must be Unknown, Internal, or External.")
    for field in DATE_FIELDS:
        if data[field]:
            _parse_date(data[field], field)
    for prefix in SOURCE_PREFIXES:
        if data[f"{prefix}SourceURL"]:
            _validate_url(data[f"{prefix}SourceURL"])
    reviewed = data["ManagementReviewDate"]
    if reviewed and any(data[field] > reviewed for field in DATE_FIELDS if data[field]):
        raise ManagementEvidenceError(
            "Review date must be on or after the recorded event and source dates."
        )


def _evidence_gaps(data: dict) -> list[str]:
    gaps = [label for field, label in FAVORABLE_REQUIRED_FIELDS.items() if not data[field].strip()]
    if data["ManagementCEOOrigin"] == "Unknown":
        gaps.append("internal/external CEO origin")
    if not data["ManagementSourcesConfirmedPrimary"]:
        gaps.append("confirmation that the cited sources are primary documents")
    for prefix in SOURCE_PREFIXES:
        if bool(data[f"{prefix}SourceURL"]) != bool(data[f"{prefix}SourceDate"]):
            gaps.append(f"a paired URL and publication date for {prefix.removeprefix('Management')}")
    return gaps


def _view(symbol: str, row: sqlite3.Row | None) -> dict:
    data = _payload(row)
    reviewed = data["ManagementReviewDate"]
    age = (_today() - date.fromisoformat(reviewed)).days if reviewed else None
    stale = age is not None and age > REVIEW_MAX_AGE_DAYS
    gaps = _evidence_gaps(data)
    manual = data["ManagementManualAssessment"]
    status = manual
    if manual == "Favorable" and (gaps or stale):
        status = "Needs evidence"
    elif manual in ("Mixed", "Unfavorable") and (not reviewed or stale):
        status = "Needs evidence"
    elif manual == "Unreviewed" and (
        data["ManagementCEOOrigin"] != "Unknown" or any(
            value for field, value in data.items()
            if field in EDITABLE_FIELDS
            and field not in ("ManagementCompanyName", "ManagementManualAssessment", "ManagementCEOOrigin")
        )
    ):
        status = "Needs evidence"
    appointment = data["ManagementCEOAppointmentDate"]
    if status == "Unreviewed":
        reason = "No management assessment has been recorded. Unresearched does not mean unfavorable."
    elif stale:
        reason = (
            f"The saved {manual} judgment is older than 365 days; evidence and notes are "
            "preserved, but a fresh review is needed for favorable-filter eligibility."
        )
    elif status == "Needs evidence":
        reason = "Manual research is not yet a current favorable assessment."
        if gaps:
            remaining = f"; plus {len(gaps) - 3} other requirements" if len(gaps) > 3 else ""
            reason += " Favorable still requires: " + "; ".join(gaps[:3]) + remaining + "."
    elif status == "Favorable":
        reason = (
            "Explicit favorable user judgment with a current review and required dated "
            "primary-source citations recorded; not an automatic signal or verified alpha."
        )
    else:
        reason = f"Explicit {manual.lower()} user judgment; not an automatic investment signal."
    return {
        **{field: data[field] for field in EDITABLE_FIELDS},
        "ManagementSymbol": symbol,
        "ManagementStatus": status,
        "ManagementReason": reason,
        "ManagementReviewFreshness": (
            "Stale" if stale else "Current" if reviewed
            else "Unreviewed" if row is None else "Not dated"
        ),
        "ManagementReviewAgeDays": age,
        "ManagementReviewStale": stale,
        "ManagementNewCEO": bool(
            appointment and (_today() - date.fromisoformat(appointment)).days <= REVIEW_MAX_AGE_DAYS
        ),
        "ManagementFavorableFilterEligible": status == "Favorable",
        "ManagementEvidenceGaps": "; ".join(gaps),
        "ManagementCreatedAt": row["created_at"] if row else "",
        "ManagementUpdatedAt": row["updated_at"] if row else "",
    }


def get_management_evidence(symbol: str) -> dict:
    """Return flat JSON-safe Management* fields; missing symbols are Unreviewed."""
    symbol = _symbol_key(symbol)
    with _database() as connection:
        row = connection.execute(
            "SELECT * FROM management_evidence WHERE symbol = ?", (symbol,)
        ).fetchone()
    return _view(symbol, row)


def list_management_evidence() -> list[dict]:
    """Return saved reviews only, sorted by canonical listing symbol."""
    with _database() as connection:
        rows = connection.execute("SELECT * FROM management_evidence ORDER BY symbol").fetchall()
    return [_view(row["symbol"], row) for row in rows]


def save_management_evidence(
    symbol: str, fields: Mapping, *, expected_updated_at: str | None = None,
) -> dict:
    """Merge editable Management* fields, preserving omitted data.

    Favorable is an explicit, evidence-backed user judgment, never an automatic
    signal. Supply the last ManagementUpdatedAt ("" for a new review) to prevent
    overwriting another editor's changes.
    """
    symbol = _symbol_key(symbol)
    if not isinstance(fields, Mapping):
        raise ManagementEvidenceError("Evidence fields must be a mapping.")
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ManagementEvidenceError(f"Unknown or read-only evidence fields: {sorted(map(str, unknown))}")
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM management_evidence WHERE symbol = ?", (symbol,)
        ).fetchone()
        _check_version(row, expected_updated_at)
        data = _payload(row)
        data.update({field: value.strip() if isinstance(value, str) else value
                     for field, value in fields.items()})
        _validate(data)
        if data["ManagementManualAssessment"] == "Favorable":
            gaps = _evidence_gaps(data)
            if gaps:
                raise ManagementEvidenceError(
                    "Favorable requires: " + "; ".join(gaps)
                    + ". Save as Needs evidence while researching."
                )
            age = (_today() - date.fromisoformat(data["ManagementReviewDate"])).days
            if age > REVIEW_MAX_AGE_DAYS:
                raise ManagementEvidenceError(
                    "Favorable requires a review within 365 days. Refresh the review "
                    "or save as Needs evidence; the previous record has not been changed."
                )
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO management_evidence (symbol, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(symbol) DO UPDATE SET "
            "payload = excluded.payload, updated_at = excluded.updated_at",
            (symbol, json.dumps(data, ensure_ascii=False), row["created_at"] if row else now, now),
        )
        saved = connection.execute(
            "SELECT * FROM management_evidence WHERE symbol = ?", (symbol,)
        ).fetchone()
    return _view(symbol, saved)


def _check_version(row: sqlite3.Row | None, expected_updated_at: str | None) -> None:
    if expected_updated_at is not None:
        current = row["updated_at"] if row else ""
        if expected_updated_at != current:
            raise ManagementEvidenceError(
                "This review changed in another editor. Reload before saving or resetting."
            )


def reset_management_evidence(
    symbol: str, *, confirmed: bool = False, expected_updated_at: str | None = None,
) -> None:
    """Delete only this listing after explicit confirmation; other reviews survive."""
    symbol = _symbol_key(symbol)
    if confirmed is not True:
        raise ManagementEvidenceError("Confirm the reset explicitly; saved evidence is unchanged.")
    with _database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT * FROM management_evidence WHERE symbol = ?", (symbol,)
        ).fetchone()
        _check_version(row, expected_updated_at)
        connection.execute("DELETE FROM management_evidence WHERE symbol = ?", (symbol,))


def management_search_links(symbol: str, company_name: str = "") -> dict[str, str]:
    """Ordinary encoded search links only. Calling this does not access a network."""
    symbol = _symbol_key(symbol)
    identity = f"{symbol} {str(company_name).strip()}".strip()
    searches = {
        "CEO appointment / background": "CEO appointment background mandate investor relations",
        "Proxy / DEF 14A": "proxy DEF 14A executive compensation incentive performance metrics",
        "Remuneration report": "annual remuneration report performance shares relative TSR holding period",
        "8-K management / pay changes": "8-K CEO appointment compensation incentive plan",
        "Execution updates": "investor relations results strategy execution progress",
    }
    return {
        label: "https://www.google.com/search?" + urlencode({"q": f"{identity} {query}"})
        for label, query in searches.items()
    }
