# Denkeeper Session Notes

## Project Identity

- Project name: `denkeeper`
- Assistant name: `Kyoto`
- Shared WhatsApp group name: `The Den`

## Latest Status (2026-03-23)

- Runtime mode: Docker Compose (`denkeeper-openclaw` + `denkeeper-expense-worker`) is active and healthy.
- Worker regression suite: `72 passed`.
- Current expense architecture changed again after live WhatsApp failures:
  - OpenClaw no longer sends only raw expense text to the worker
  - `denkeeper_expense` now uses a structured action contract
  - worker executes deterministic actions instead of depending on regex-first intent parsing
  - raw parser remains as a fallback/compatibility path, not the main OpenClaw boundary
- Structured expense actions now supported by the worker:
  - add expense
  - change last expense category
  - change last receipt item category
  - delete last expense
  - delete last receipt
  - undo last delete
  - list expenses by timeframe
  - totals by timeframe/category
  - category breakdown by timeframe
  - itemized breakdown within a category by timeframe
  - item spend totals
  - yes/no item purchase checks
  - list supported categories
- Recent live failure fixes now covered by regression tests:
  - `how much spent on gas this week` routes to `Transport`
  - WhatsApp mention prefixes like `@57192489156720` are stripped before parsing
  - yes/no item queries like `did I buy any milk last week?` do not fall through to `ADD`
  - `baby stuff` category phrasing maps to `Baby`
  - `show me all expense categories` resolves deterministically
  - `give me a breakdown of my expenses by category` now has a first-class handler
  - `give me a breakdown by item for baby expenses today` now has a first-class handler
  - `items under baby category from recent expenses` now resolves to a category-item breakdown instead of falling back to an expense-entry list
- Latest live worker checks after rebuild:
  - `how much did I spend on baby stuff today?` -> `Baby spend for today is $153.41.`
  - `give me a breakdown of my expenses by category` -> monthly category breakdown with total
  - `show me all expense categories` -> supported category list
  - `give me a breakdown by item for baby expenses today` -> `Kendamil / Skip Hop / Up&Up` item rollup totaling `$153.41`
- Response hardening remains in place:
  - expense/receipt final replies are forced to the exact worker tool output instead of model-written summaries
  - outbound `message_sending` enforcement remains the last channel boundary before WhatsApp delivery
- Manual data correction applied in SQLite for prior miscategorized entries:
  - gas entry corrected to `Transport`
  - Target receipt baby items corrected (`Kendamil`, `Up&Up`, `Skip Hop`)
- Bad live-test expense row created by the old parser was soft-deleted from SQLite:
  - bogus milk-query expense `id=11` no longer affects totals
- Additional bogus live-test expense row was soft-deleted from SQLite:
  - Target recategorization artifact `expenses.id=5` no longer double-counts Baby totals

Note: older sections below are retained as chronological history and may reflect earlier checkpoints.

## Initial Product Direction

The original idea was a shared household assistant accessible from WhatsApp, used by two household members for:

- expense tracking
- USCIS / VFS status checks
- scheduling
- future household workflows

The desired experience is a shared personal agentic butler, not just a narrow utility bot.

## Major Architecture Decision

The architecture changed during the session.

### Rejected direction

Do not make Denkeeper its own full chat platform with:

- custom WhatsApp bridge
- custom orchestrator
- custom scheduling control plane

That would duplicate what OpenClaw already provides.

### Chosen direction

Use:

- `OpenClaw` as the control plane
- `Denkeeper` as the backend capability layer

OpenClaw owns:

- WhatsApp integration
- chat runtime
- scheduling / cron
- plugin loading
- channel policy and group interaction

Denkeeper owns:

- isolated skills
- deterministic business logic
- local persistence
- optional worker services for heavier tasks

This split was chosen because it is cleaner, more maintainable, and avoids building a parallel agent platform.

## Native-First OpenClaw Principle

