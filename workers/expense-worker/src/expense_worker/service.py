"""Application service for expense operations."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, time, timedelta
import re
from typing import Callable

from .categories import ExpenseCategory, list_category_names, normalize_category
from .models import (
    ExpenseCommandRequest,
    ExpenseCommandResponse,
    ReceiptIngestRequest,
    StructuredExpenseCommandRequest,
)
from .parser import CommandKind, ParsedCommand, infer_category, parse_command
from .repository import ExpenseRepository, StoredAuditEvent, StoredExpense, StoredExpenseItem, StoredItemRollup

AMOUNT_TOKEN_RE = re.compile(r"^\$?\s*(\d+(?:\.\d{1,2})?)\s*$")
JAMBRA_ITEM_KEYWORDS = {
    "chips",
    "chocolate",
    "cookie",
    "cookies",
    "cake",
    "ice cream",
    "candy",
    "soda",
    "snack",
    "snacks",
    "junk",
    "dessert",
    "brownie",
}
BABY_ITEM_KEYWORDS = {
    "baby",
    "diaper",
    "diapers",
    "wipes",
    "formula",
    "enfamil",
    "similac",
    "pampers",
    "huggies",
    "baby powder",
}
TRANSPORT_ITEM_KEYWORDS = {"gas", "fuel", "toll", "parking", "uber", "lyft", "oil change", "service"}
HOME_MAINTENANCE_ITEM_KEYWORDS = {"cleaner", "yard", "repair", "maintenance", "plumber", "handyman"}


class ExpenseService:
    """High-level orchestration for expense commands."""

    def __init__(
        self,
        repository: ExpenseRepository,
        timezone,
        allowed_scopes: frozenset[str] | None = None,
    ) -> None:
        self._repository = repository
        self._timezone = timezone
        self._allowed_scopes = allowed_scopes

    def handle(self, request: ExpenseCommandRequest) -> ExpenseCommandResponse:
        """Process a chat request end to end."""

        now = datetime.now(self._timezone)
        parsed: ParsedCommand | None = None
        with self._repository.transaction():
            try:
                parsed = self._resolve_command(request)
                response = self._dispatch_parsed_command(request, parsed, now)
            except ValueError as exc:
                response = ExpenseCommandResponse(
                    action="validation_error",
                    reply_text=str(exc),
                    metadata={},
                )

            expense_id = self._extract_expense_id(response)
            audit_event = self._repository.add_audit_event(
                scope=request.scope,
                actor_id=request.actor_id,
                actor_name=request.actor_name,
                request_text=request.text,
                command_kind=self._audit_command_kind(request, parsed),
                action=response.action,
                success=response.action != "validation_error",
                expense_id=expense_id,
                reply_text=response.reply_text,
                metadata=response.metadata,
                created_at=now,
            )
            response.metadata["audit_event"] = serialize_audit_event(audit_event)
            return response

    def handle_structured(self, request: StructuredExpenseCommandRequest) -> ExpenseCommandResponse:
        """Process a structured tool request end to end."""

        now = datetime.now(self._timezone)
        parsed: ParsedCommand | None = None
        request_text = self._summarize_structured_request(request)
        domain_request = ExpenseCommandRequest(
            text=request_text,
            scope=request.scope,
            actor_name=request.actor_name,
            actor_id=request.actor_id,
        )

        with self._repository.transaction():
            try:
                parsed = self._resolve_structured_command(request)
                response = self._dispatch_parsed_command(domain_request, parsed, now)
            except ValueError as exc:
                response = ExpenseCommandResponse(
                    action="validation_error",
                    reply_text=str(exc),
                    metadata={},
                )

            expense_id = self._extract_expense_id(response)
            audit_event = self._repository.add_audit_event(
                scope=request.scope,
                actor_id=request.actor_id,
                actor_name=request.actor_name,
                request_text=request_text,
                command_kind=parsed.kind.value if parsed is not None else request.action,
                action=response.action,
                success=response.action != "validation_error",
                expense_id=expense_id,
                reply_text=response.reply_text,
                metadata=response.metadata,
                created_at=now,
            )
            response.metadata["audit_event"] = serialize_audit_event(audit_event)
            return response

    def _resolve_command(self, request: ExpenseCommandRequest) -> ParsedCommand:
        """Resolve a worker request into a validated domain command."""

        self._validate_scope(request.scope)
        return parse_command(request.text)

    def _resolve_structured_command(self, request: StructuredExpenseCommandRequest) -> ParsedCommand:
        """Convert a structured tool request into the domain command shape."""

        self._validate_scope(request.scope)

        if request.action == "add_expense":
            amount = request.amount
            if amount is None:
                raise ValueError("This expense add request is missing an amount.")

            merchant = _normalize_structured_text(request.merchant) or "Unknown"
            category = (
                self._require_category(request.category)
                if request.category is not None
                else infer_category(request.raw_text or merchant, merchant if merchant != "Unknown" else None)
            )
            return ParsedCommand(
                kind=CommandKind.ADD,
                amount_cents=_parse_money_to_cents(amount),
                merchant=merchant,
                category=category,
            )

        if request.action == "change_last_category":
            return ParsedCommand(
                kind=CommandKind.CHANGE_LAST_CATEGORY,
                category=self._require_category(request.category),
            )

        if request.action == "change_last_receipt_item_category":
            item_name = _normalize_structured_item_name(request.item_name)
            return ParsedCommand(
                kind=CommandKind.CHANGE_LAST_ITEM_CATEGORY,
                item_name=item_name,
                category=self._require_category(request.category),
            )

        if request.action == "delete_last":
            return ParsedCommand(kind=CommandKind.DELETE_LAST)

        if request.action == "delete_last_receipt":
            return ParsedCommand(kind=CommandKind.DELETE_LAST_RECEIPT)

        if request.action == "undo_last":
            return ParsedCommand(kind=CommandKind.UNDO_LAST)

        if request.action == "list_expenses":
            return ParsedCommand(
                kind=CommandKind.LIST_EXPENSES,
                timeframe=request.timeframe or "today",
            )

        if request.action == "total":
            return ParsedCommand(
                kind=CommandKind.TOTAL,
                category=self._optional_category(request.category),
                timeframe=request.timeframe or "this month",
            )

        if request.action == "category_breakdown":
            return ParsedCommand(
                kind=CommandKind.CATEGORY_BREAKDOWN,
                timeframe=request.timeframe or "this month",
            )

        if request.action == "category_item_breakdown":
            return ParsedCommand(
                kind=CommandKind.CATEGORY_ITEM_BREAKDOWN,
                category=self._require_category(request.category),
                timeframe=request.timeframe or "this month",
            )

        if request.action == "item_total":
            return ParsedCommand(
                kind=CommandKind.ITEM_TOTAL,
                item_name=_normalize_structured_item_name(request.item_name),
                timeframe=request.timeframe or "this month",
            )

        if request.action == "item_presence":
            return ParsedCommand(
                kind=CommandKind.ITEM_PRESENCE,
                item_name=_normalize_structured_item_name(request.item_name),
                timeframe=request.timeframe or "this month",
            )

        if request.action == "list_categories":
            return ParsedCommand(kind=CommandKind.LIST_CATEGORIES)

        raise ValueError(f"Unsupported structured action: {request.action}")

    def _dispatch_parsed_command(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        """Route a parsed command to its command handler."""

        handlers: dict[CommandKind, Callable[[], ExpenseCommandResponse]] = {
            CommandKind.ADD: lambda: self._handle_add(request, parsed, now),
            CommandKind.CHANGE_LAST_CATEGORY: lambda: self._handle_change_last(request, parsed, now),
            CommandKind.CHANGE_LAST_ITEM_CATEGORY: lambda: self._handle_change_last_item_category(request, parsed),
            CommandKind.DELETE_LAST: lambda: self._handle_delete_last(request, now),
            CommandKind.DELETE_LAST_RECEIPT: lambda: self._handle_delete_last_receipt(request, now),
            CommandKind.UNDO_LAST: lambda: self._handle_undo_last(request, now),
            CommandKind.SHOW_TODAY: lambda: self._handle_list_expenses(request, "today", now),
            CommandKind.LIST_EXPENSES: lambda: self._handle_list_expenses(request, parsed.timeframe or "today", now),
            CommandKind.TOTAL: lambda: self._handle_total(request, parsed, now),
            CommandKind.CATEGORY_BREAKDOWN: lambda: self._handle_category_breakdown(request, parsed, now),
            CommandKind.CATEGORY_ITEM_BREAKDOWN: lambda: self._handle_category_item_breakdown(request, parsed, now),
            CommandKind.ITEM_TOTAL: lambda: self._handle_item_total(request, parsed, now),
            CommandKind.ITEM_PRESENCE: lambda: self._handle_item_presence(request, parsed, now),
            CommandKind.LIST_CATEGORIES: self._handle_list_categories,
        }
        try:
            handler = handlers[parsed.kind]
        except KeyError as exc:
            raise ValueError(f"Unsupported action: {parsed.kind}") from exc
        return handler()

    def _handle_add(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        expense = self._repository.add_expense(
            scope=request.scope,
            actor_id=request.actor_id,
            actor_name=request.actor_name,
            amount_cents=parsed.amount_cents or 0,
            merchant=parsed.merchant or "Unknown",
            category=parsed.category or ExpenseCategory.OTHER,
            raw_text=request.text,
            created_at=now,
        )
        if expense.merchant == "Unknown":
            reply = f"Saved {format_amount(expense.amount_cents)} under {expense.category}."
        else:
            reply = (
                f"Saved {format_amount(expense.amount_cents)} at {expense.merchant} "
                f"under {expense.category}."
            )
        return ExpenseCommandResponse(
            action="expense_added",
            reply_text=reply,
            metadata={"expense": serialize_expense(expense)},
        )

    def _handle_change_last(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        expense = self._repository.update_last_category(
            request.scope,
            parsed.category or ExpenseCategory.OTHER,
            now,
        )
        if expense is None:
            return ExpenseCommandResponse(
                action="no_expense_to_update",
                reply_text="There is no recent expense to update.",
            )

        return ExpenseCommandResponse(
            action="expense_updated",
            reply_text=(
                f"Updated the last expense: {format_amount(expense.amount_cents)} at "
                f"{expense.merchant} is now under {expense.category}."
            ),
            metadata={"expense": serialize_expense(expense)},
        )

    def _handle_delete_last(
        self,
        request: ExpenseCommandRequest,
        now: datetime,
    ) -> ExpenseCommandResponse:
        expense = self._repository.soft_delete_last(request.scope, now)
        if expense is None:
            return ExpenseCommandResponse(
                action="no_expense_to_delete",
                reply_text="There is no recent expense to delete.",
            )

        return ExpenseCommandResponse(
            action="expense_deleted",
            reply_text=(
                f"Deleted the last expense: {format_amount(expense.amount_cents)} at "
                f"{expense.merchant} from {expense.category}."
            ),
            metadata={"expense": serialize_expense(expense)},
        )

    def _handle_list_expenses(
        self,
        request: ExpenseCommandRequest,
        timeframe: str,
        now: datetime,
    ) -> ExpenseCommandResponse:
        start, end = window_for_timeframe(now, timeframe)
        expenses = self._repository.list_expenses_between(
            scope=request.scope,
            start=start,
            end=end,
        )
        if not expenses:
            return ExpenseCommandResponse(
                action="expense_list_empty",
                reply_text=f"No expenses logged for {timeframe}.",
                metadata={"expenses": [], "timeframe": timeframe},
            )

        total_cents = sum(expense.amount_cents for expense in expenses)
        lines = [
            f"- {format_amount(expense.amount_cents)} at {expense.merchant} ({expense.category})"
            for expense in expenses
        ]
        reply = f"Expenses for {timeframe}:\n" + "\n".join(lines) + f"\nTotal: {format_amount(total_cents)}"
        return ExpenseCommandResponse(
            action="expense_list",
            reply_text=reply,
            metadata={
                "expenses": [serialize_expense(expense) for expense in expenses],
                "timeframe": timeframe,
                "total_cents": total_cents,
            },
        )

    def _handle_delete_last_receipt(
        self,
        request: ExpenseCommandRequest,
        now: datetime,
    ) -> ExpenseCommandResponse:
        """Delete the most recent active receipt (expense with itemized lines)."""

        deleted = self._repository.soft_delete_last_receipt(request.scope, now)
        if deleted is None:
            return ExpenseCommandResponse(
                action="no_receipt_to_delete",
                reply_text="There is no recent receipt to delete.",
            )

        expense, item_count = deleted
        this_week_start, this_week_end = window_for_timeframe(now, "this week")
        this_week_total_cents = self._repository.sum_expenses_between(
            scope=request.scope,
            category=None,
            start=this_week_start,
            end=this_week_end,
        )
        return ExpenseCommandResponse(
            action="receipt_deleted",
            reply_text=(
                f"Deleted the last receipt: {expense.merchant} "
                f"({format_amount(expense.amount_cents)}, {item_count} item(s)). "
                f"This week's total is now {format_amount(this_week_total_cents)}."
            ),
            metadata={
                "expense": serialize_expense(expense),
                "item_count": item_count,
                "this_week_total_cents": this_week_total_cents,
            },
        )

    def _handle_undo_last(
        self,
        request: ExpenseCommandRequest,
        now: datetime,
    ) -> ExpenseCommandResponse:
        expense = self._repository.restore_last_deleted(request.scope, now)
        if expense is None:
            return ExpenseCommandResponse(
                action="nothing_to_undo",
                reply_text="There is nothing to undo right now.",
            )

        return ExpenseCommandResponse(
            action="expense_restored",
            reply_text=(
                f"Restored the last deleted expense: {format_amount(expense.amount_cents)} at "
                f"{expense.merchant} in {expense.category}."
            ),
            metadata={"expense": serialize_expense(expense)},
        )

    def _handle_total(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        timeframe = parsed.timeframe or "this week"
        start, end = window_for_timeframe(now, timeframe)
        if parsed.category is None:
            total_cents = self._repository.sum_expenses_between(
                scope=request.scope,
                category=None,
                start=start,
                end=end,
            )
        else:
            total_cents = self._repository.sum_effective_category_total_between(
                scope=request.scope,
                category=parsed.category,
                start=start,
                end=end,
            )
        category_label = parsed.category.value if parsed.category is not None else "Total"
        return ExpenseCommandResponse(
            action="expense_total",
            reply_text=(
                f"{category_label} spend for {timeframe} is {format_amount(total_cents)}."
            ),
            metadata={
                "category": parsed.category.value if parsed.category is not None else None,
                "timeframe": timeframe,
                "total_cents": total_cents,
            },
        )

    def _handle_category_breakdown(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        """Return spend totals by category for a given timeframe."""

        timeframe = parsed.timeframe or "this month"
        start, end = window_for_timeframe(now, timeframe)
        totals_by_category = self._repository.sum_effective_categories_between(
            scope=request.scope,
            start=start,
            end=end,
        )

        ordered_categories = list_category_names()
        lines = [f"- {category}: {format_amount(totals_by_category.get(category, 0))}" for category in ordered_categories]
        total_cents = sum(totals_by_category.values())
        return ExpenseCommandResponse(
            action="category_breakdown",
            reply_text=(
                f"Category breakdown for {timeframe}:\n"
                + "\n".join(lines)
                + f"\nTotal: {format_amount(total_cents)}"
            ),
            metadata={
                "timeframe": timeframe,
                "breakdown": {
                    category: totals_by_category.get(category, 0)
                    for category in ordered_categories
                },
                "total_cents": total_cents,
            },
        )

    def _handle_category_item_breakdown(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        """Return aggregated itemized spend for one category over a timeframe."""

        category = parsed.category
        if category is None:
            raise ValueError("Category item breakdown is missing a category.")

        timeframe = parsed.timeframe or "this month"
        start, end = window_for_timeframe(now, timeframe)
        rollups = self._repository.list_item_rollups_for_category_between(
            scope=request.scope,
            category=category,
            start=start,
            end=end,
        )
        if not rollups:
            return ExpenseCommandResponse(
                action="category_item_breakdown_empty",
                reply_text=f"No itemized {category.value} purchases found for {timeframe}.",
                metadata={
                    "category": category.value,
                    "timeframe": timeframe,
                    "items": [],
                    "total_cents": 0,
                },
            )

        total_cents = sum(rollup.total_cents for rollup in rollups)
        lines = [f"- {rollup.item_name}: {format_amount(rollup.total_cents)}" for rollup in rollups]
        return ExpenseCommandResponse(
            action="category_item_breakdown",
            reply_text=(
                f"Item breakdown for {category.value} during {timeframe}:\n"
                + "\n".join(lines)
                + f"\nTotal: {format_amount(total_cents)}"
            ),
            metadata={
                "category": category.value,
                "timeframe": timeframe,
                "items": [serialize_item_rollup(rollup) for rollup in rollups],
                "total_cents": total_cents,
            },
        )

    def _handle_change_last_item_category(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
    ) -> ExpenseCommandResponse:
        """Recategorize a matching item in the most recent receipt."""

        if parsed.item_name is None or parsed.category is None:
            raise ValueError("Item category update requires both item name and category.")

        updated_items = self._repository.update_last_receipt_item_category(
            scope=request.scope,
            item_name_normalized=parsed.item_name,
            category=parsed.category,
        )
        if not updated_items:
            return ExpenseCommandResponse(
                action="no_receipt_item_to_update",
                reply_text=f"No matching item found for '{parsed.item_name}' in the last receipt.",
            )

        lines = "\n".join(
            f"- {item.item_name}: {format_amount(item.line_total_cents)} -> {item.item_category}"
            for item in updated_items
        )
        return ExpenseCommandResponse(
            action="receipt_item_category_updated",
            reply_text=(
                f"Updated {len(updated_items)} item(s) in the last receipt to {parsed.category.value}:\n{lines}"
            ),
            metadata={
                "item_name": parsed.item_name,
                "category": parsed.category.value,
                "updated_count": len(updated_items),
                "items": [serialize_expense_item(item) for item in updated_items],
            },
        )

    def _handle_item_total(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        item_name = parsed.item_name
        if item_name is None:
            raise ValueError("Itemized spend query is missing an item name.")

        timeframe = parsed.timeframe or "this month"
        start, end = window_for_timeframe(now, timeframe)
        total_cents = self._repository.sum_item_spend_between(
            scope=request.scope,
            normalized_item_name=item_name,
            start=start,
            end=end,
        )
        return ExpenseCommandResponse(
            action="item_expense_total",
            reply_text=f"Spend on {item_name} for {timeframe} is {format_amount(total_cents)}.",
            metadata={
                "item_name": item_name,
                "timeframe": timeframe,
                "total_cents": total_cents,
            },
        )

    def _handle_item_presence(
        self,
        request: ExpenseCommandRequest,
        parsed: ParsedCommand,
        now: datetime,
    ) -> ExpenseCommandResponse:
        """Answer yes/no item purchase questions from receipt line items."""

        item_name = parsed.item_name
        if item_name is None:
            raise ValueError("Item presence query is missing an item name.")

        timeframe = parsed.timeframe or "this month"
        start, end = window_for_timeframe(now, timeframe)
        total_cents = self._repository.sum_item_spend_between(
            scope=request.scope,
            normalized_item_name=item_name,
            start=start,
            end=end,
        )
        found = total_cents > 0
        reply_text = (
            f"Yes — {item_name} spend for {timeframe} is {format_amount(total_cents)}."
            if found
            else f"No — no {item_name} found for {timeframe}."
        )
        return ExpenseCommandResponse(
            action="item_presence",
            reply_text=reply_text,
            metadata={
                "item_name": item_name,
                "timeframe": timeframe,
                "found": found,
                "total_cents": total_cents,
            },
        )

    def _handle_list_categories(self) -> ExpenseCommandResponse:
        """Return the supported Denkeeper expense categories."""

        categories = list_category_names()
        reply = "Supported categories:\n" + "\n".join(f"- {category}" for category in categories)
        return ExpenseCommandResponse(
            action="expense_categories",
            reply_text=reply,
            metadata={"categories": categories},
        )

    def _require_category(self, category_name: str | None) -> ExpenseCategory:
        """Resolve a required category name into the canonical category enum."""

        if category_name is None:
            raise ValueError("This request is missing a category.")
        category = normalize_category(category_name)
        if category is None:
            raise ValueError(f"Unsupported category: {category_name}")
        return category

    def _optional_category(self, category_name: str | None) -> ExpenseCategory | None:
        """Resolve an optional category name into the canonical category enum."""

        if category_name is None:
            return None
        return self._require_category(category_name)

    def _summarize_structured_request(self, request: StructuredExpenseCommandRequest) -> str:
        """Build a stable audit text when the tool sends structured fields."""

        if request.raw_text:
            return request.raw_text

        parts = [request.action]
        if request.amount:
            parts.append(f"amount={request.amount}")
        if request.merchant:
            parts.append(f"merchant={request.merchant}")
        if request.category:
            parts.append(f"category={request.category}")
        if request.timeframe:
            parts.append(f"timeframe={request.timeframe}")
        if request.item_name:
            parts.append(f"item={request.item_name}")
        return " ".join(parts)

    @staticmethod
    def _extract_expense_id(response: ExpenseCommandResponse) -> int | None:
        """Return the linked expense identifier when a response references one."""

        expense = response.metadata.get("expense")
        if isinstance(expense, dict):
            expense_id = expense.get("id")
            if isinstance(expense_id, int):
                return expense_id
        return None

    @staticmethod
    def _audit_command_kind(
        request: ExpenseCommandRequest,
        parsed: ParsedCommand | None,
    ) -> str | None:
        """Choose the most informative command kind for audit rows."""

        _ = request
        if parsed is not None:
            return parsed.kind.value
        return None

    def ingest_receipt(self, request: ReceiptIngestRequest) -> ExpenseCommandResponse:
        """Persist a structured, itemized receipt into expenses + line items."""

        try:
            self._validate_scope(request.scope)
        except ValueError as exc:
            return ExpenseCommandResponse(
                action="validation_error",
                reply_text=str(exc),
            )

        now = datetime.now(self._timezone)
        created_at = _coerce_to_timezone(request.purchased_at, now, self._timezone)

        category = ExpenseCategory.GROCERIES
        if request.category is not None:
            normalized = normalize_category(request.category)
            if normalized is None:
                return ExpenseCommandResponse(
                    action="validation_error",
                    reply_text=f"Unsupported category: {request.category}",
                )
            category = normalized

        try:
            parsed_items = [
                _parse_receipt_item_payload(item.model_dump(), default_category=category)
                for item in request.items
            ]
            computed_total = sum(int(item["line_total_cents"]) for item in parsed_items)
            receipt_total_cents = (
                _parse_money_to_cents(request.receipt_total)
                if request.receipt_total is not None
                else computed_total
            )
        except ValueError as exc:
            return ExpenseCommandResponse(
                action="validation_error",
                reply_text=str(exc),
            )

        with self._repository.transaction():
            expense = self._repository.add_expense(
                scope=request.scope,
                actor_id=request.actor_id,
                actor_name=request.actor_name,
                amount_cents=receipt_total_cents,
                merchant=request.merchant.strip(),
                category=category,
                raw_text=request.raw_text or f"receipt import {request.merchant.strip()}",
                created_at=created_at,
            )
            inserted_items = self._repository.add_expense_items(
                expense_id=expense.id,
                items=parsed_items,
                created_at=created_at,
            )
            response = ExpenseCommandResponse(
                action="receipt_added",
                reply_text=(
                    f"Saved receipt from {expense.merchant}: {len(inserted_items)} items, "
                    f"total {format_amount(expense.amount_cents)} under {expense.category}.\n"
                    f"{_format_receipt_items(inserted_items)}"
                ),
                metadata={
                    "expense": serialize_expense(expense),
                    "item_count": len(inserted_items),
                    "computed_total_cents": computed_total,
                    "receipt_total_cents": receipt_total_cents,
                    "total_mismatch": computed_total != receipt_total_cents,
                    "items": [serialize_expense_item(item) for item in inserted_items],
                },
            )
            audit_event = self._repository.add_audit_event(
                scope=request.scope,
                actor_id=request.actor_id,
                actor_name=request.actor_name,
                request_text=request.raw_text or "receipt_ingest",
                command_kind="receipt_ingest",
                action=response.action,
                success=True,
                expense_id=expense.id,
                reply_text=response.reply_text,
                metadata=response.metadata,
                created_at=created_at,
            )
            response.metadata["audit_event"] = serialize_audit_event(audit_event)
            return response

    def _validate_scope(self, scope: str) -> None:
        """Validate scope against optional allowlist."""

        if not scope.strip():
            raise ValueError("Scope is required.")
        if self._allowed_scopes is None:
            return
        if scope in self._allowed_scopes:
            return
        allowed = ", ".join(sorted(self._allowed_scopes))
        raise ValueError(
            f"Unsupported scope: {scope}. Allowed scopes: {allowed}."
        )


def window_for_timeframe(now: datetime, timeframe: str) -> tuple[datetime, datetime]:
    """Translate a named timeframe into an inclusive-exclusive window."""

    key = timeframe.lower()
    if key == "today":
        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        return start, start + timedelta(days=1)
    if key == "yesterday":
        today_start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo)
        return today_start - timedelta(days=1), today_start
    if key == "this week":
        start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo) - timedelta(days=now.weekday())
        return start, start + timedelta(days=7)
    if key == "last week":
        this_week_start = datetime.combine(now.date(), time.min, tzinfo=now.tzinfo) - timedelta(days=now.weekday())
        return this_week_start - timedelta(days=7), this_week_start
    if key == "this month":
        start = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        if now.month == 12:
            end = datetime(now.year + 1, 1, 1, tzinfo=now.tzinfo)
        else:
            end = datetime(now.year, now.month + 1, 1, tzinfo=now.tzinfo)
        return start, end
    if key == "last month":
        this_month_start = datetime(now.year, now.month, 1, tzinfo=now.tzinfo)
        if now.month == 1:
            last_month_start = datetime(now.year - 1, 12, 1, tzinfo=now.tzinfo)
        else:
            last_month_start = datetime(now.year, now.month - 1, 1, tzinfo=now.tzinfo)
        return last_month_start, this_month_start
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def format_amount(amount_cents: int) -> str:
    """Format integer cents as a currency string."""

    return f"${amount_cents / 100:.2f}"


def serialize_expense(expense: StoredExpense) -> dict[str, object]:
    """Convert a stored expense into JSON-safe metadata."""

    payload = asdict(expense)
    payload["created_at"] = expense.created_at.isoformat()
    payload["amount"] = format_amount(expense.amount_cents)
    return payload


def serialize_audit_event(audit_event: StoredAuditEvent) -> dict[str, object]:
    """Convert an audit event into compact JSON-safe metadata."""

    return {
        "id": audit_event.id,
        "action": audit_event.action,
        "success": audit_event.success,
        "created_at": audit_event.created_at.isoformat(),
    }


def serialize_expense_item(item: StoredExpenseItem) -> dict[str, object]:
    """Convert a stored expense item into JSON-safe metadata."""

    return {
        "id": item.id,
        "expense_id": item.expense_id,
        "name": item.item_name,
        "normalized_name": item.item_name_normalized,
        "category": item.item_category,
        "quantity": item.quantity,
        "unit": item.unit,
        "unit_price": format_amount(item.unit_price_cents) if item.unit_price_cents is not None else None,
        "line_total": format_amount(item.line_total_cents),
        "created_at": item.created_at.isoformat(),
    }


def serialize_item_rollup(rollup: StoredItemRollup) -> dict[str, object]:
    """Convert an aggregated item total into JSON-safe metadata."""

    return {
        "name": rollup.item_name,
        "normalized_name": rollup.item_name_normalized,
        "total": format_amount(rollup.total_cents),
        "total_cents": rollup.total_cents,
        "line_count": rollup.line_count,
    }


def _normalize_item_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
    normalized = " ".join(normalized.split()).strip()
    if not normalized:
        raise ValueError("Receipt item name cannot be empty.")
    return normalized


def _normalize_structured_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().split())
    return normalized or None


def _normalize_structured_item_name(value: str | None) -> str:
    if value is None:
        raise ValueError("This request is missing an item name.")
    normalized = _normalize_item_text(value)
    if not normalized:
        raise ValueError("This request is missing an item name.")
    return normalized


def _parse_money_to_cents(raw: str) -> int:
    match = AMOUNT_TOKEN_RE.fullmatch(raw.strip())
    if match is None:
        raise ValueError(f"Invalid money amount: {raw}")
    dollars, _, cents = match.group(1).partition(".")
    cents = (cents + "00")[:2]
    return int(dollars) * 100 + int(cents)


def _parse_receipt_item_payload(
    item: dict[str, object],
    *,
    default_category: ExpenseCategory,
) -> dict[str, object]:
    name = str(item.get("name", "")).strip()
    if not name:
        raise ValueError("Receipt item name cannot be empty.")

    line_total_raw = str(item.get("line_total", "")).strip()
    if not line_total_raw:
        raise ValueError(f"Receipt item {name} is missing line_total.")

    quantity_raw = item.get("quantity")
    quantity = float(quantity_raw) if quantity_raw is not None else None

    unit_raw = item.get("unit")
    unit = str(unit_raw).strip() if unit_raw is not None and str(unit_raw).strip() else None

    unit_price_raw = item.get("unit_price")
    unit_price_cents = None
    if unit_price_raw is not None and str(unit_price_raw).strip():
        unit_price_cents = _parse_money_to_cents(str(unit_price_raw))

    # Item category is inferred by Denkeeper by default to keep behavior deterministic.
    # User corrections are handled through explicit follow-up commands
    # (for example: "change item milk to Baby").
    inferred_category = infer_item_category(name, fallback=default_category)

    return {
        "item_name": name,
        "item_name_normalized": _normalize_item_text(name),
        "item_category": inferred_category.value,
        "quantity": quantity,
        "unit": unit,
        "unit_price_cents": unit_price_cents,
        "line_total_cents": _parse_money_to_cents(line_total_raw),
    }


def _coerce_to_timezone(
    value: datetime | None,
    fallback_now: datetime,
    timezone,
) -> datetime:
    if value is None:
        return fallback_now
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def infer_item_category(name: str, *, fallback: ExpenseCategory) -> ExpenseCategory:
    """Infer category for an itemized receipt line."""

    normalized = _normalize_item_text(name)

    if any(keyword in normalized for keyword in BABY_ITEM_KEYWORDS):
        return ExpenseCategory.BABY
    if any(keyword in normalized for keyword in JAMBRA_ITEM_KEYWORDS):
        return ExpenseCategory.JAMBRA
    if any(keyword in normalized for keyword in TRANSPORT_ITEM_KEYWORDS):
        return ExpenseCategory.TRANSPORT
    if any(keyword in normalized for keyword in HOME_MAINTENANCE_ITEM_KEYWORDS):
        return ExpenseCategory.HOME_MAINTENANCE
    return fallback


def _format_receipt_items(items: list[StoredExpenseItem]) -> str:
    if not items:
        return "No item lines saved."
    lines = [
        f"- {item.item_name}: {format_amount(item.line_total_cents)} -> {item.item_category}"
        for item in items
    ]
    return "Itemized categories:\n" + "\n".join(lines)
