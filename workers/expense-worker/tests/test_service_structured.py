from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from expense_worker.database import connect, ensure_database
from expense_worker.models import (
    ExpenseCommandRequest,
    ReceiptIngestRequest,
    ReceiptLineItem,
    StructuredExpenseCommandRequest,
)
from expense_worker.repository import ExpenseRepository
from expense_worker.service import ExpenseService, window_for_timeframe


def build_service(
    tmp_path: Path,
    *,
    allowed_scopes: frozenset[str] | None = None,
) -> ExpenseService:
    db_path = tmp_path / "expenses.sqlite3"
    ensure_database(str(db_path))
    repository = ExpenseRepository(connect(str(db_path)))
    return ExpenseService(repository, ZoneInfo("UTC"), allowed_scopes)


def test_raw_add_logs_expense(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $2.20 on water bottle",
            scope="household",
        )
    )

    assert response.action == "expense_added"
    assert "water bottle" in response.reply_text


def test_raw_add_gas_phrase_maps_to_transport_and_costco(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto add $41.50 gas expenses from Costco today",
            scope="household",
        )
    )

    assert response.action == "expense_added"
    assert response.reply_text == "Saved $41.50 at Costco under Transport."


def test_raw_add_without_merchant_phrase_uses_unknown_and_clean_reply(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto add this to gas expenses but it’s $41.50",
            scope="household",
        )
    )

    assert response.action == "expense_added"
    assert response.reply_text == "Saved $41.50 under Transport."


def test_scope_allowlist_blocks_unknown_scope_for_command(tmp_path: Path) -> None:
    service = build_service(tmp_path, allowed_scopes=frozenset({"the-den"}))

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $2.20 on water bottle",
            scope="typo-den",
        )
    )

    assert response.action == "validation_error"
    assert response.reply_text == "Unsupported scope: typo-den. Allowed scopes: the-den."


def test_scope_allowlist_blocks_unknown_scope_for_receipt_ingest(tmp_path: Path) -> None:
    service = build_service(tmp_path, allowed_scopes=frozenset({"the-den"}))

    response = service.ingest_receipt(
        ReceiptIngestRequest(
            scope="typo-den",
            merchant="TestMart",
            category="Groceries",
            items=[ReceiptLineItem(name="Milk", line_total="4.00")],
            receipt_total="4.00",
            raw_text="receipt import",
        )
    )

    assert response.action == "validation_error"
    assert response.reply_text == "Unsupported scope: typo-den. Allowed scopes: the-den."


def test_raw_add_without_amount_returns_validation_error(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto add expense for snacks",
            scope="household",
        )
    )

    assert response.action == "validation_error"
    assert response.reply_text == "I could not find an amount in that request."


def test_raw_total_uses_category_and_timeframe_from_text(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $14 at Starbucks",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto how much did we spend on eating out this week?",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert "Eating Out spend for this week is $14.00." == response.reply_text


def test_raw_total_baby_stuff_maps_to_baby_category(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $16.99 on baby bottle",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 how much did I spend on baby stuff today?",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Baby spend for today is $16.99."


def test_raw_total_bay_stuff_typo_maps_to_baby_category(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $16.99 on baby bottle",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 how much did I spend on bay stuff today?",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Baby spend for today is $16.99."


def test_raw_total_short_phrase_with_category_expense_suffix(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $5.50 on cookies as Jambra",
            scope="household",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $9.00 at Trader Joe's",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto show Jambra expense this week",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Jambra spend for this week is $5.50."


def test_raw_total_how_much_spent_on_gas_this_week_maps_transport(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto add $41.50 gas expenses from Costco today",
            scope="household",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $9.00 at Trader Joe's",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@kyoto how much spent on gas this week",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Transport spend for this week is $41.50."


def test_raw_total_numeric_whatsapp_mention_still_maps_transport(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto add $41.50 gas expenses from Costco today",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 how much spent on gas this week",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Transport spend for this week is $41.50."


def test_structured_total_for_baby_category(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $16.99 on baby bottle",
            scope="household",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="total",
            scope="household",
            category="Baby",
            timeframe="today",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Baby spend for today is $16.99."


def test_structured_list_categories(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="list_categories",
            scope="household",
        )
    )

    assert response.action == "expense_categories"
    assert "Supported categories:" in response.reply_text
    assert "- Baby" in response.reply_text


def test_structured_category_breakdown_defaults_month_and_lists_all_categories(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto add $41.50 gas expenses from Costco today",
            scope="household",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $9.00 at Trader Joe's",
            scope="household",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="category_breakdown",
            scope="household",
        )
    )

    assert response.action == "category_breakdown"
    assert "Category breakdown for this month:" in response.reply_text
    assert "- Transport: $41.50" in response.reply_text
    assert "- Groceries: $9.00" in response.reply_text
    assert "Total: $50.50" in response.reply_text


def test_structured_category_item_breakdown_for_baby(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Target",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Formula", line_total="89.98"),
                ReceiptLineItem(name="Baby Wipes", line_total="6.45"),
                ReceiptLineItem(name="Milk", line_total="4.99"),
            ],
            receipt_total="101.42",
            raw_text="receipt import",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="category_item_breakdown",
            scope="household",
            category="Baby",
            timeframe="today",
        )
    )

    assert response.action == "category_item_breakdown"
    assert "Item breakdown for Baby during today:" in response.reply_text
    assert "- Baby Formula: $89.98" in response.reply_text
    assert "- Baby Wipes: $6.45" in response.reply_text
    assert "Total: $96.43" in response.reply_text


def test_raw_category_item_breakdown_with_numeric_mention_and_extra_wording(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Target",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Formula", line_total="89.98"),
                ReceiptLineItem(name="Baby Wipes", line_total="6.45"),
                ReceiptLineItem(name="Milk", line_total="4.99"),
            ],
            receipt_total="101.42",
            raw_text="receipt import",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 give me a breakdown down by item for baby expenses today",
            scope="household",
        )
    )

    assert response.action == "category_item_breakdown"
    assert "Item breakdown for Baby during today:" in response.reply_text
    assert "- Baby Formula: $89.98" in response.reply_text
    assert "- Baby Wipes: $6.45" in response.reply_text
    assert "Total: $96.43" in response.reply_text