You explicitly want to leverage existing OpenClaw functionality wherever possible instead of rebuilding it as custom Denkeeper code.

This became an architectural rule:

- prefer OpenClaw-native capabilities first
- build Denkeeper-specific code only where native functionality is insufficient or where deterministic domain logic and persistence are required

Capabilities you specifically want to lean on from OpenClaw include:

- memory between sessions
- browser controls
- existing skills system
- scheduling and cron
- the general agent runtime

This means Denkeeper should stay thin around platform concerns and focus on:

- expense persistence and reporting
- deterministic domain logic
- future specialized worker-style integrations like USCIS / VFS tracking

## Skill Isolation Principles

A major requirement is strong isolation between skills.

Requirements discussed:

- expense tracking should not share domain logic with USCIS tracking
- future immigration tracking should not be tightly coupled to expense tracking
- each skill should be easy to enable, disable, replace, or extend
- shared code should remain domain-agnostic
- avoid spaghetti architecture

The intended shape is:

- thin OpenClaw-facing plugin layer
- isolated skill modules
- optional local worker services for deterministic or long-running tasks

## V1 Focus

The first implemented capability is:

- `expense-tracker`

This is the first vertical slice for Denkeeper.

## Expense Tool Contract Decision

You explicitly pushed back on two bad extremes:

- making OpenClaw prompting fully responsible for expense correctness
- expanding Denkeeper into a brittle regex-heavy parser

Decision (latest):

- keep a single Denkeeper expense tool
- but make the OpenClaw-to-Denkeeper contract structured
- OpenClaw now chooses a fixed expense action and fills canonical fields
- Denkeeper owns:
  - deterministic validation
  - category policy
  - persistence
  - audit logging
  - fixed handler behavior

Important principle:

- OpenClaw does natural-language canonicalization into a bounded schema
- Denkeeper does deterministic domain policy and state mutation

Reason for the change:

- the raw-text boundary was too brittle
- every new phrasing became a parser bug
- the model runtime was available but underused

Current rule:

- use model intelligence for tool argument shaping
- keep worker behavior deterministic after the tool call

Additional refinement:

- category totals are now item-aware
- itemized receipts use `expense_items.item_category`
- standalone expenses use `expenses.category`

## Audit Logging Decision

You explicitly asked for persistent audit logging that does not depend on raw OpenClaw logs.

Decision:

- OpenClaw transcripts can exist for runtime/session history
- Denkeeper must own a SQLite-backed audit trail for domain actions

Implementation added to the expense worker:

- append-only table: `expense_audit_events`
- records:
  - request text
  - scope
  - actor ID / actor name
  - parsed command kind when available
  - action result
  - success / failure
  - linked expense ID when relevant
  - reply text
  - metadata payload
  - timestamp

Important implementation rule:

- an expense mutation and its audit event commit in the same SQLite transaction

This means:

- successful adds / updates / deletes are auditable
- read/query actions are auditable
- validation failures are also auditable

## Expense Tracking Goals

Kyoto should support:

- logging expenses from natural language
- explicit category override
- correcting the last expense
- deleting the last expense
- undoing the last deletion
- querying recent expenses
- future reporting and monthly summaries

Examples discussed:

- `spent 42 at Trader Joe's`
- `add $18.50 for Starbucks as Eating Out`
- `log 12 as Jambra`
- `put this under Baby`
- `change last expense to Shopping`
- `delete last expense`
- `undo that`
- `show expenses today`
- `how much did we spend on Jambra this week?`

## Final Expense Categories

The agreed fixed category set is:

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

### Category rationale

- `Mortgage` replaced `Rent`
- `Transport` was preferred over `Gas` because it includes:
  - gas
  - parking
  - tolls
  - rideshare
  - car servicing
  - related transport expenses
- `Home Maintenance` was added for:
  - cleaners
  - yard work
  - repairs
  - upkeep services
- `Other` remains as the fallback category

