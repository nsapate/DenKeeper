# Denkeeper

Denkeeper is the backend capability layer for your OpenClaw-based household assistant.

The user-facing assistant is `Kyoto`, and the shared WhatsApp group is `The Den`.

## System Role

Denkeeper is not the chat platform itself.

OpenClaw owns:

- WhatsApp channel integration
- agent runtime
- scheduling and cron
- plugin loading
- chat-facing orchestration

Denkeeper owns:

- isolated household skills
- domain policy, validation, and deterministic business logic
- local persistence
- SQLite-backed audit trails for domain actions
- optional worker services for specialized tasks

## Current Focus

Version 1 currently ships one isolated OpenClaw-backed capability:

- `expense-tracker`

The long-term design supports additional isolated skills, such as:

- expense tracking
- USCIS / VFS status tracking
- household reminders
- daily summaries
- receipt image processing

## Design Goals

- OpenClaw-first architecture
- native-first feature usage: prefer built-in OpenClaw capabilities before custom code
- strong skill isolation
- per-skill maintainability and clear ownership
- container-first deployment
- durable local state
- readable, maintainable code over shortcuts

## Project Docs

- [Requirements](./docs/requirements.md)
- [Architecture](./docs/architecture.md)
- [Implementation Plan](./docs/implementation-plan.md)
- [Session Notes](./docs/session.md)

## Status

The repository now contains a working OpenClaw + Denkeeper expense vertical slice:

- OpenClaw plugin with two tools: `denkeeper_expense` and `denkeeper_receipt`
- SQLite-backed expense worker (FastAPI)
- append-only SQLite audit trail for expense interactions
- raw-text tool contract for expense intent handling
- itemized receipt ingestion with per-item category inference
- item-level total queries and item recategorization in the latest receipt
- delete-last-receipt support

Current test status (worker): `46 passed`.

Recent behavior hardening in the expense worker:

- gas/fuel phrases now reliably infer `Transport` even when merchant is a grocery chain
- merchant extraction supports `from` phrases (for example `from Costco`)
- `yesterday` timeframe is supported for totals
- non-merchant filler phrases now cleanly store as `Unknown` instead of noisy labels

Runtime options:

- host-process mode (supported for local debugging)
- full container mode (`OpenClaw + worker`) via [ops/docker/README.md](./ops/docker/README.md)
- reboot-safe compose startup via user systemd units in [ops/systemd/README.md](./ops/systemd/README.md)

## Security And Git Hygiene

- Secrets must live only in runtime env files (for example `ops/docker/.env`), never in committed code.
- `.env` and `.env.*` are gitignored; keep only template files such as `.env.example` in git.
- OpenClaw auth profile secrets are gitignored (`**/auth-profiles.json` and `.denkeeper-bootstrap/`).
- Worker auth is fail-closed by default (`DENKEEPER_EXPENSE_REQUIRE_API_TOKEN=true`).
- SQLite data and logs are gitignored (`data/*.sqlite3`, `*.log`).
- TLS keys/certs and token files are gitignored (`*.key`, `*.pem`, `*.p12`, `*.pfx`, `*.token`).

Before pushing to GitHub, run a quick local leak scan:

```bash
rg -n --hidden -g '!plugins/**/node_modules/**' -g '!workers/**/.venv/**' -g '!data/**' \
  '(OPENCLAW_GATEWAY_TOKEN|DENKEEPER_WORKER_TOKEN|sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{20,}|BEGIN .* PRIVATE KEY|token=|secret=)'
```

## Expense Tool Contracts

`denkeeper_expense` uses a raw-text handoff.

- OpenClaw passes the exact request text and actor/scope metadata
- Denkeeper performs intent detection, category interpretation, validation, persistence, and audit logging
- OpenClaw should not construct structured expense intents or category payloads for this tool
- This includes yes/no purchase checks such as `did I buy any milk last week?`

This keeps OpenClaw as chat transport/orchestration while Denkeeper owns expense domain behavior end to end.

`denkeeper_receipt` handles structured itemized receipt ingestion.

- OpenClaw passes merchant, line items, totals, and optional actor/scope metadata
- Denkeeper enforces item-category inference by default during ingest
- post-ingest item corrections happen through explicit chat commands (for example: `change item milk to Baby`)

## Audit Trail

The expense worker now persists an append-only audit log in the same SQLite database as the expense records.

- table: `expense_audit_events`
- captures: request text, actor, scope, parsed command kind, action result, success/failure, linked expense ID, reply text, metadata, timestamp
- write behavior: expense mutations and their audit events commit in a single SQLite transaction

This audit trail is the Denkeeper-owned system of record for expense interactions. OpenClaw session transcripts remain useful for debugging, but they are not the preferred long-term audit surface.