def test_raw_category_item_breakdown_under_fuzzy_category_phrase(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Target",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Formula", line_total="89.98"),
                ReceiptLineItem(name="Baby Wipes", line_total="6.45"),
                ReceiptLineItem(name="Milk", line_total="4.99"),
            ],
            receipt_total="101.42",
            raw_text="receipt import",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto give me a summary of items under babby category this month",
            scope="household",
        )
    )

    assert response.action == "category_item_breakdown"
    assert "Item breakdown for Baby during this month:" in response.reply_text
    assert "- Baby Formula: $89.98" in response.reply_text
    assert "- Baby Wipes: $6.45" in response.reply_text
    assert "Total: $96.43" in response.reply_text


def test_category_total_uses_itemized_receipt_categories(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Target",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Formula", line_total="89.98"),
                ReceiptLineItem(name="Milk", line_total="4.99"),
            ],
            receipt_total="94.97",
            raw_text="receipt import",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="total",
            scope="household",
            category="Baby",
            timeframe="today",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Baby spend for today is $89.98."


def test_category_breakdown_uses_itemized_receipt_categories(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Target",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Formula", line_total="89.98"),
                ReceiptLineItem(name="Milk", line_total="4.99"),
            ],
            receipt_total="94.97",
            raw_text="receipt import",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="category_breakdown",
            scope="household",
            timeframe="today",
        )
    )

    assert response.action == "category_breakdown"
    assert "- Baby: $89.98" in response.reply_text
    assert "- Groceries: $4.99" in response.reply_text
    assert "Total: $94.97" in response.reply_text


def test_structured_list_expenses_for_today(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $9.00 at Trader Joe's",
            scope="household",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="list_expenses",
            scope="household",
            timeframe="today",
        )
    )

    assert response.action == "expense_list"
    assert "Expenses for today:" in response.reply_text
    assert "- $9.00 at Trader Joe's (Groceries)" in response.reply_text


def test_structured_item_presence_yes(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Trader Joe's",
            category="Groceries",
            items=[ReceiptLineItem(name="Organic Milk 2%", line_total="6.50")],
            receipt_total="6.50",
            raw_text="receipt import",
        )
    )

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="item_presence",
            scope="household",
            item_name="milk",
            timeframe="this month",
        )
    )

    assert response.action == "item_presence"
    assert response.reply_text == "Yes — milk spend for this month is $6.50."


def test_structured_add_requires_amount(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle_structured(
        StructuredExpenseCommandRequest(
            action="add_expense",
            scope="household",
            merchant="Trader Joe's",
        )
    )

    assert response.action == "validation_error"
    assert response.reply_text == "This expense add request is missing an amount."


def test_raw_item_presence_query_yes_from_receipt(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Trader Joe's",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Organic Milk 2%", line_total="6.50"),
                ReceiptLineItem(name="Bread", line_total="3.00"),
            ],
            receipt_total="9.50",
            raw_text="receipt import",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 did I buy any milk this month?",
            scope="household",
        )
    )

    assert response.action == "item_presence"
    assert response.reply_text == "Yes — milk spend for this month is $6.50."


def test_raw_item_presence_query_no_does_not_add_bogus_expense(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="@57192489156720 did I buy any milk last week?",
            scope="household",
        )
    )

    assert response.action == "item_presence"
    assert response.reply_text == "No — no milk found for last week."

    total_response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto monthly total",
            scope="household",
        )
    )
    assert total_response.reply_text == "Total spend for this month is $0.00."


def test_window_for_timeframe_yesterday_is_previous_day_range() -> None:
    now = datetime(2026, 3, 23, 12, 0, tzinfo=timezone.utc)

    start, end = window_for_timeframe(now, "yesterday")

    assert start == datetime(2026, 3, 22, 0, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 3, 23, 0, 0, tzinfo=timezone.utc)