### Jambra definition

`Jambra` is a first-class category and not just a tag.

Definition:

- non-essential edible purchases
- guilt snacks
- junk food
- treats
- chips
- chocolate
- cake
- soda
- similar indulgence items

Important distinction:

- grocery essentials should stay in `Groceries`
- junk/treat/snack items should go to `Jambra`
- restaurant and cafe purchases still belong in `Eating Out`

## Category Override Rules

Important explicit rule:

- user-specified category always overrides system inference

Kyoto should support both:

- inferred categorization
- explicit user override

Examples discussed:

- `Add $14 Starbucks as Jambra`
- `Mark this receipt as Groceries not Shopping`
- `Log $42 at Target under Baby`
- `This is Jambra`
- `Put this under Shopping`

## Engineering Principles Requested

You explicitly asked that implementation follow principal-engineer-level standards:

- modular
- maintainable
- readable
- robust
- containerized
- easy to understand
- well commented, but only where comments add real value
- not spaghetti

This led to creation of reusable prompt files under:

- `/home/ninadsapate21/workspace/projects/prompts/principal-engineering-practices.md`
- `/home/ninadsapate21/workspace/projects/prompts/project-kickoff.md`

## Repository Direction

Denkeeper should be deployable anywhere and container-friendly.

The current direction is:

- OpenClaw plugin layer
- local worker service for expense tracking
- SQLite persistence
- future adapters for reporting/export

The implemented worker is currently:

- SQLite-backed
- FastAPI-based
- isolated from OpenClaw runtime concerns

The OpenClaw plugin is intentionally thin and delegates business logic to the worker.

## Source Of Truth Decision

The source of truth should be:

- `SQLite`

Reasoning:

- supports edits, undo, and deletes cleanly
- better transactional integrity than Sheets
- simpler to maintain as the real write path
- portable and low cost

This was an explicit decision:

- Google Sheets should not be the primary transactional database

## Reporting / Sheets Discussion

You want the eventual review surface to be:

- easy to analyze
- organized by month
- not just a raw export

Important decision:

- Sheets should be treated as a reporting and review surface
- not as the system of record

### Desired future reporting structure

Suggested workbook layout:

- `Transactions`
- `Monthly Summary`
- `Monthly Detail`

### Intended sheet purpose

This is not meant to be only an audit log.

The goal is:

- structured monthly breakdown
- easier household analysis
- better review experience for both household members

### Proposed monthly summary shape

One row per month with totals for:

- total spend
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

### Proposed monthly detail shape

Possible rows grouped by:

- month + category

and later possibly:

- month + category + merchant

### Important implementation principle for reporting

When Sheets is added later:

- Denkeeper should compute monthly aggregates from SQLite
- Denkeeper should write clean tables into Sheets
- do not rely on fragile spreadsheet formulas for core business logic

## Deferred Sheets Work

Sheets integration was intentionally deferred.

Reason:

- account choice is not decided yet
- credential model is not decided yet
- shared ownership/access model needs to be figured out first

Open question:

- whose Google account or shared household account should own the reporting sheet?

## OpenClaw / WhatsApp Notes

Earlier in the broader discussion:

- OpenClaw was identified as the right chat runtime and WhatsApp-facing system
- Denkeeper should sit behind it as a capability layer
- the expense tracker is a better fit for agent-driven interaction than deterministic polling tools like USCIS/VFS checks

## Current Implementation Snapshot

Current state, Denkeeper contains:

- planning docs
- OpenClaw-first architecture
- expense plugin (loaded in OpenClaw)
- expense worker service
- SQLite persistence layer
- parser/service logic for expense + receipt flows

Verified so far:

- worker source compiles
- worker tests pass (`46 passed`)
- plugin compile checks pass (`npx tsc --noEmit`)
- live OpenClaw plugin runtime integration is active
- end-to-end WhatsApp flow through Kyoto is active

Still deferred:

