"""Category definitions and normalization helpers."""

from __future__ import annotations

from difflib import get_close_matches
from enum import StrEnum


class ExpenseCategory(StrEnum):
    """Fixed household expense categories."""

    MORTGAGE = "Mortgage"
    UTILITIES = "Utilities"
    GROCERIES = "Groceries"
    JAMBRA = "Jambra"
    EATING_OUT = "Eating Out"
    SHOPPING = "Shopping"
    BABY = "Baby"
    TRANSPORT = "Transport"
    HOME_MAINTENANCE = "Home Maintenance"
    OTHER = "Other"


CATEGORY_ALIASES: dict[str, ExpenseCategory] = {
    "mortgage": ExpenseCategory.MORTGAGE,
    "utilities": ExpenseCategory.UTILITIES,
    "utility": ExpenseCategory.UTILITIES,
    "groceries": ExpenseCategory.GROCERIES,
    "grocery": ExpenseCategory.GROCERIES,
    "jambra": ExpenseCategory.JAMBRA,
    "eating out": ExpenseCategory.EATING_OUT,
    "take out": ExpenseCategory.EATING_OUT,
    "takeout": ExpenseCategory.EATING_OUT,
    "take outs": ExpenseCategory.EATING_OUT,
    "restaurant": ExpenseCategory.EATING_OUT,
    "shopping": ExpenseCategory.SHOPPING,
    "baby": ExpenseCategory.BABY,
    "baby stuff": ExpenseCategory.BABY,
    "baby items": ExpenseCategory.BABY,
    "baby things": ExpenseCategory.BABY,
    "transport": ExpenseCategory.TRANSPORT,
    "gas": ExpenseCategory.TRANSPORT,
    "car": ExpenseCategory.TRANSPORT,
    "home maintenance": ExpenseCategory.HOME_MAINTENANCE,
    "maintenance": ExpenseCategory.HOME_MAINTENANCE,
    "house maintenance": ExpenseCategory.HOME_MAINTENANCE,
    "other": ExpenseCategory.OTHER,
    "uncategorized": ExpenseCategory.OTHER,
}

FUZZY_CATEGORY_MATCH_CUTOFF = 0.84
FUZZY_CATEGORY_MIN_LENGTH = 3
FUZZY_CATEGORY_KEYS = tuple(sorted(CATEGORY_ALIASES.keys()))


def normalize_category(value: str) -> ExpenseCategory | None:
    """Map freeform category text to a supported category."""

    key = " ".join(value.lower().strip().replace("_", " ").split())
    category = CATEGORY_ALIASES.get(key)
    if category is not None:
        return category

    if len(key) < FUZZY_CATEGORY_MIN_LENGTH:
        return None

    matches = get_close_matches(
        key,
        FUZZY_CATEGORY_KEYS,
        n=1,
        cutoff=FUZZY_CATEGORY_MATCH_CUTOFF,
    )
    if not matches:
        return None
    return CATEGORY_ALIASES[matches[0]]


def list_category_names() -> list[str]:
    """Return the canonical category labels."""

    return [category.value for category in ExpenseCategory]
