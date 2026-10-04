"""SQLite-backed storage helpers for the expense tracker."""
from __future__ import annotations

import itertools
import sqlite3
import threading

_request_ids = itertools.count(1)

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    category TEXT NOT NULL,
    day TEXT NOT NULL,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS budgets (
    user TEXT NOT NULL,
    month TEXT NOT NULL,
    limit_cents INTEGER NOT NULL,
    PRIMARY KEY (user, month)
);
"""


class Database:
    """Hands out one connection per request and tracks which are still open.

    Handlers call acquire() when they start touching the database and
    release() when they are done so connections cannot pile up.
    """

    def __init__(self, path: str):
        self.path = path
        self._connections: dict[int, sqlite3.Connection] = {}
        self._lock = threading.Lock()
        setup = sqlite3.connect(self.path)
        setup.executescript(SCHEMA)
        setup.close()

    def acquire(self) -> tuple[int, sqlite3.Connection]:
        request_id = next(_request_ids)
        conn = sqlite3.connect(self.path)
        conn.execute("SELECT 1")  # warm the connection before handing it out
        with self._lock:
            self._connections[request_id] = conn
        return request_id, conn

    def release(self, request_id: int) -> None:
        with self._lock:
            conn = self._connections.pop(request_id, None)
        if conn is not None:
            conn.close()

    def open_count(self) -> int:
        with self._lock:
            return len(self._connections)