- Google Sheets reporting/export

## Immediate Next Priorities

Current next steps:

1. Productionize startup/restart behavior for OpenClaw + worker.
2. Harden scope derivation/allowlist mapping.
3. Continue intent canonicalization hardening while keeping handlers fixed.
4. Decide Sheets ownership and credentials.
5. Add monthly reporting/export when ownership is finalized.

## Latest Runtime Fixes (2026-03-22)

Implemented after live The Den transcript review:

- Re-architecture completed for expense tool contract:
  - OpenClaw now sends only raw user text plus optional actor/scope metadata.
  - Denkeeper now owns full intent/category/timeframe resolution.
- Fixed parser coverage for summary/category requests that were failing in chat:
  - `show weekly expense`
  - `monthly total`
  - `show all expense categories`
- Added guard so amount-bearing add messages (for example, `spent $12 today`) are not misclassified as summary queries.
- Fixed worker total reply path for categoryless totals:
  - now returns `Total spend for this week/month...` safely.
- Fixed intermittent FastAPI/SQLite 500s by opening SQLite connections with `check_same_thread=False`.
- Added tests for:
  - categoryless weekly/monthly totals
  - category list phrasing variants
  - add-vs-total misclassification guard

Status at that checkpoint:

- expense-worker tests at that checkpoint (`28 passed`)
- live local API smoke checks passing for weekly/monthly totals, category list, and receipt itemization
- worker process running on `127.0.0.1:8765` with persisted SQLite path:
  - `/home/ninadsapate21/workspace/projects/denkeeper/data/expenses.sqlite3`

## Latest Interaction Follow-up (2026-03-22)

Issue observed from latest `The Den` interaction:

- `denkeeper_receipt` call produced line items where everything was tagged as `Groceries`, including items that should be split to `Baby`/`Jambra`.
- Root cause: tool payload was allowing per-item category values from model output, which could override backend inference behavior.

Fixes implemented:

- Backend enforcement in worker:
  - receipt ingest now ignores incoming per-item category hints and always runs Denkeeper item-category inference by default.
- Plugin contract tightened:
  - removed per-item `category` from receipt tool schema and request payload types.
- Skill guidance updated:
  - prompt instructions now tell Kyoto/OpenClaw to send item description + amount only for each receipt line.
- Regression test added:
  - ensures `Chocolate Chips` maps to `Jambra` even if payload tries to force `Groceries`.

Verification completed at that checkpoint:

- Worker tests at that checkpoint: `28 passed`
- Plugin type-check: `npx tsc --noEmit` passed
- Runtime smoke check: payload with forced `Groceries` still returns inferred split (`Baby Milk Powder -> Baby`, `Cookies -> Jambra`)

## Latest Interaction Follow-up 2 (2026-03-22)

Issue observed from newest The Den messages:

- `Kyoto delete last receipt` and `Kyoto delete all expenses from last receipt` were routed to expense parsing that required amount, returning:
  - `I could not find an amount in that request.`

Fixes implemented:

- Added a dedicated parser intent:
  - `DELETE_LAST_RECEIPT`
  - supports phrasing variants for delete/remove + last/latest/recent receipt.
- Added a dedicated service handler:
  - deletes most recent active receipt (latest expense that has itemized receipt lines), not the latest generic expense.
- Added repository support:
  - lookup + soft-delete for the latest active receipt with item count metadata.
- Added tests:
  - parser coverage for delete-last-receipt variants.
  - end-to-end service regression confirming receipt deletion does not delete newer non-receipt expenses.

Verification completed at that checkpoint:

- Worker tests at that checkpoint: `28 passed`
- Runtime API smoke:
  - `Kyoto delete last receipt` now returns `receipt_deleted`.
  - after delete: item query (`milk this month`) returns `$0.00`, while overall monthly total still includes non-receipt expenses.

## Runtime Deployment Check (2026-03-22)

