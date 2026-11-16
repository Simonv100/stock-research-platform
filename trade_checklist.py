"""Local reusable trading principles and review marks; no market or AI requests."""

from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, TypedDict
from urllib.parse import urlsplit


CHECKLIST_PATH = Path(__file__).resolve().parent / "data" / "trade_checklist.sqlite3"
DEFAULT_TITLE = "Crowded trades: check the thesis and trend"
DEFAULT_NOTE = (
    "Crowded trades can be acceptable as long as the investment thesis remains "
    "sound and the trend remains supportive."
)
DEFAULT_ATTRIBUTION = (
    "Attributed to Stanley Druckenmiller: user-supplied paraphrase, "
    "not a verified quotation."
)


class ChecklistError(RuntimeError):
    """A validation or storage error; existing checklist content is preserved."""


class ChecklistItem(TypedDict):
    id: int
    title: str
    note: str
    attribution: str
    source_url: str
    checked: bool
    revision: int


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    try:
        CHECKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(CHECKLIST_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS items ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, "
                    "note TEXT NOT NULL, attribution TEXT NOT NULL, source_url TEXT NOT NULL, "
                    "checked INTEGER NOT NULL DEFAULT 0 CHECK (checked IN (0, 1)), "
                    "revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL)"
                )
                connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY)")
                seeded = connection.execute(
                    "INSERT OR IGNORE INTO settings (key) VALUES ('initial-item-v1')"
                )
                if seeded.rowcount:
                    connection.execute(
                        "INSERT INTO items (title, note, attribution, source_url, updated_at) VALUES (?, ?, ?, ?, ?)",
                        (DEFAULT_TITLE, DEFAULT_NOTE, DEFAULT_ATTRIBUTION, "", _now()),
                    )
                yield connection
    except (OSError, sqlite3.Error) as exc:
        raise ChecklistError(f"Local trade checklist could not be accessed: {exc}") from exc


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fields(title: str, note: str, attribution: str, source_url: str) -> tuple[str, str, str, str]:
    for name, value, maximum in (
        ("Title", title, 160), ("Note", note, 4000),
        ("Attribution", attribution, 300), ("Source URL", source_url, 2000),
    ):
        if not isinstance(value, str) or len(value.strip()) > maximum:
            raise ChecklistError(f"{name} must be text of at most {maximum} characters.")
    title, note, attribution, source_url = (value.strip() for value in (title, note, attribution, source_url))
    if not title:
        raise ChecklistError("Enter a checklist item title.")
    if source_url:
        try:
            parsed = urlsplit(source_url)
            valid = (
                parsed.scheme in ("http", "https") and parsed.hostname
                and not parsed.username and not parsed.password
                and not any(character.isspace() for character in source_url)
            )
        except ValueError as exc:
            raise ChecklistError("Enter a valid public HTTP or HTTPS source URL.") from exc
        if not valid:
            raise ChecklistError("Enter a valid public HTTP or HTTPS source URL without credentials.")
    return title, note, attribution, source_url


def _identity(item_id: int, expected_revision: int) -> None:
    if type(item_id) is not int or item_id < 1 or type(expected_revision) is not int or expected_revision < 1:
        raise ChecklistError("A valid checklist item and saved revision are required.")


def _require_updated(cursor: sqlite3.Cursor) -> None:
    if cursor.rowcount != 1:
        raise ChecklistError("This checklist item changed or was removed in another view. Reload the checklist before retrying.")


def list_checklist_items() -> list[ChecklistItem]:
    with _database() as connection:
        return [
            ChecklistItem(
                id=row["id"], title=row["title"], note=row["note"], attribution=row["attribution"],
                source_url=row["source_url"], checked=bool(row["checked"]), revision=row["revision"],
            )
            for row in connection.execute("SELECT * FROM items ORDER BY id")
        ]


def add_checklist_item(title: str, note: str = "", attribution: str = "", source_url: str = "") -> None:
    fields = _fields(title, note, attribution, source_url)
    with _database() as connection:
        connection.execute(
            "INSERT INTO items (title, note, attribution, source_url, updated_at) VALUES (?, ?, ?, ?, ?)",
            (*fields, _now()),
        )


def update_checklist_item(
    item_id: int, expected_revision: int, title: str, note: str = "",
    attribution: str = "", source_url: str = "",
) -> None:
    _identity(item_id, expected_revision)
    fields = _fields(title, note, attribution, source_url)
    with _database() as connection:
        _require_updated(connection.execute(
            "UPDATE items SET title=?, note=?, attribution=?, source_url=?, checked=0, "
            "revision=revision+1, updated_at=? WHERE id=? AND revision=?",
            (*fields, _now(), item_id, expected_revision),
        ))


def set_checklist_checked(item_id: int, expected_revision: int, checked: bool) -> None:
    _identity(item_id, expected_revision)
    if type(checked) is not bool:
        raise ChecklistError("A checklist review mark must be true or false.")
    with _database() as connection:
        _require_updated(connection.execute(
            "UPDATE items SET checked=?, updated_at=? WHERE id=? AND revision=?",
            (int(checked), _now(), item_id, expected_revision),
        ))


def reset_checklist_checks() -> None:
    with _database() as connection:
        connection.execute(
            "UPDATE items SET checked=0, updated_at=? WHERE checked=1",
            (_now(),),
        )


def delete_checklist_item(item_id: int, expected_revision: int, *, confirmed: bool = False) -> None:
    _identity(item_id, expected_revision)
    if confirmed is not True:
        raise ChecklistError("Confirm removal of this checklist item.")
    with _database() as connection:
        _require_updated(connection.execute(
            "DELETE FROM items WHERE id=? AND revision=?", (item_id, expected_revision),
        ))
