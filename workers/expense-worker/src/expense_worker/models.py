"""Pydantic request and response models for the expense worker."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExpenseCommandRequest(BaseModel):
    """Inbound request from the OpenClaw plugin."""

    text: str = Field(min_length=1, max_length=4000)
    scope: str = Field(min_length=1, max_length=128)
    actor_name: str | None = Field(default=None, max_length=128)
    actor_id: str | None = Field(default=None, max_length=128)


ExpenseAction = Literal[
    "add_expense",
    "change_last_category",
    "change_last_receipt_item_category",
    "delete_last",
    "delete_last_receipt",
    "undo_last",
    "list_expenses",
    "total",
    "category_breakdown",
    "category_item_breakdown",
    "item_total",
    "item_presence",
    "list_categories",
]
ExpenseTimeframe = Literal["today", "yesterday", "this week", "last week", "this month", "last month"]


class StructuredExpenseCommandRequest(BaseModel):
    """Structured request produced by the OpenClaw tool schema."""

    action: ExpenseAction
    scope: str = Field(min_length=1, max_length=128)
    actor_name: str | None = Field(default=None, max_length=128)
    actor_id: str | None = Field(default=None, max_length=128)
    amount: str | None = Field(default=None, max_length=32)
    merchant: str | None = Field(default=None, max_length=200)
    category: str | None = Field(default=None, max_length=64)
    timeframe: ExpenseTimeframe | None = None
    item_name: str | None = Field(default=None, max_length=200)
    raw_text: str | None = Field(default=None, max_length=4000)


class ExpenseSummary(BaseModel):
    """Structured expense representation returned to callers."""

    id: int
    amount: str
    merchant: str
    category: str
    created_at: datetime


class ExpenseCommandResponse(BaseModel):
    """Outbound response consumed by the OpenClaw plugin."""

    action: str
    reply_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReceiptLineItem(BaseModel):
    """One line item extracted from a receipt."""

    name: str = Field(min_length=1, max_length=200)
    line_total: str = Field(min_length=1, max_length=32)
    quantity: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    unit_price: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=64)


class ReceiptIngestRequest(BaseModel):
    """Structured receipt payload written into the expense ledger."""

    scope: str = Field(min_length=1, max_length=128)
    merchant: str = Field(min_length=1, max_length=200)
    items: list[ReceiptLineItem] = Field(min_length=1, max_length=300)
    actor_name: str | None = Field(default=None, max_length=128)
    actor_id: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=64)
    receipt_total: str | None = Field(default=None, max_length=32)
    purchased_at: datetime | None = None
    raw_text: str | None = Field(default=None, max_length=4000)