Runtime state on instance at that checkpoint:

- OpenClaw is currently running as a host process (`openclaw`, `openclaw-gateway`), not under systemd user service.
- Expense worker is currently running as a host `uvicorn` process.
- A Denkeeper compose file exists at `ops/docker/docker-compose.yml` with `restart: unless-stopped` for worker container, but this compose deployment is not currently the active runtime path.
- No OpenClaw/Denkeeper systemd unit was found; no reboot auto-start guarantee exists yet for current host-process launch path.

## Latest Interaction Follow-up 3 (2026-03-22)

Issue observed:

- On receipt ingest, tool output included full itemized lines, but Kyoto’s final reply compressed that into a one-line summary.

Fixes implemented:

- Updated Kyoto expense skill guidance to require full itemized breakdown in final replies for `denkeeper_receipt`.
- Added explicit instruction to prefer verbatim tool response for successful receipt ingests.
- Updated tool description text in plugin registration to reinforce no-summary behavior for receipt replies.
- Reloaded OpenClaw gateway after skill/plugin updates.

Verification at that checkpoint:

- Local agent smoke response now includes itemized receipt lines in the final reply payload.

## Latest Interaction Follow-up 4 (2026-03-22)

Issue reviewed:

- perceived mismatch after `Kyoto delete last receipt` followed by total/discovery queries.

Cross-check summary (OpenClaw logs + SQLite audit/events):

- `Kyoto total weekly expense` returned the expected pre-delete weekly total.
- `Kyoto delete last receipt` deleted the latest receipt entry for that scope.
- follow-up queries for `last week` and `last month` were correct for their windows.
- current `this week` active total correctly reflected pre-delete total minus deleted receipt amount.

Conclusion:

- deletion flow is consistent with persisted data.
- confusion comes from timeframe semantics in NL query interpretation (`last week` vs `this week`, calendar-week expectation vs user expectation).

## Latest Interaction Follow-up 5 (2026-03-22)

Improvements implemented after the above review:

- Parser canonicalization hardening:
  - short phrases such as `total expense this week` now resolve to overall `expense_total` (not `item_expense_total`).
  - short phrases such as `total groceries this week now` now resolve to category total (`Groceries`) with optional `now` suffix support.
- Delete confirmation clarity:
  - `delete last receipt` reply now includes refreshed `this week` total in the same response.

Verification:

- Worker tests at that checkpoint: `30 passed`.
- Live worker smoke:
  - `Kyoto total expense this week` -> `expense_total` with correct amount.
  - `Kyoto total groceries this week now` -> `expense_total` with category `Groceries`.
- `Kyoto delete last receipt` -> includes `This week's total is now ...` in reply.

## Latest Interaction Follow-up 6 (2026-03-22)

Scope safety hardening implemented:

- Added optional environment-based scope allowlist:
  - `DENKEEPER_EXPENSE_ALLOWED_SCOPES` (comma-separated, example: `the-den,travel-2026`)
- Behavior:
  - if unset/empty: existing behavior unchanged
  - if set: unknown scope requests return `validation_error` and no expense mutation occurs
- Applied to both command handling and receipt ingest paths.

Verification at that checkpoint:

- New tests added for command and receipt allowlist rejection.
- Worker test suite at that checkpoint: `34 passed`.
- Worker restarted and healthy after changes.
- Live runtime now started with:
  - `DENKEEPER_EXPENSE_ALLOWED_SCOPES=the-den`
  - verified allowed scope succeeds and typo scope is rejected.

## Latest Interaction Follow-up 7 (2026-03-22)

Full-stack containerization implemented (`OpenClaw + Denkeeper worker`).

Changes:

- Added full compose topology in `ops/docker/docker-compose.yml`:
  - `denkeeper-expense-worker` service
  - `denkeeper-openclaw` service
  - service health checks and `restart: unless-stopped`
  - persistent OpenClaw state volume (`denkeeper_openclaw_state`)
