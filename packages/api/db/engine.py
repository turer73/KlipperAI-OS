"""SQLite engine — senkron (SBC icin basit)."""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .tables import TABLES_SQL

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        for sql in TABLES_SQL:
            self._conn.execute(sql)
        self._conn.commit()
        logger.info("Database connected: %s", self.db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        assert self._conn is not None, "Database not connected"
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        if self._conn:
            self._conn.commit()

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        cursor = self.execute(sql, params)
        row = cursor.fetchone()
        return dict(row) if row else None
