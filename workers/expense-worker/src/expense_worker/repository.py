"""Persistence layer for expenses."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import sqlite3
from typing import Iterator

from .categories import ExpenseCategory


@dataclass(frozen=True)
class StoredExpense:
    """Database representation used internally by the service layer."""

    id: int
    scope: str
    actor_id: str | None
    actor_name: str | None
    amount_cents: int
    merchant: str
    category: str
    raw_text: str
    created_at: datetime


@dataclass(frozen=True)
class StoredAuditEvent:
    """Append-only audit entry for expense worker interactions."""

    id: int
    scope: str
    actor_id: str | None
    actor_name: str | None
    request_text: str
    command_kind: str | None
    action: str
    success: bool
    expense_id: int | None
    reply_text: str
    metadata_json: str
    created_at: datetime


@dataclass(frozen=True)
class StoredExpenseItem:
    """Database representation for one itemized receipt line."""

    id: int
    expense_id: int
    item_name: str
    item_name_normalized: str
    item_category: str
    quantity: float | None
    unit: str | None
    unit_price_cents: int | None
    line_total_cents: int
    created_at: datetime


@dataclass(frozen=True)
class StoredItemRollup:
    """Aggregated itemized spend over a query window."""

    item_name: str
    item_name_normalized: str
    total_cents: int
    line_count: int


class ExpenseRepository:
    """Encapsulates all expense database access."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit or roll back a unit of work as one atomic transaction."""

        try:
            yield
        except Exception:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def add_expense(
        self,
        *,
        scope: str,
        actor_id: str | None,
        actor_name: str | None,
        amount_cents: int,
        merchant: str,
        category: ExpenseCategory,
        raw_text: str,
        created_at: datetime,
    ) -> StoredExpense:
        """Insert an expense and return the stored record."""

        timestamp = created_at.isoformat()
        cursor = self._connection.execute(
            """
            INSERT INTO expenses (
                scope,
                actor_id,
                actor_name,
                amount_cents,
                merchant,
                category,
                raw_text,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope,
                actor_id,
                actor_name,
                amount_cents,
                merchant,
                category.value,
                raw_text,
                timestamp,
                timestamp,
            ),
        )
        return self.get_expense(cursor.lastrowid)

    def get_expense(self, expense_id: int) -> StoredExpense:
        """Fetch a single expense by identifier."""

        row = self._connection.execute(
            """
            SELECT id, scope, actor_id, actor_name, amount_cents, merchant, category, raw_text, created_at
            FROM expenses
            WHERE id = ?
            """,
            (expense_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Expense {expense_id} not found")
        return self._row_to_expense(row)

    def get_last_active_expense(self, scope: str) -> StoredExpense | None:
        """Return the most recent non-deleted expense in a scope."""

        row = self._connection.execute(
            """
            SELECT id, scope, actor_id, actor_name, amount_cents, merchant, category, raw_text, created_at
            FROM expenses
            WHERE scope = ? AND deleted_at IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (scope,),
        ).fetchone()
        return self._row_to_expense(row) if row else None

    def get_last_active_receipt(self, scope: str) -> StoredExpense | None:
        """Return the most recent non-deleted expense that has itemized receipt lines."""

        row = self._connection.execute(
            """
            SELECT e.id, e.scope, e.actor_id, e.actor_name, e.amount_cents, e.merchant, e.category, e.raw_text, e.created_at
            FROM expenses e
            WHERE e.scope = ?
              AND e.deleted_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM expense_items ei
                  WHERE ei.expense_id = e.id
              )
            ORDER BY e.id DESC
            LIMIT 1
            """,
            (scope,),
        ).fetchone()
        return self._row_to_expense(row) if row else None

    def update_last_category(self, scope: str, category: ExpenseCategory, now: datetime) -> StoredExpense | None:
        """Recategorize the most recent active expense."""

        expense = self.get_last_active_expense(scope)
        if expense is None:
            return None

        self._connection.execute(
            """
            UPDATE expenses
            SET category = ?, updated_at = ?
            WHERE id = ?
            """,
            (category.value, now.isoformat(), expense.id),
        )
        return self.get_expense(expense.id)

    def soft_delete_last(self, scope: str, now: datetime) -> StoredExpense | None:
        """Soft-delete the most recent active expense."""

        expense = self.get_last_active_expense(scope)
        if expense is None:
            return None

        self._connection.execute(
            """
            UPDATE expenses
            SET deleted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now.isoformat(), now.isoformat(), expense.id),
        )
        return expense

    def soft_delete_last_receipt(
        self,
        scope: str,
        now: datetime,
    ) -> tuple[StoredExpense, int] | None:
        """Soft-delete the most recent active receipt expense."""

        receipt = self.get_last_active_receipt(scope)
        if receipt is None:
            return None

        self._connection.execute(
            """
            UPDATE expenses
            SET deleted_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now.isoformat(), now.isoformat(), receipt.id),
        )

        row = self._connection.execute(
            """
            SELECT COUNT(*) AS item_count
            FROM expense_items
            WHERE expense_id = ?
            """,
            (receipt.id,),
        ).fetchone()
        item_count = int(row["item_count"]) if row is not None else 0
        return receipt, item_count

    def restore_last_deleted(self, scope: str, now: datetime) -> StoredExpense | None:
        """Restore the most recently deleted expense in a scope."""

        row = self._connection.execute(
            """
            SELECT id, scope, actor_id, actor_name, amount_cents, merchant, category, raw_text, created_at
            FROM expenses
            WHERE scope = ? AND deleted_at IS NOT NULL
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (scope,),
        ).fetchone()
        if row is None:
            return None

        expense = self._row_to_expense(row)
        self._connection.execute(
            """
            UPDATE expenses
            SET deleted_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (now.isoformat(), expense.id),
        )
        return self.get_expense(expense.id)

    def add_audit_event(
        self,
        *,
        scope: str,
        actor_id: str | None,
        actor_name: str | None,
        request_text: str,
        command_kind: str | None,
        action: str,
        success: bool,
        expense_id: int | None,
        reply_text: str,
        metadata: dict[str, object],
        created_at: datetime,
    ) -> StoredAuditEvent:
        """Insert an append-only audit record and return it."""

        metadata_json = json.dumps(metadata, sort_keys=True)
        cursor = self._connection.execute(
            """
            INSERT INTO expense_audit_events (
                scope,
                actor_id,
                actor_name,
                request_text,
                command_kind,
                action,
                success,
                expense_id,
                reply_text,
                metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scope,
                actor_id,
                actor_name,
                request_text,
                command_kind,
                action,
                1 if success else 0,
                expense_id,
                reply_text,
                metadata_json,
                created_at.isoformat(),
            ),
        )
        return self.get_audit_event(cursor.lastrowid)

    def add_expense_items(
        self,
        *,
        expense_id: int,
        items: list[dict[str, object]],
        created_at: datetime,
    ) -> list[StoredExpenseItem]:
        """Insert itemized receipt rows linked to an expense."""

        timestamp = created_at.isoformat()
        inserted_ids: list[int] = []
        for item in items:
            cursor = self._connection.execute(
                """
                INSERT INTO expense_items (
                    expense_id,
                    item_name,
                    item_name_normalized,
                    item_category,
                    quantity,
                    unit,
                    unit_price_cents,
                    line_total_cents,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    expense_id,
                    item["item_name"],
                    item["item_name_normalized"],
                    item["item_category"],
                    item["quantity"],
                    item["unit"],
                    item["unit_price_cents"],
                    item["line_total_cents"],
                    timestamp,
                ),
            )
            inserted_ids.append(int(cursor.lastrowid))

        return [self.get_expense_item(item_id) for item_id in inserted_ids]

    def get_expense_item(self, expense_item_id: int) -> StoredExpenseItem:
        """Fetch one receipt item by identifier."""

        row = self._connection.execute(
            """
            SELECT
                id,
                expense_id,
                item_name,
                item_name_normalized,
                item_category,
                quantity,
                unit,
                unit_price_cents,
                line_total_cents,
                created_at
            FROM expense_items
            WHERE id = ?
            """,
            (expense_item_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Expense item {expense_item_id} not found")
        return self._row_to_expense_item(row)

    def update_last_receipt_item_category(
        self,
        *,
        scope: str,
        item_name_normalized: str,
        category: ExpenseCategory,
    ) -> list[StoredExpenseItem]:
        """Recategorize matching items in the latest active expense for a scope."""

        expense = self.get_last_active_receipt(scope)
        if expense is None:
            return []

        self._connection.execute(
            """
            UPDATE expense_items
            SET item_category = ?
            WHERE expense_id = ?
              AND item_name_normalized LIKE '%' || ? || '%'
            """,
            (
                category.value,
                expense.id,
                item_name_normalized,
            ),
        )

        rows = self._connection.execute(
            """
            SELECT
                id,
                expense_id,
                item_name,
                item_name_normalized,
                item_category,
                quantity,
                unit,
                unit_price_cents,
                line_total_cents,
                created_at
            FROM expense_items
            WHERE expense_id = ?
              AND item_name_normalized LIKE '%' || ? || '%'
            ORDER BY id ASC
            """,
            (expense.id, item_name_normalized),
        ).fetchall()
        return [self._row_to_expense_item(row) for row in rows]

    def get_audit_event(self, audit_event_id: int) -> StoredAuditEvent:
        """Fetch a single audit event by identifier."""

        row = self._connection.execute(
            """
            SELECT
                id,
                scope,
                actor_id,
                actor_name,
                request_text,
                command_kind,
                action,
                success,
                expense_id,
                reply_text,
                metadata_json,
                created_at
            FROM expense_audit_events
            WHERE id = ?
            """,
            (audit_event_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"Audit event {audit_event_id} not found")
        return self._row_to_audit_event(row)

    def list_expenses_between(
        self,
        *,
        scope: str,
        start: datetime,
        end: datetime,
    ) -> list[StoredExpense]:
        """List active expenses inside a time window."""

        rows = self._connection.execute(
            """
            SELECT id, scope, actor_id, actor_name, amount_cents, merchant, category, raw_text, created_at
            FROM expenses
            WHERE scope = ?
              AND deleted_at IS NULL
              AND created_at >= ?
              AND created_at < ?
            ORDER BY created_at ASC, id ASC
            """,
            (scope, start.isoformat(), end.isoformat()),
        ).fetchall()
        return [self._row_to_expense(row) for row in rows]

    def sum_expenses_between(
        self,
        *,
        scope: str,
        category: ExpenseCategory | None,
        start: datetime,
        end: datetime,
    ) -> int:
        """Return the total amount in cents over a time window."""

        if category is None:
            row = self._connection.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS total
                FROM expenses
                WHERE scope = ?
                  AND deleted_at IS NULL
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (scope, start.isoformat(), end.isoformat()),
            ).fetchone()
        else:
            row = self._connection.execute(
                """
                SELECT COALESCE(SUM(amount_cents), 0) AS total
                FROM expenses
                WHERE scope = ?
                  AND category = ?
                  AND deleted_at IS NULL
                  AND created_at >= ?
                  AND created_at < ?
                """,
                (scope, category.value, start.isoformat(), end.isoformat()),
            ).fetchone()
        return int(row["total"])

    def sum_expenses_by_category_between(
        self,
        *,
        scope: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """Return grouped expense totals by category over a time window."""

        rows = self._connection.execute(
            """
            SELECT category, COALESCE(SUM(amount_cents), 0) AS total
            FROM expenses
            WHERE scope = ?
              AND deleted_at IS NULL
              AND created_at >= ?
              AND created_at < ?
            GROUP BY category
            ORDER BY total DESC, category ASC
            """,
            (scope, start.isoformat(), end.isoformat()),
        ).fetchall()
        return {str(row["category"]): int(row["total"]) for row in rows}

    def sum_effective_category_total_between(
        self,
        *,
        scope: str,
        category: ExpenseCategory,
        start: datetime,
        end: datetime,
    ) -> int:
        """Return category spend using receipt item categories when itemized data exists."""

        standalone_row = self._connection.execute(
            """
            SELECT COALESCE(SUM(e.amount_cents), 0) AS total
            FROM expenses e
            WHERE e.scope = ?
              AND e.category = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM expense_items ei
                  WHERE ei.expense_id = e.id
              )
            """,
            (scope, category.value, start.isoformat(), end.isoformat()),
        ).fetchone()

        itemized_row = self._connection.execute(
            """
            SELECT COALESCE(SUM(ei.line_total_cents), 0) AS total
            FROM expense_items ei
            JOIN expenses e ON e.id = ei.expense_id
            WHERE e.scope = ?
              AND ei.item_category = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
            """,
            (scope, category.value, start.isoformat(), end.isoformat()),
        ).fetchone()

        return int(standalone_row["total"]) + int(itemized_row["total"])

    def sum_effective_categories_between(
        self,
        *,
        scope: str,
        start: datetime,
        end: datetime,
    ) -> dict[str, int]:
        """Return category totals using itemized lines when receipts exist."""

        totals: dict[str, int] = {}

        standalone_rows = self._connection.execute(
            """
            SELECT e.category, COALESCE(SUM(e.amount_cents), 0) AS total
            FROM expenses e
            WHERE e.scope = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM expense_items ei
                  WHERE ei.expense_id = e.id
              )
            GROUP BY e.category
            """,
            (scope, start.isoformat(), end.isoformat()),
        ).fetchall()
        for row in standalone_rows:
            totals[str(row["category"])] = totals.get(str(row["category"]), 0) + int(row["total"])

        itemized_rows = self._connection.execute(
            """
            SELECT ei.item_category, COALESCE(SUM(ei.line_total_cents), 0) AS total
            FROM expense_items ei
            JOIN expenses e ON e.id = ei.expense_id
            WHERE e.scope = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
            GROUP BY ei.item_category
            """,
            (scope, start.isoformat(), end.isoformat()),
        ).fetchall()
        for row in itemized_rows:
            category = str(row["item_category"])
            totals[category] = totals.get(category, 0) + int(row["total"])

        return totals

    def sum_item_spend_between(
        self,
        *,
        scope: str,
        normalized_item_name: str,
        start: datetime,
        end: datetime,
    ) -> int:
        """Return item-level spend in cents over a time window."""

        row = self._connection.execute(
            """
            SELECT COALESCE(SUM(ei.line_total_cents), 0) AS total
            FROM expense_items ei
            JOIN expenses e ON e.id = ei.expense_id
            WHERE e.scope = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
              AND ei.item_name_normalized LIKE '%' || ? || '%'
            """,
            (
                scope,
                start.isoformat(),
                end.isoformat(),
                normalized_item_name,
            ),
        ).fetchone()
        return int(row["total"])

    def list_item_rollups_for_category_between(
        self,
        *,
        scope: str,
        category: ExpenseCategory,
        start: datetime,
        end: datetime,
    ) -> list[StoredItemRollup]:
        """Return itemized totals for one category over a time window."""

        rows = self._connection.execute(
            """
            SELECT
                MIN(ei.item_name) AS item_name,
                ei.item_name_normalized AS item_name_normalized,
                COALESCE(SUM(ei.line_total_cents), 0) AS total_cents,
                COUNT(*) AS line_count
            FROM expense_items ei
            JOIN expenses e ON e.id = ei.expense_id
            WHERE e.scope = ?
              AND ei.item_category = ?
              AND e.deleted_at IS NULL
              AND e.created_at >= ?
              AND e.created_at < ?
            GROUP BY ei.item_name_normalized
            ORDER BY total_cents DESC, item_name ASC
            """,
            (scope, category.value, start.isoformat(), end.isoformat()),
        ).fetchall()
        return [
            StoredItemRollup(
                item_name=str(row["item_name"]),
                item_name_normalized=str(row["item_name_normalized"]),
                total_cents=int(row["total_cents"]),
                line_count=int(row["line_count"]),
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_expense(row: sqlite3.Row) -> StoredExpense:
        return StoredExpense(
            id=int(row["id"]),
            scope=str(row["scope"]),
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            amount_cents=int(row["amount_cents"]),
            merchant=str(row["merchant"]),
            category=str(row["category"]),
            raw_text=str(row["raw_text"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    @staticmethod
    def _row_to_audit_event(row: sqlite3.Row) -> StoredAuditEvent:
        return StoredAuditEvent(
            id=int(row["id"]),
            scope=str(row["scope"]),
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            request_text=str(row["request_text"]),
            command_kind=row["command_kind"],
            action=str(row["action"]),
            success=bool(row["success"]),
            expense_id=int(row["expense_id"]) if row["expense_id"] is not None else None,
            reply_text=str(row["reply_text"]),
            metadata_json=str(row["metadata_json"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    @staticmethod
    def _row_to_expense_item(row: sqlite3.Row) -> StoredExpenseItem:
        return StoredExpenseItem(
            id=int(row["id"]),
            expense_id=int(row["expense_id"]),
            item_name=str(row["item_name"]),
            item_name_normalized=str(row["item_name_normalized"]),
            item_category=str(row["item_category"]),
            quantity=float(row["quantity"]) if row["quantity"] is not None else None,
            unit=str(row["unit"]) if row["unit"] is not None else None,
            unit_price_cents=int(row["unit_price_cents"]) if row["unit_price_cents"] is not None else None,
            line_total_cents=int(row["line_total_cents"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )
