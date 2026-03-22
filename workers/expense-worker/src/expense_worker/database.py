"""SQLite database lifecycle helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    actor_id TEXT,
    actor_name TEXT,
    amount_cents INTEGER NOT NULL,
    merchant TEXT NOT NULL,
    category TEXT NOT NULL,
    note TEXT,
    raw_text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_expenses_scope_created_at
ON expenses (scope, created_at);

CREATE TABLE IF NOT EXISTS expense_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id INTEGER NOT NULL,
    item_name TEXT NOT NULL,
    item_name_normalized TEXT NOT NULL,
    item_category TEXT NOT NULL,
    quantity REAL,
    unit TEXT,
    unit_price_cents INTEGER,
    line_total_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (expense_id) REFERENCES expenses(id)
);

CREATE INDEX IF NOT EXISTS idx_expense_items_expense_id
ON expense_items (expense_id);

CREATE INDEX IF NOT EXISTS idx_expense_items_name_normalized
ON expense_items (item_name_normalized);

CREATE TABLE IF NOT EXISTS expense_audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    actor_id TEXT,
    actor_name TEXT,
    request_text TEXT NOT NULL,
    command_kind TEXT,
    action TEXT NOT NULL,
    success INTEGER NOT NULL,
    expense_id INTEGER,
    reply_text TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (expense_id) REFERENCES expenses(id)
);

CREATE INDEX IF NOT EXISTS idx_expense_audit_scope_created_at
ON expense_audit_events (scope, created_at);
"""


def ensure_database(db_path: str) -> None:
    """Create the SQLite file and schema if missing."""

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA)
        _ensure_column(
            connection,
            table_name="expense_items",
            column_name="item_category",
            column_definition="TEXT NOT NULL DEFAULT 'Other'",
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_expense_items_category ON expense_items (item_category)"
        )
        connection.commit()


def connect(db_path: str) -> sqlite3.Connection:
    """Open a configured SQLite connection."""

    # FastAPI can execute dependency setup/teardown on different threads.
    # Disable sqlite's same-thread guard for this per-request connection model.
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    """Idempotently add a column when upgrading an existing local schema."""

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    existing = {str(row[1]) for row in rows}
    if column_name in existing:
        return
    connection.execute(
        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
    )
