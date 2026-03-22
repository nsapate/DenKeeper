"""Parse freeform expense requests into explicit commands."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re

from .categories import CATEGORY_ALIASES, ExpenseCategory, normalize_category


class CommandKind(StrEnum):
    """Supported expense command types."""

    ADD = "add"
    CHANGE_LAST_CATEGORY = "change_last_category"
    CHANGE_LAST_ITEM_CATEGORY = "change_last_item_category"
    DELETE_LAST = "delete_last"
    DELETE_LAST_RECEIPT = "delete_last_receipt"
    UNDO_LAST = "undo_last"
    SHOW_TODAY = "show_today"
    LIST_EXPENSES = "list_expenses"
    TOTAL = "total"
    CATEGORY_BREAKDOWN = "category_breakdown"
    CATEGORY_ITEM_BREAKDOWN = "category_item_breakdown"
    ITEM_TOTAL = "item_total"
    ITEM_PRESENCE = "item_presence"
    LIST_CATEGORIES = "list_categories"


@dataclass(frozen=True)
class ParsedCommand:
    """Normalized command emitted by the parser."""

    kind: CommandKind
    amount_cents: int | None = None
    merchant: str | None = None
    category: ExpenseCategory | None = None
    timeframe: str | None = None
    item_name: str | None = None


CATEGORY_OVERRIDE_RE = re.compile(
    r"\b(?:as|under|into|to)\s+([a-z ]+)$",
    re.IGNORECASE,
)
MERCHANT_RE = re.compile(
    r"\b(?:at|for|on|from)\s+(.+?)(?:\s+\b(?:as|under|into|to)\b\s+.+)?$",
    re.IGNORECASE,
)
TOTAL_RE = re.compile(
    r"how much(?:\s+did\s+(?:we|i))?\s+(?:spend|spent)\s+on\s+([a-z0-9 '&-]+)\s+"
    r"(today|yesterday|this week|this month|last week|last month)(?:\s+now)?\??$",
    re.IGNORECASE,
)
ITEM_TOTAL_RE = re.compile(
    r"(?:show|what(?:'s| is)?|total)\s+([a-z0-9 '&-]+)\s+"
    r"(today|yesterday|this week|this month|last week|last month)(?:\s+now)?\??$",
    re.IGNORECASE,
)
ITEM_PRESENCE_RE = re.compile(
    r"did\s+(?:i|we)\s+(?:buy|get|purchase|purchase[d]?)\s+(?:any\s+)?([a-z0-9 '&-]+)\s+"
    r"(today|yesterday|this week|this month|last week|last month)\??$",
    re.IGNORECASE,
)
ITEM_CATEGORY_OVERRIDE_RE = re.compile(
    r"^(?:change|set|mark)\s+(?:item\s+)?([a-z0-9 '&-]+?)\s+"
    r"(?:in\s+last\s+receipt\s+)?(?:as|to|under)\s+([a-z ]+)$",
    re.IGNORECASE,
)
THIS_IS_CATEGORY_RE = re.compile(
    r"^(?:this|that)\s+(?:is|should be)\s+([a-z ]+)$",
    re.IGNORECASE,
)
OVERALL_TOTAL_TRIGGER_RE = re.compile(
    r"\b(?:show|total|summary|how much|what(?:'s| is)?|expense|expenses|spend|report)\b",
    re.IGNORECASE,
)
ADD_INTENT_RE = re.compile(
    r"\b(?:spent|spend|add|log|record|track|save|pay|paid|buy|bought|purchase|purchased)\b",
    re.IGNORECASE,
)
QUESTION_RE = re.compile(
    r"^(?:did|do|does|what|how|show|list|which|when|where|who|is|are|can)\b",
    re.IGNORECASE,
)
LEADING_MENTION_RE = re.compile(r"^(?:@[a-z0-9_.:+-]+[\s,:-]*)+", re.IGNORECASE)
LEADING_ASSISTANT_RE = re.compile(r"^(?:kyoto\b[\s,:-]*)+", re.IGNORECASE)
EXPLICIT_CURRENCY_AMOUNT_RE = re.compile(r"\$\s*(\d{1,6}(?:\.\d{1,2})?)")
DECIMAL_AMOUNT_RE = re.compile(r"(?<![@\w])(\d{1,6}\.\d{1,2})(?!\d)")
VERB_PLAIN_AMOUNT_RE = re.compile(
    r"\b(?:spent|spend|paid|pay|add|log|record|track|save)\b(?:\s+(?:about|around|roughly))?\s+"
    r"(\d{1,5}(?:\.\d{1,2})?)\b",
    re.IGNORECASE,
)
PREFIX_PLAIN_AMOUNT_RE = re.compile(
    r"^\s*(\d{1,5}(?:\.\d{1,2})?)\s+(?:at|for|on|from)\b",
    re.IGNORECASE,
)
DELETE_LAST_RECEIPT_RE = re.compile(
    r"\b(?:delete|remove)\b.*\b(?:last|latest|recent)\b.*\breceipt\b",
    re.IGNORECASE,
)
CATEGORY_BREAKDOWN_RE = re.compile(
    r"\b(?:breakdown|summary)\b.*\bcategory\b|\bcategory\b.*\b(?:breakdown|summary)\b",
    re.IGNORECASE,
)
CATEGORY_ITEM_BREAKDOWN_TRIGGER_RE = re.compile(
    r"\b(?:breakdown|summary)\b.*\bitem(?:s|ized)?\b|\bitem(?:s|ized)?\b.*\b(?:breakdown|summary)\b",
    re.IGNORECASE,
)
CATEGORY_CONTEXT_PATTERNS = (
    re.compile(r"\bunder\s+([a-z ]+?)\s+category\b", re.IGNORECASE),
    re.compile(r"\bfor\s+([a-z ]+?)\s+expenses?\b", re.IGNORECASE),
)

JAMBRA_KEYWORDS = {
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
    "junk food",
    "dessert",
}

GENERIC_TOTAL_SUBJECTS = {
    "expense",
    "expenses",
    "spend",
    "spending",
    "total",
    "summary",
    "report",
}

ADD_PREFIX_RE = re.compile(
    r"^(?:add|log|record|track|save)\b\s*(?:new\s+)?(?:expense\b\s*)?",
    re.IGNORECASE,
)


def parse_command(text: str) -> ParsedCommand:
    """Parse a user message into an explicit command."""

    normalized = _normalize_input(text)
    lowered = normalized.lower()

    if lowered in {"delete last expense", "delete last"}:
        return ParsedCommand(kind=CommandKind.DELETE_LAST)

    if lowered in {
        "delete last receipt",
        "delete latest receipt",
        "remove last receipt",
        "remove latest receipt",
        "delete all expenses from last receipt",
        "remove all expenses from last receipt",
    } or DELETE_LAST_RECEIPT_RE.search(lowered):
        return ParsedCommand(kind=CommandKind.DELETE_LAST_RECEIPT)

    if lowered in {"undo that", "undo"}:
        return ParsedCommand(kind=CommandKind.UNDO_LAST)

    if lowered in {
        "show expenses today",
        "show today's expenses",
        "show todays expenses",
        "list today",
        "show today",
        "today's expenses",
        "todays expenses",
    }:
        return ParsedCommand(kind=CommandKind.SHOW_TODAY)

    if lowered in {
        "what categories are there",
        "what categories are present",
        "what categories are available",
        "what category's are there",
        "what categories do we have",
        "what are the expense categories",
        "list categories",
        "show categories",
        "expense categories",
        "show all expense categories",
        "show me all expense categories",
        "show me expense categories",
        "give me expense categories",
        "show all categories",
        "all expense categories",
    }:
        return ParsedCommand(kind=CommandKind.LIST_CATEGORIES)

    this_is_match = THIS_IS_CATEGORY_RE.search(lowered)
    if this_is_match:
        category = normalize_category(this_is_match.group(1))
        if category is None:
            raise ValueError(f"Unsupported category: {this_is_match.group(1)}")
        return ParsedCommand(kind=CommandKind.CHANGE_LAST_CATEGORY, category=category)

    item_category_match = ITEM_CATEGORY_OVERRIDE_RE.search(lowered)
    if item_category_match:
        item_name = _normalize_item_name(item_category_match.group(1))
        if item_name not in {"last expense", "expense"}:
            category = normalize_category(item_category_match.group(2))
            if category is None:
                raise ValueError(f"Unsupported category: {item_category_match.group(2)}")
            return ParsedCommand(
                kind=CommandKind.CHANGE_LAST_ITEM_CATEGORY,
                item_name=item_name,
                category=category,
            )

    amount_match = _find_amount_match(normalized)

    total_match = TOTAL_RE.search(lowered)
    if total_match:
        subject = _normalize_item_name(total_match.group(1))
        normalized_subject = _normalize_total_subject(subject)
        category = normalize_category(normalized_subject) or normalize_category(subject)
        timeframe = _normalize_timeframe(total_match.group(2))
        if category is not None:
            return ParsedCommand(
                kind=CommandKind.TOTAL,
                category=category,
                timeframe=timeframe,
            )
        if _is_generic_total_subject(subject) and (
            not normalized_subject
            or _is_generic_total_subject(normalized_subject)
            or _looks_like_summary_style_subject(subject)
        ):
            return ParsedCommand(
                kind=CommandKind.TOTAL,
                category=None,
                timeframe=timeframe,
            )
        return ParsedCommand(
            kind=CommandKind.ITEM_TOTAL,
            item_name=normalized_subject or subject,
            timeframe=timeframe,
        )

    category_item_breakdown = _extract_category_item_breakdown(lowered, has_amount=amount_match is not None)
    if category_item_breakdown is not None:
        category, timeframe = category_item_breakdown
        return ParsedCommand(
            kind=CommandKind.CATEGORY_ITEM_BREAKDOWN,
            category=category,
            timeframe=timeframe,
        )

    if CATEGORY_BREAKDOWN_RE.search(lowered):
        return ParsedCommand(
            kind=CommandKind.CATEGORY_BREAKDOWN,
            timeframe=_extract_overall_total_timeframe(lowered, has_amount=amount_match is not None) or "this month",
        )

    item_total_match = ITEM_TOTAL_RE.search(lowered)
    if item_total_match:
        subject = _normalize_item_name(item_total_match.group(1))
        normalized_subject = _normalize_total_subject(subject)
        timeframe = _normalize_timeframe(item_total_match.group(2))
        category = normalize_category(normalized_subject) or normalize_category(subject)
        if category is not None:
            return ParsedCommand(
                kind=CommandKind.TOTAL,
                category=category,
                timeframe=timeframe,
            )
        if _is_generic_total_subject(subject) and (
            not normalized_subject
            or _is_generic_total_subject(normalized_subject)
            or _looks_like_summary_style_subject(subject)
        ):
            return ParsedCommand(
                kind=CommandKind.TOTAL,
                category=None,
                timeframe=timeframe,
            )
        return ParsedCommand(
            kind=CommandKind.ITEM_TOTAL,
            item_name=normalized_subject or subject,
            timeframe=timeframe,
        )

    item_presence_match = ITEM_PRESENCE_RE.search(lowered)
    if item_presence_match:
        return ParsedCommand(
            kind=CommandKind.ITEM_PRESENCE,
            item_name=_normalize_item_name(item_presence_match.group(1)),
            timeframe=_normalize_timeframe(item_presence_match.group(2)),
        )

    overall_timeframe = _extract_overall_total_timeframe(lowered, has_amount=amount_match is not None)
    if overall_timeframe is not None:
        return ParsedCommand(
            kind=CommandKind.TOTAL,
            category=None,
            timeframe=overall_timeframe,
        )

    if (
        lowered.startswith("change last expense to ")
        or lowered.startswith("move last expense to ")
        or lowered.startswith("put this under ")
    ):
        category_text = normalized.split(" to ", 1)[1]
        if lowered.startswith("put this under "):
            category_text = normalized.split("under ", 1)[1]
        category = normalize_category(category_text)
        if category is None:
            raise ValueError(f"Unsupported category: {category_text}")
        return ParsedCommand(kind=CommandKind.CHANGE_LAST_CATEGORY, category=category)

    if _looks_like_question(normalized, lowered):
        raise ValueError(
            "I could not interpret that expense question yet. "
            "Try wording like: how much did I spend on milk last month?"
        )

    if amount_match is None:
        raise ValueError("I could not find an amount in that request.")

    if not _looks_like_add_intent(normalized, lowered):
        raise ValueError(
            "I could not determine an expense-add command. "
            "Try wording like: spent $12 at Trader Joe's."
        )

    category_override = _extract_override_category(normalized)
    merchant = _extract_merchant(normalized, amount_match.span())
    inferred_category = category_override or infer_category(normalized, merchant)
    amount_cents = to_cents(amount_match.group(1))

    return ParsedCommand(
        kind=CommandKind.ADD,
        amount_cents=amount_cents,
        merchant=merchant,
        category=inferred_category,
    )


def _normalize_input(text: str) -> str:
    """Normalize common chat formatting before command parsing."""

    normalized = text.replace("\u2019", "'").replace("\u2018", "'")
    normalized = " ".join(normalized.strip().split())
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = LEADING_MENTION_RE.sub("", normalized).strip()
        normalized = LEADING_ASSISTANT_RE.sub("", normalized).strip()
    return normalized


def _find_amount_match(text: str) -> re.Match[str] | None:
    """Find the most plausible amount token for add-style commands."""

    for pattern in (
        EXPLICIT_CURRENCY_AMOUNT_RE,
        DECIMAL_AMOUNT_RE,
        VERB_PLAIN_AMOUNT_RE,
        PREFIX_PLAIN_AMOUNT_RE,
    ):
        match = pattern.search(text)
        if match is not None:
            return match
    return None


def infer_category(text: str, merchant: str | None) -> ExpenseCategory:
    """Infer a category using lightweight heuristics."""

    haystack = f"{text.lower()} {merchant.lower() if merchant else ''}"

    if any(keyword in haystack for keyword in JAMBRA_KEYWORDS):
        return ExpenseCategory.JAMBRA

    merchant_text = (merchant or "").lower()

    if any(
        token in haystack
        for token in {"gas", "fuel", "shell", "chevron", "uber", "lyft", "parking", "toll", "service", "oil change"}
    ):
        return ExpenseCategory.TRANSPORT
    if any(token in haystack for token in {"diaper", "wipes", "formula", "baby"}):
        return ExpenseCategory.BABY
    if any(token in merchant_text for token in {"trader joe", "safeway", "whole foods", "costco"}):
        return ExpenseCategory.GROCERIES
    if any(token in merchant_text for token in {"starbucks", "doordash", "uber eats", "restaurant", "cafe"}):
        return ExpenseCategory.EATING_OUT
    if any(token in merchant_text for token in {"amazon", "target", "best buy"}):
        return ExpenseCategory.SHOPPING
    if any(token in haystack for token in {"cleaner", "yard", "plumber", "repair", "maintenance", "handyman"}):
        return ExpenseCategory.HOME_MAINTENANCE
    if any(token in haystack for token in {"mortgage"}):
        return ExpenseCategory.MORTGAGE
    if any(
        token in haystack
        for token in {
            "internet",
            "electric",
            "electricity",
            "water bill",
            "gas bill",
            "phone bill",
            "utility",
            "utilities",
            "pg&e",
            "pge",
        }
    ):
        return ExpenseCategory.UTILITIES

    return ExpenseCategory.OTHER


def _extract_override_category(text: str) -> ExpenseCategory | None:
    match = CATEGORY_OVERRIDE_RE.search(text)
    if match is None:
        return None
    return normalize_category(match.group(1))


def _extract_merchant(text: str, amount_span: tuple[int, int]) -> str:
    match = MERCHANT_RE.search(text)
    if match is None:
        fallback = _extract_merchant_from_amount_context(text, amount_span)
        return _clean_merchant_label(fallback) if fallback else "Unknown"
    merchant = _clean_merchant_label(match.group(1))
    return merchant or "Unknown"


def _extract_merchant_from_amount_context(text: str, amount_span: tuple[int, int]) -> str | None:
    """Infer a merchant/label when the request does not use at/for/on phrasing."""

    before_amount = text[: amount_span[0]].strip(" ,.-")
    after_amount = text[amount_span[1] :].strip(" ,.-")

    before_amount = ADD_PREFIX_RE.sub("", before_amount).strip(" ,.-")
    before_amount = re.sub(r"\b(?:spent|spend)\b", "", before_amount, flags=re.IGNORECASE).strip(" ,.-")

    if before_amount and not _looks_like_non_merchant_phrase(before_amount):
        return before_amount
    if after_amount and not _looks_like_non_merchant_phrase(after_amount):
        return after_amount
    return None


def _clean_merchant_label(value: str | None) -> str:
    """Normalize merchant labels extracted from freeform chat text."""

    if value is None:
        return "Unknown"

    cleaned = value.strip(" .,-")
    cleaned = re.sub(r"\b(?:today|yesterday)\b$", "", cleaned, flags=re.IGNORECASE).strip(" .,-")
    cleaned = re.sub(
        r"\b(?:this|last)\s+(?:week|month)\b$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip(" .,-")
    return cleaned or "Unknown"


def _looks_like_non_merchant_phrase(value: str) -> bool:
    """Return True when context text is clearly not a merchant label."""

    lowered = " ".join(value.lower().split())
    if not lowered:
        return True

    if re.match(r"^(?:this|that|it|its)\b", lowered):
        return True
    if lowered in {"expense", "expenses", "transaction", "payment"}:
        return True
    if "expense" in lowered and re.search(r"\b(?:this|that|it|its)\b", lowered):
        return True

    return False


def to_cents(value: str) -> int:
    """Convert a decimal string to cents."""

    dollars, _, cents = value.partition(".")
    cents = (cents + "00")[:2]
    return int(dollars) * 100 + int(cents)


def _extract_overall_total_timeframe(text: str, *, has_amount: bool) -> str | None:
    """Return timeframe for total queries that do not specify a category."""

    if has_amount:
        return None

    if OVERALL_TOTAL_TRIGGER_RE.search(text) is None:
        return None

    if re.search(r"\b(?:this week|weekly)\b", text):
        return "this week"
    if re.search(r"\b(?:last week)\b", text):
        return "last week"
    if re.search(r"\b(?:this month|monthly)\b", text):
        return "this month"
    if re.search(r"\b(?:last month)\b", text):
        return "last month"
    if re.search(r"\b(?:today|todays?|daily)\b", text):
        return "today"
    if re.search(r"\b(?:yesterday)\b", text):
        return "yesterday"
    if re.search(r"\brecent\b", text):
        return "this week"
    if re.search(r"\bweek\b", text):
        return "this week"
    if re.search(r"\bmonth\b", text):
        return "this month"
    return None


def _normalize_timeframe(value: str) -> str:
    key = value.lower().strip()
    if key in {"today", "yesterday", "this week", "this month", "last week", "last month"}:
        return key
    raise ValueError(f"Unsupported timeframe: {value}")


def _normalize_item_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
    normalized = " ".join(normalized.split()).strip()
    if not normalized:
        raise ValueError("Could not determine item name for itemized spend query.")
    return normalized


def _is_generic_total_subject(value: str) -> bool:
    """Return True when the subject means overall totals, not item totals."""

    if value in GENERIC_TOTAL_SUBJECTS:
        return True
    return any(token in value for token in {"expense", "expenses", "spend", "spending", "summary", "report"})


def _normalize_total_subject(value: str) -> str:
    """Normalize summary subjects so category names can be extracted from NL variants."""

    subject = value.strip()
    subject = re.sub(r"^(?:my|our|the)\s+", "", subject).strip()
    subject = re.sub(r"\s+(?:expense|expenses|spend|spending|total|summary|report)$", "", subject).strip()
    subject = re.sub(r"\s+(?:stuff|items|things)$", "", subject).strip()
    return subject


def _looks_like_summary_style_subject(value: str) -> bool:
    """Return True when subject wording implies a summary query, not an item query."""

    return re.search(r"\b(?:top|highest|largest|biggest|most)\b", value) is not None


def _looks_like_add_intent(normalized: str, lowered: str) -> bool:
    """Return True when message likely intends to add an expense."""

    if "$" in normalized:
        return True
    if ADD_INTENT_RE.search(lowered):
        return True
    if PREFIX_PLAIN_AMOUNT_RE.search(lowered):
        return True
    return False


def _looks_like_question(normalized: str, lowered: str) -> bool:
    """Return True when the message is a question that should not fall through to ADD."""

    if "?" in normalized:
        return True
    return QUESTION_RE.search(lowered) is not None


def _extract_category_item_breakdown(
    text: str,
    *,
    has_amount: bool,
) -> tuple[ExpenseCategory, str] | None:
    """Extract itemized category breakdown requests such as 'items under baby category today'."""

    if has_amount:
        return None
    if CATEGORY_ITEM_BREAKDOWN_TRIGGER_RE.search(text) is None:
        return None

    category = _extract_category_mention(text)
    if category is None:
        return None

    timeframe = _extract_overall_total_timeframe(text, has_amount=False) or "this month"
    return category, timeframe


def _extract_category_mention(text: str) -> ExpenseCategory | None:
    """Find the first supported category mention in freeform text."""

    for alias in sorted(CATEGORY_ALIASES.keys(), key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return CATEGORY_ALIASES[alias]

    for pattern in CATEGORY_CONTEXT_PATTERNS:
        for match in pattern.finditer(text):
            category = normalize_category(match.group(1))
            if category is not None:
                return category
    return None
