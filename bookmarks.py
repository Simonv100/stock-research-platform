from __future__ import annotations

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


BOOKMARKS_PATH = Path(__file__).resolve().parent / "data" / "bookmarks.sqlite3"


class BookmarkError(RuntimeError):
    """Raised when local bookmarks cannot be read or saved."""


def _symbol_key(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized or any(character.isspace() for character in normalized):
        raise BookmarkError("A non-empty ticker symbol without spaces is required.")
    return normalized


@contextmanager
def _database() -> Iterator[sqlite3.Connection]:
    try:
        BOOKMARKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(BOOKMARKS_PATH, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS bookmarks ("
                    "symbol TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)"
                )
                yield connection
    except (OSError, sqlite3.Error) as exc:
        raise BookmarkError(f"Local bookmarks could not be accessed: {exc}") from exc


def list_bookmarks() -> list[dict[str, str]]:
    with _database() as connection:
        return [
            dict(row) for row in connection.execute(
                "SELECT symbol, name, created_at FROM bookmarks ORDER BY symbol"
            )
        ]


def add_bookmark(symbol: str, name: str) -> None:
    symbol = _symbol_key(symbol)
    with _database() as connection:
        connection.execute(
            "INSERT INTO bookmarks (symbol, name, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(symbol) DO NOTHING",
            (symbol, name.strip() or symbol, datetime.now(timezone.utc).isoformat()),
        )


def remove_bookmark(symbol: str) -> None:
    symbol = _symbol_key(symbol)
    with _database() as connection:
        connection.execute("DELETE FROM bookmarks WHERE symbol = ?", (symbol,))
