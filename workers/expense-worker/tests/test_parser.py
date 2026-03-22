from expense_worker.categories import ExpenseCategory
from expense_worker.parser import CommandKind, parse_command

import pytest


def test_parse_add_with_explicit_category() -> None:
    command = parse_command("Log $18.50 for Starbucks as Eating Out")

    assert command.kind == CommandKind.ADD
    assert command.amount_cents == 1850
    assert command.merchant == "Starbucks"
    assert command.category == ExpenseCategory.EATING_OUT


def test_parse_change_last_category() -> None:
    command = parse_command("change last expense to Jambra")

    assert command.kind == CommandKind.CHANGE_LAST_CATEGORY
    assert command.category == ExpenseCategory.JAMBRA


def test_parse_change_last_category_with_kyoto_prefix() -> None:
    command = parse_command("Kyoto change last expense to Jambra")

    assert command.kind == CommandKind.CHANGE_LAST_CATEGORY
    assert command.category == ExpenseCategory.JAMBRA


def test_parse_total_query() -> None:
    command = parse_command("How much did we spend on Baby this week?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "this week"


def test_parse_item_total_query_last_month() -> None:
    command = parse_command("How much did I spend on milk last month?")

    assert command.kind == CommandKind.ITEM_TOTAL
    assert command.item_name == "milk"
    assert command.timeframe == "last month"


def test_parse_total_query_with_yesterday_timeframe() -> None:
    command = parse_command("Kyoto how much did I spend on Jambra yesterday?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.JAMBRA
    assert command.timeframe == "yesterday"


def test_parse_total_query_with_baby_stuff_maps_baby_category() -> None:
    command = parse_command("@57192489156720 how much did I spend on baby stuff today?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "today"


def test_parse_total_query_with_bay_stuff_typo_maps_baby_category() -> None:
    command = parse_command("@57192489156720 how much did I spend on bay stuff today?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "today"


def test_parse_total_query_with_baby_items_maps_baby_category() -> None:
    command = parse_command("Kyoto how much did we spend on baby items this week?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "this week"


def test_parse_undo() -> None:
    command = parse_command("undo")

    assert command.kind == CommandKind.UNDO_LAST


def test_parse_show_today_with_kyoto_prefix_and_curly_apostrophe() -> None:
    command = parse_command("Kyoto show today’s expenses")

    assert command.kind == CommandKind.SHOW_TODAY


def test_parse_list_today_with_kyoto_prefix() -> None:
    command = parse_command("Kyoto list today")

    assert command.kind == CommandKind.SHOW_TODAY


def test_parse_list_categories() -> None:
    command = parse_command("Kyoto what categories are present")

    assert command.kind == CommandKind.LIST_CATEGORIES


def test_parse_list_all_categories_phrase() -> None:
    command = parse_command("Kyoto show all expense categories")

    assert command.kind == CommandKind.LIST_CATEGORIES


def test_parse_list_categories_with_show_me_phrase() -> None:
    command = parse_command("@57192489156720 show me all expense categories")

    assert command.kind == CommandKind.LIST_CATEGORIES


def test_parse_total_query_without_category_weekly() -> None:
    command = parse_command("Kyoto show weekly expense")

    assert command.kind == CommandKind.TOTAL
    assert command.category is None
    assert command.timeframe == "this week"


def test_parse_total_query_without_category_monthly() -> None:
    command = parse_command("Kyoto monthly total")

    assert command.kind == CommandKind.TOTAL
    assert command.category is None
    assert command.timeframe == "this month"


def test_parse_item_total_short_phrase() -> None:
    command = parse_command("Kyoto show organic milk last month")

    assert command.kind == CommandKind.ITEM_TOTAL
    assert command.item_name == "organic milk"
    assert command.timeframe == "last month"


def test_parse_total_short_phrase_with_generic_subject() -> None:
    command = parse_command("Kyoto total expense this week")

    assert command.kind == CommandKind.TOTAL
    assert command.category is None
    assert command.timeframe == "this week"


def test_parse_total_short_phrase_with_category_subject_and_now_suffix() -> None:
    command = parse_command("Kyoto total groceries this week now")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.GROCERIES
    assert command.timeframe == "this week"


def test_parse_total_short_phrase_with_category_and_expense_suffix() -> None:
    command = parse_command("Kyoto show Jambra expense this week")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.JAMBRA
    assert command.timeframe == "this week"


def test_parse_total_short_phrase_with_my_gas_expenses_maps_transport() -> None:
    command = parse_command("Kyoto show my gas expenses this week")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.timeframe == "this week"


def test_parse_how_much_on_gas_expenses_maps_transport() -> None:
    command = parse_command("Kyoto how much did I spend on gas expenses this week?")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.timeframe == "this week"


def test_parse_how_much_spent_on_gas_this_week_maps_transport() -> None:
    command = parse_command("@kyoto how much spent on gas this week")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.timeframe == "this week"


def test_parse_numeric_whatsapp_mention_then_gas_query_maps_transport() -> None:
    command = parse_command("@57192489156720 how much spent on gas this week")

    assert command.kind == CommandKind.TOTAL
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.timeframe == "this week"


def test_parse_item_presence_query_with_numeric_whatsapp_mention() -> None:
    command = parse_command("@57192489156720 did I buy any milk last week?")

    assert command.kind == CommandKind.ITEM_PRESENCE
    assert command.item_name == "milk"
    assert command.timeframe == "last week"


def test_parse_item_presence_query_with_kyoto_prefix() -> None:
    command = parse_command("Kyoto did we buy diapers this month?")

    assert command.kind == CommandKind.ITEM_PRESENCE
    assert command.item_name == "diapers"
    assert command.timeframe == "this month"


def test_parse_change_last_receipt_item_category() -> None:
    command = parse_command("Kyoto change item chips to Jambra")

    assert command.kind == CommandKind.CHANGE_LAST_ITEM_CATEGORY
    assert command.item_name == "chips"
    assert command.category == ExpenseCategory.JAMBRA


def test_parse_add_with_amount_is_not_misclassified_as_total() -> None:
    command = parse_command("Kyoto spent $12 today at Trader Joe's")

    assert command.kind == CommandKind.ADD
    assert command.amount_cents == 1200


def test_parse_add_with_gas_phrase_infers_transport_and_merchant_from_from_clause() -> None:
    command = parse_command("Kyoto add $41.50 gas expenses from Costco today")

    assert command.kind == CommandKind.ADD
    assert command.amount_cents == 4150
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.merchant == "Costco"


def test_parse_add_without_merchant_phrase_uses_unknown_merchant() -> None:
    command = parse_command("Kyoto add this to gas expenses but it’s $41.50")

    assert command.kind == CommandKind.ADD
    assert command.amount_cents == 4150
    assert command.category == ExpenseCategory.TRANSPORT
    assert command.merchant == "Unknown"


def test_parse_delete_last_receipt() -> None:
    command = parse_command("Kyoto delete last receipt")

    assert command.kind == CommandKind.DELETE_LAST_RECEIPT


def test_parse_delete_all_expenses_from_last_receipt() -> None:
    command = parse_command("Kyoto delete all expenses from last receipt")

    assert command.kind == CommandKind.DELETE_LAST_RECEIPT


def test_parse_query_with_number_is_not_misclassified_as_add() -> None:
    with pytest.raises(ValueError, match="expense question"):
        parse_command("Kyoto show 2026 expenses")


def test_parse_top_expenses_phrase_routes_to_overall_total_not_item_total() -> None:
    command = parse_command("Kyoto show top 3 expenses this month")

    assert command.kind == CommandKind.TOTAL
    assert command.category is None
    assert command.timeframe == "this month"


def test_parse_category_breakdown_phrase_defaults_to_current_month() -> None:
    command = parse_command("Kyoto give me a breakdown of my expenses by category")

    assert command.kind == CommandKind.CATEGORY_BREAKDOWN
    assert command.timeframe == "this month"


def test_parse_category_breakdown_phrase_with_week_timeframe() -> None:
    command = parse_command("Kyoto show a category breakdown for this week")

    assert command.kind == CommandKind.CATEGORY_BREAKDOWN
    assert command.timeframe == "this week"


def test_parse_category_item_breakdown_for_baby_today() -> None:
    command = parse_command("Kyoto give me a breakdown by item for baby expenses today")

    assert command.kind == CommandKind.CATEGORY_ITEM_BREAKDOWN
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "today"


def test_parse_category_item_breakdown_with_repeated_down_and_numeric_mention() -> None:
    command = parse_command("@57192489156720 give me a breakdown down by item for baby expenses today")

    assert command.kind == CommandKind.CATEGORY_ITEM_BREAKDOWN
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "today"


def test_parse_category_item_breakdown_under_baby_recent_defaults_this_week() -> None:
    command = parse_command("Kyoto give me a breakdown of items under baby category from recent expenses")

    assert command.kind == CommandKind.CATEGORY_ITEM_BREAKDOWN
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "this week"


def test_parse_category_item_breakdown_under_babby_category_uses_fuzzy_match() -> None:
    command = parse_command("Kyoto give me a summary of items under babby category this month")

    assert command.kind == CommandKind.CATEGORY_ITEM_BREAKDOWN
    assert command.category == ExpenseCategory.BABY
    assert command.timeframe == "this month"


def test_parse_plain_integer_add_after_spent_works() -> None:
    command = parse_command("Kyoto spent 20 at Starbucks")

    assert command.kind == CommandKind.ADD
    assert command.amount_cents == 2000
    assert command.merchant == "Starbucks"


def test_parse_question_with_phone_like_digits_is_not_misclassified_as_add() -> None:
    with pytest.raises(ValueError, match="expense question"):
        parse_command("@57192489156720 did I buy any yogurt in 2026?")