- Added OpenClaw container image:
  - `ops/docker/openclaw/Dockerfile`
  - installs OpenClaw CLI and bundles `expense-tracker` plugin
  - starts gateway via deterministic entrypoint
- Added OpenClaw runtime bootstrap:
  - `ops/docker/openclaw/entrypoint.sh`
  - enforces required secrets (`OPENCLAW_GATEWAY_TOKEN`, `DENKEEPER_WORKER_TOKEN`)
  - sets plugin/gateway/channel config from environment each startup
- Added container config baseline:
  - `ops/docker/openclaw/openclaw.base.json`
- Added operator assets:
  - `ops/docker/.env.example`
  - `ops/docker/README.md`
  - `ops/docker/migrate-openclaw-state.sh` (host state -> named Docker volume migration)

Validation at that checkpoint:

- compose file renders successfully with injected env vars (`docker compose config`)
- worker test suite remained green (`34 passed`)

## Recovery Snapshot (2026-03-22, post-session crash)

Recovery validation performed after reloading from an older chat session (historical checkpoint):

- worker tests at that checkpoint: `34 passed`
- plugin typecheck: `npx tsc --noEmit` passed
- compose render: `docker compose --env-file .env.example config` passed

Runtime observed on instance at that checkpoint:

- host expense worker is running on `127.0.0.1:8765`
- OpenClaw host gateway was not running at that checkpoint
- no denkeeper containers are currently running

Doc consistency updates applied:

- corrected stale runtime notes in `docs/architecture.md` and `ops/openclaw/README.md`
- updated container README gateway healthcheck wording to match TCP-based probe

## Latest Interaction Follow-up 8 (2026-03-22)

Startup hardening implementation added to continue backlog execution:

- Added `ops/docker/healthcheck.sh`:
  - validates compose availability
  - validates worker/openclaw container state + health
  - validates worker HTTP health endpoint and gateway TCP reachability
  - optional alert hook via `DENKEEPER_ALERT_WEBHOOK_URL`
- Added systemd user-unit assets in `ops/systemd`:
  - `denkeeper-compose.service`
  - `denkeeper-healthcheck.service`
  - `denkeeper-healthcheck.timer`
  - `install-user-units.sh`
  - `README.md` runbook
  - unit templates are rendered with detected project root during install (no hardcoded checkout path)

Status:

- startup hardening assets are implemented
- target VM enablement/verification is still pending (unit install + linger enable)

## Latest Interaction Follow-up 9 (2026-03-22)

Freeform query hardening pass applied after reviewing the latest WhatsApp failures.

Root cause confirmed from OpenClaw session trace and SQLite audit:

- older runtime had no first-class intent for "itemized breakdown within a category"
- model selected `list_expenses` for prompts like:
  - `give me a breakdown by item for baby expenses today`
  - `give me a breakdown of items under baby category from recent expenses`
- `list_expenses` ignores category-level line-item rollups and returned full expense-entry lists instead
- category-like typo phrasing such as `bay stuff` also relied too heavily on model normalization

Hardening applied:

- worker category normalization now supports safe fuzzy matching for near-miss category text
- parser category-context extraction now handles `under <category> category` and `for <category> expenses`
- OpenClaw expense tool guidance now explicitly maps `by item`, `itemized`, and `items under <category>` phrasing to `category_item_breakdown`
- regression suite expanded to cover:
  - numeric WhatsApp mentions + repeated wording like `breakdown down by item`
  - fuzzy category phrase `babby category`
  - typo-style total query `bay stuff`

Verification:

- worker tests: `83 passed`
- plugin type-check: passed
- live worker verification:
  - `@57192489156720 give me a breakdown of items under baby category from recent expenses`
    - `Item breakdown for Baby during this week ... Total: $153.41`
  - `@57192489156720 how much did I spend on bay stuff today?`
    - `Baby spend for today is $153.41.`
