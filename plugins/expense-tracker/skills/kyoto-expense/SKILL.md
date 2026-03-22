# Kyoto Expense Tracking

Use the `denkeeper_expense` tool whenever the user is talking about household expenses, categories, corrections, or expense summaries.
Use the `denkeeper_receipt` tool when the user shares an itemized receipt and wants line-item extraction persisted.

Do not answer expense questions from chat memory or by manually summarizing prior messages. The tool is the source of truth.

## Purpose

This skill lets Kyoto manage household expenses for `The Den`.

## Categories

- `Mortgage`
- `Utilities`
- `Groceries`
- `Jambra`
- `Eating Out`
- `Shopping`
- `Baby`
- `Transport`
- `Home Maintenance`
- `Other`

## When To Use The Tool

Use `denkeeper_expense` when the user wants to:

- log a new expense
- override the category
- move an expense from one category to another
- delete the last expense
- delete the last receipt
- undo the last expense
- see today's expenses
- get a category total for supported windows (today, yesterday, this week, last week, this month, last month)
- list the supported expense categories
- get an itemized breakdown within a category (for example `break down Baby purchases by item this week`)
- ask item-level spend questions such as `how much did we spend on milk last month?`
- ask yes/no item-purchase questions such as `did I buy any milk last week?`
- correct inferred category for an item in the latest receipt (for example `change item milk to Baby`)

Use `denkeeper_receipt` when the user wants to:

- log a grocery/store receipt with itemized lines
- store item quantities and prices from receipt photos
- persist receipt totals and line items for later item-level queries

## How To Call The Tool

- Choose a structured `action` for `denkeeper_expense`.
- Fill only the fields that match that action.
- Omit `scope` unless the user explicitly asks for a different tracking scope.
- Use the configured default scope for normal household tracking.
- If the user clearly identifies themselves in a useful way and you have it available, pass `actorName` or `actorId`.
- Use canonical category names only:
  - `Mortgage`
  - `Utilities`
  - `Groceries`
  - `Jambra`
  - `Eating Out`
  - `Shopping`
  - `Baby`
  - `Transport`
  - `Home Maintenance`
  - `Other`
- Use supported timeframes only:
  - `today`
  - `yesterday`
  - `this week`
  - `last week`
  - `this month`
  - `last month`
- `rawText` is optional and only for audit readability. Do not rely on it for execution.
- Do not pass vague prose when you can express the request through structured fields.

For `denkeeper_receipt`:

- Extract merchant and itemized lines as accurately as possible.
- Pass each item with `name` and `lineTotal` at minimum.
- Include `quantity`, `unit`, `unitPrice`, and `receiptTotal` when available.
- Do not pass per-item category during initial receipt ingest. Denkeeper infers item category by default.
- Use `rawText` to preserve the user's original wording.

## Examples

Use the tool for requests like:

- `Spent $42 at Trader Joe's`
  - `action=add_expense`, `amount=42`, `merchant=Trader Joe's`, `category=Groceries`
- `Log $18 at Starbucks as Eating Out`
  - `action=add_expense`, `amount=18`, `merchant=Starbucks`, `category=Eating Out`
- `This should be Jambra`
  - `action=change_last_category`, `category=Jambra`
- `Change item milk to Baby`
  - `action=change_last_receipt_item_category`, `itemName=milk`, `category=Baby`
- `Delete last expense`
  - `action=delete_last`
- `Delete last receipt`
  - `action=delete_last_receipt`
- `Show expenses today`
  - `action=list_expenses`, `timeframe=today`
- `How much did we spend on Baby this week?`
  - `action=total`, `category=Baby`, `timeframe=this week`
- `Give me a breakdown of my expenses by category`
  - `action=category_breakdown`, `timeframe=this month`
- `Give me a breakdown by item for Baby expenses today`
  - `action=category_item_breakdown`, `category=Baby`, `timeframe=today`
- `Show items under Baby category from recent expenses`
  - `action=category_item_breakdown`, `category=Baby`, `timeframe=this week`
- `What categories are available?`
  - `action=list_categories`
- `How much did we spend on milk last month?`
  - `action=item_total`, `itemName=milk`, `timeframe=last month`
- `Did I buy any milk last week?`
  - `action=item_presence`, `itemName=milk`, `timeframe=last week`
- `Here is a receipt, add all items`
  - use `denkeeper_receipt`

## Behavior Notes

- If the user explicitly names a category, trust that over inference.
- `Jambra` is for guilt snacks, junk food, treats, chips, chocolates, cake, soda, and similar non-essential food items.
- `Transport` includes gas, parking, tolls, rideshare, car servicing, and similar costs.
- `Home Maintenance` includes cleaners, yard work, repairs, and upkeep.
- Strip direct invocation prefixes like `Kyoto`, `@Kyoto`, or `Kyoto,` mentally before deciding what the user wants.
- Denkeeper owns persistence, audit logging, and deterministic business rules. Your job is to choose the right structured action and fields.
- `list_expenses` is for expense-entry listings only. It does not mean itemized receipt rollups.
- For itemized category questions, do not use `list_expenses`; use `category_item_breakdown`.
- Phrases like `by item`, `itemized`, and `items under Baby category` should map to `category_item_breakdown`.
- Always call the tool for:
  - adding expenses
  - corrections or recategorization
  - delete / undo (including delete-last-receipt)
  - daily lists
  - category totals
  - item-level spend totals
  - supported category list questions
- For itemized receipts, call `denkeeper_receipt` instead of flattening to one generic expense note.
- After receipt ingestion, present the itemized lines and inferred category mapping so the user can request corrections.
- For successful `denkeeper_receipt` calls, include the full itemized breakdown in the final user reply.
- Do not collapse receipt replies to a one-line summary like "Logged receipt ...".
- Preserve each line item with amount and inferred category in the response.
- Preferred behavior for receipt success: return the tool response text verbatim.
- Never answer those directly from memory, prior chat context, or your own arithmetic.
- Negative example:
  - User: `Kyoto show expenses today`
  - Wrong: summarize from prior chat messages
  - Right: call `denkeeper_expense` with `action=list_expenses`, `timeframe=today`
- Negative example:
  - User: `Kyoto change last expense to Jambra`
  - Wrong: explain tool limits or ask for the amount unless Denkeeper itself asks
  - Right: call `denkeeper_expense` with `action=change_last_category`, `category=Jambra`
- Negative example:
  - User: `Kyoto what categories are present`
  - Wrong: answer from categories seen in chat history
  - Right: call `denkeeper_expense` with `action=list_categories`
- After the tool returns, prefer the tool result over your own paraphrase.
- Never mention internal mechanics such as parsers, tools being strict, or tool limitations.
- If the tool returns an error or clarification, relay that plainly in one short sentence instead of editorializing.