def test_raw_total_without_category_uses_overall_timeframe(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $10 at Trader Joe's",
            scope="household",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $20 at Target",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto monthly total",
            scope="household",
        )
    )

    assert response.action == "expense_total"
    assert response.reply_text == "Total spend for this month is $30.00."
    assert response.metadata["category"] is None


def test_raw_change_last_category(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $7 on coke",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto change last expense to Jambra",
            scope="household",
        )
    )

    assert response.action == "expense_updated"
    assert "Jambra" in response.reply_text


def test_raw_list_categories_returns_supported_categories(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto what categories are available",
            scope="household",
        )
    )

    assert response.action == "expense_categories"
    assert "Supported categories:" in response.reply_text
    assert "Jambra" in response.reply_text


def test_receipt_ingest_and_item_total_query_last_month(tmp_path: Path) -> None:
    service = build_service(tmp_path)
    now = datetime.now(timezone.utc)
    if now.month == 1:
        purchased_at = datetime(now.year - 1, 12, 15, tzinfo=timezone.utc)
    else:
        purchased_at = datetime(now.year, now.month - 1, 15, tzinfo=timezone.utc)

    ingest_response = service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Trader Joe's",
            category="Groceries",
            purchased_at=purchased_at,
            items=[
                ReceiptLineItem(name="Organic Milk 2%", line_total="6.50"),
                ReceiptLineItem(name="Bread", line_total="3.00"),
            ],
            receipt_total="9.50",
            raw_text="receipt import",
        )
    )

    assert ingest_response.action == "receipt_added"
    assert "2 items" in ingest_response.reply_text

    query_response = service.handle(
        ExpenseCommandRequest(
            text="How much did I spend on milk last month?",
            scope="household",
        )
    )

    assert query_response.action == "item_expense_total"
    assert query_response.reply_text == "Spend on milk for last month is $6.50."


def test_receipt_item_auto_categorization(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Costco",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Baby Milk Powder", line_total="29.99"),
                ReceiptLineItem(name="Potato Chips", line_total="4.50"),
                ReceiptLineItem(name="Rice", line_total="12.00"),
            ],
            receipt_total="46.49",
            raw_text="receipt import",
        )
    )

    assert response.action == "receipt_added"
    assert "Baby Milk Powder: $29.99 -> Baby" in response.reply_text
    assert "Potato Chips: $4.50 -> Jambra" in response.reply_text
    assert "Rice: $12.00 -> Groceries" in response.reply_text


def test_change_last_receipt_item_category(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Trader Joe's",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Banana Chips", line_total="4.50"),
                ReceiptLineItem(name="Milk", line_total="5.00"),
            ],
            receipt_total="9.50",
            raw_text="receipt import",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto change item milk to Baby",
            scope="household",
        )
    )

    assert response.action == "receipt_item_category_updated"
    assert "Milk: $5.00 -> Baby" in response.reply_text


def test_change_last_receipt_item_category_targets_latest_receipt_not_latest_expense(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Trader Joe's",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Milk", line_total="5.00"),
                ReceiptLineItem(name="Bread", line_total="3.00"),
            ],
            receipt_total="8.00",
            raw_text="receipt import",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $2.00 on parking",
            scope="household",
        )
    )

    response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto change item milk to Baby",
            scope="household",
        )
    )

    assert response.action == "receipt_item_category_updated"
    assert "Milk: $5.00 -> Baby" in response.reply_text


def test_receipt_ingest_ignores_payload_item_category_and_uses_inference(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    response = service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Store",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Chocolate Chips", line_total="3.00", category="Groceries"),
            ],
            receipt_total="3.00",
            raw_text="receipt import",
        )
    )

    assert response.action == "receipt_added"
    assert "Chocolate Chips: $3.00 -> Jambra" in response.reply_text


def test_delete_last_receipt_targets_latest_receipt_not_latest_expense(tmp_path: Path) -> None:
    service = build_service(tmp_path)

    service.ingest_receipt(
        ReceiptIngestRequest(
            scope="household",
            merchant="Sprouts",
            category="Groceries",
            items=[
                ReceiptLineItem(name="Milk", line_total="6.00"),
                ReceiptLineItem(name="Cookies", line_total="4.00"),
            ],
            receipt_total="10.00",
            raw_text="receipt import",
        )
    )
    service.handle(
        ExpenseCommandRequest(
            text="Kyoto spent $2.00 on parking",
            scope="household",
        )
    )

    delete_response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto delete last receipt",
            scope="household",
        )
    )

    assert delete_response.action == "receipt_deleted"
    assert "Sprouts ($10.00, 2 item(s))" in delete_response.reply_text
    assert "This week's total is now $2.00." in delete_response.reply_text

    milk_total_response = service.handle(
        ExpenseCommandRequest(
            text="How much did I spend on milk this month?",
            scope="household",
        )
    )
    assert milk_total_response.action == "item_expense_total"
    assert milk_total_response.reply_text == "Spend on milk for this month is $0.00."

    overall_total_response = service.handle(
        ExpenseCommandRequest(
            text="Kyoto monthly total",
            scope="household",
        )
    )
    assert overall_total_response.action == "expense_total"
    assert overall_total_response.reply_text == "Total spend for this month is $2.00."
