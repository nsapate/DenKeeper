# Denkeeper Improvements

## Completed Recently

- Reworked the main expense integration boundary:
  - `denkeeper_expense` now uses a structured action schema instead of a raw-text-only contract
  - worker added `POST /v1/expenses/handle-structured`
  - OpenClaw now does NL-to-schema canonicalization; worker stays deterministic after the tool call
- Added first-class expense actions for:
  - category breakdown by timeframe
  - list supported categories
  - list expenses by timeframe
  - itemized breakdown within a category by timeframe
- Receipt ingest now ignores payload item-category hints and applies Denkeeper inference by default.
- Added `delete last receipt` intent/handler path.
- Added receipt/item regression coverage and parser coverage for recent NL variants.
- Canonicalized short total phrases so generic subjects like `expense` route to overall totals, not item totals.
- Added delete-receipt confirmation that returns the refreshed `this week` total immediately.
- Added optional scope allowlist guardrail via `DENKEEPER_EXPENSE_ALLOWED_SCOPES` to prevent typo-created ledgers.
- Added full Docker Compose topology for `OpenClaw + Denkeeper worker` with state volume + health checks.
- Added startup hardening assets:
  - `ops/systemd` user units for reboot-safe compose startup
  - `ops/docker/healthcheck.sh` with optional webhook alert integration
- Fixed expense parser/category regressions from live interactions:
  - `from <merchant>` parsing for add commands
  - transport inference precedence for gas/fuel phrases
  - `yesterday` support for timeframe totals
  - fallback to `Unknown` for non-merchant filler text
- Fixed natural-language total variant:
  - `how much spent on gas this week` now resolves to `Transport` instead of falling back to overall weekly total
- Hardened OpenClaw expense response flow:
  - expense/receipt final replies are persisted as exact worker text
  - outbound `message_sending` enforcement now replaces model paraphrases with the exact worker answer before WhatsApp delivery
  - this removes model-added commentary from deterministic worker answers
- Fixed WhatsApp mention/query regressions:
  - leading numeric mentions are stripped before parsing
  - yes/no item queries such as `did I buy any milk last week?` now resolve to deterministic item-presence checks
  - bogus parser-created expense row from the old milk-query failure was soft-deleted from SQLite
- Fixed category and reporting regressions from live WhatsApp tests:
  - `baby stuff` now maps to `Baby`
  - near-miss category phrasing such as `bay stuff` and `babby category` now resolves through safe fuzzy category matching
  - `show me all expense categories` resolves correctly
  - `give me a breakdown of my expenses by category` now has deterministic support
  - `give me a breakdown by item for baby expenses today` now has deterministic support
  - `items under baby category from recent expenses` now resolves to an itemized category breakdown
- Fixed category-accounting inconsistency:
  - category totals and category breakdowns now use itemized receipt categories when receipt lines exist
  - standalone non-itemized expenses still use expense-header categories
- Cleaned live data pollution from older parser bugs:
  - soft-deleted bogus Target recategorization expense artifact `expenses.id=5`
- Expanded worker regression suite to `83 passed`.

## Priority Backlog

1. Startup hardening
- validate and enable systemd user units on target VM
- runbook for alert destination and escalation policy

2. Structured tool hardening
- add explicit clarification flows when required fields are missing from the tool call
- add plugin-level regression coverage for tool schema selection and exact-reply passthrough
- add more examples for mixed phrasing such as "what did I spend on X" vs "how much for X"

3. Scope safety hardening
- derive scope from chat/group ID or enforce group-to-scope mapping
- prevent typo-created accidental ledgers

4. Reporting/export
- monthly rollups from SQLite
- sheets export as reporting surface only
- decide account ownership and credential model

5. Deletion/total audit guardrails (note-only, no fix yet)
- add a repeatable reconciliation check for `total` and `delete last receipt` flows against SQLite audit + expense rows
- pin this as a regression suite invariant: totals before deletion vs after deletion must match expected deltas
- add a small operator command/doc section to run this reconciliation on demand after production incidents
