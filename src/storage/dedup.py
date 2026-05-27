from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from src.models import RawItem

DEFAULT_DB_PATH = Path("data/state.db")


class DedupStore:
    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_items (
                    dedup_key TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    seen_at TEXT NOT NULL
                )
                """
            )

    def filter_new(self, items: list[RawItem]) -> list[RawItem]:
        if not items:
            return []

        keys = [item.dedup_key for item in items]
        placeholders = ",".join("?" for _ in keys)

        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT dedup_key FROM seen_items WHERE dedup_key IN ({placeholders})",
                keys,
            ).fetchall()
            seen = {row[0] for row in rows}

        return [item for item in items if item.dedup_key not in seen]

    def mark_seen(self, items: list[RawItem]) -> None:
        if not items:
            return

        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (item.dedup_key, item.source, item.id, item.url, now)
            for item in items
        ]

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO seen_items
                (dedup_key, source, item_id, url, seen_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
