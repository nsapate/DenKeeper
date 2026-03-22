# Denkeeper V1 Requirements

## Objective

Build an OpenClaw-integrated backend capability layer for a shared household assistant.

- OpenClaw owns WhatsApp transport, agent runtime, scheduling, and memory.
- Denkeeper owns deterministic domain logic, persistence, and auditability.

V1 scope is an expense-tracking capability for `Kyoto` in the shared WhatsApp group `The Den`.

## Primary User Workflows

1. Log an expense from natural language.
- Example: `spent 42 at Trader Joe's`
- Example: `add $18.50 for Starbucks as Eating Out`

2. Override or correct categorization.
- Example: `change last expense to Shopping`
- Example: `change item milk to Baby`

3. Manage recent entries.
- Example: `delete last expense`
- Example: `delete last receipt`
- Example: `undo that`

4. Query spend.
- Example: `show expenses today`
- Example: `how much did we spend on Jambra this week?`
- Example: `how much did I spend on milk last month?`

5. Ingest itemized receipts.
- Example: send receipt image/text, store line items and totals, review inferred line-item categories.

## Functional Requirements

- OpenClaw is the primary runtime and WhatsApp interface.
- Denkeeper integrates as isolated plugin/worker capabilities behind OpenClaw.
- Expense capability must support:
  - freeform text command handling
  - explicit category overrides
  - edit/delete/undo flows for recent records
  - delete-last-receipt flow
  - today list and timeframe totals
  - item-level totals across timeframe windows
  - itemized receipt ingest (header + line items)
  - per-item category inference by default
  - per-item recategorization via explicit command
- Expense actions and reads must be auditable in persistent storage.
- Skills must remain independently maintainable and separately toggleable.

## Expense Categories

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

## Category Rules

- User-specified category overrides inference.
- `Jambra` is a first-class category for junk/snack/treat purchases.
- Receipt ingest uses Denkeeper-managed per-item inference by default.
- Per-item category corrections happen through explicit user commands.
- `Other` is fallback when no stronger mapping exists.

## Non-Functional Requirements

- Modular, maintainable, readable code.
- Clear plugin/worker boundaries.
- SQLite durability across restarts.
- Secrets only through environment variables.
- Worker auth via token header when configured.
- Audit trail persistence for operational traceability.
- Low operational cost and low external dependency footprint.

## Operational Constraints

- Deployment target is a user-managed VM.
- OpenClaw handles channel policy and mention behavior.
- Denkeeper should not reimplement OpenClaw-native platform features.
- Runtime should support both host-process and full-stack container operation (`OpenClaw + worker`).

## Source Of Truth

- SQLite is the transactional source of truth for expense data and audit events.
- Sheets (if added) is reporting/export only.

## Out Of Scope For V1

- Custom chat gateway or custom WhatsApp bridge
- USCIS/VFS tracker integration in this expense skill
- Role-based access beyond OpenClaw allowlists/policies
- Full analytics dashboard UI
- Automated OCR pipeline tuning beyond current receipt ingest workflow

## Current Open Questions

- Final startup enablement on target VM (systemd user units implemented; enable/verify pending)
- Scope hardening completion (group-id mapping on top of allowlist)
- Reporting ownership and credentials for future Sheets export
