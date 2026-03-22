# Denkeeper Architecture

## Overview

Denkeeper is an OpenClaw-integrated capability layer.

- OpenClaw is the control plane (WhatsApp transport, agent runtime, scheduling, memory, plugin loading).
- Denkeeper is the domain plane (deterministic business logic, persistence, auditability, skill boundaries).

Current production slice is `expense-tracker`.

## Current Runtime Shape (2026-03-23)

Latest verified local runtime:

- Container stack is active and healthy:
  - `denkeeper-expense-worker` on `127.0.0.1:8765`
  - `denkeeper-openclaw` on `127.0.0.1:1455`
- SQLite data store is mounted at `workspace/projects/denkeeper/data/expenses.sqlite3`.
- Host-process mode remains supported for local debugging but is not the active runtime path.
- Worker regression suite: `72 passed`.

Supported deployment runtime:

- full container stack (`denkeeper-openclaw` + `denkeeper-expense-worker`) via `ops/docker/docker-compose.yml`
- persistent OpenClaw state volume (`denkeeper_openclaw_state`)
- shared SQLite bind mount (`workspace/projects/denkeeper/data`)
- optional reboot-safe user systemd units via `ops/systemd/*`

## Components

### 1. OpenClaw Gateway (Control Plane)

Owns:

- WhatsApp integration and group policy
- agent loop and tool invocation
- scheduling/cron
- session memory

### 2. Denkeeper Expense Plugin (Chat Boundary)

Owns:

- tool registration
- prompt-level tool guidance for expense flows
- exact tool-reply passthrough for expense/receipt responses
- outbound reply enforcement at the channel boundary for expense/receipt responses
- narrow request/response contract to worker
- no domain mutations or inference logic

Registered tools:

- `denkeeper_expense`: structured expense command path
- `denkeeper_receipt`: structured itemized receipt ingest path

### 3. Expense Worker (Domain + Persistence Boundary)

Owns:

- intent parsing and canonicalization
- category policy and inference
- validation and correction logic
- SQLite transactions
- audit logging

Endpoints:

- `POST /v1/expenses/handle`
- `POST /v1/expenses/handle-structured`
- `POST /v1/expenses/receipt`
- `GET /health`

### 4. SQLite Database

Tables:

- `expenses`
- `expense_items`
- `expense_audit_events`

Key behavior:

- mutation and audit event are committed atomically in one transaction
- soft-delete strategy for reversible history
- scope isolation supported via `scope` column

## Intent And Command Boundary

`denkeeper_expense` now passes a structured action contract into Denkeeper.

OpenClaw owns the natural-language to tool-schema step. Denkeeper owns deterministic execution once the structured action is chosen.

Structured actions currently supported:

- add expense
- change last expense category
- change item category in last receipt
- delete last expense
- delete last receipt
- undo last delete
- list expenses for a supported timeframe
- totals by timeframe/category
- category breakdown by timeframe
- itemized breakdown within a category by timeframe
- item spend totals
- yes/no item purchase checks
- list supported categories

The legacy raw-text worker endpoint still exists as a compatibility/fallback path, but it is no longer the primary OpenClaw contract.

## Response Boundary

For expense and receipt flows, the worker reply is the source of truth for the user-visible answer.

- OpenClaw may still decide when to call the tool.
- Once `denkeeper_expense` or `denkeeper_receipt` returns, the plugin persists that exact tool text.
- The plugin tries to rewrite the transcript-side assistant message before session write.
- The plugin also enforces the exact worker text at outbound `message_sending`, so WhatsApp receives the deterministic worker answer even if the model tries to paraphrase.
- This prevents model-added commentary from drifting away from the deterministic worker result.

## Receipt Path

`denkeeper_receipt` persists a receipt header (`expenses`) plus line items (`expense_items`).

- per-item category is inferred by Denkeeper by default
- per-item category hints from ingest payload are ignored
- user corrections happen explicitly via follow-up commands

This keeps category outcomes deterministic and auditable.

## Category Accounting Rule

Category-based answers now use an item-aware model:

- for itemized receipts, category totals come from `expense_items.item_category`
- for non-itemized standalone expenses, category totals come from `expenses.category`
- overall spend totals still use expense headers, because that is the actual transaction total

This avoids misclassifying mixed receipts such as one Target receipt that contains both Groceries and Baby items.

## Current Weak Point Addressed

The earlier raw-text boundary let OpenClaw send whole user sentences into a regex-heavy parser. That created a brittle failure mode where new phrasings broke behavior even though the model runtime was available.

Current fix:

- OpenClaw chooses a structured expense action
- worker executes a fixed deterministic contract
- raw parser remains as fallback coverage, not the main integration path

This is the current architectural direction for future Denkeeper skills as well: model for canonicalization, worker for deterministic domain behavior.

## Security Boundary

- Worker can require `x-denkeeper-token` (`DENKEEPER_EXPENSE_API_TOKEN`)
- Worker auth is fail-closed by default (`DENKEEPER_EXPENSE_REQUIRE_API_TOKEN=true`)
- Plugin injects token for worker calls
- OpenClaw channel policy limits processing to allowlisted group/user context
- Denkeeper stores audit records for traceability

## Deployment Model

Supported:

- Host-process mode (debug/local fallback)
- Full container mode (`OpenClaw + worker`) via `ops/docker/docker-compose.yml`

Hardening status:

- reboot-safe startup assets implemented (compose + systemd user-unit wrapper)
- periodic stack self-check script implemented (`ops/docker/healthcheck.sh`)
- remaining: target VM enablement and alert destination policy

## Design Rules

- Prefer native OpenClaw capabilities for platform concerns.
- Keep Denkeeper logic deterministic for stateful business operations.
- Preserve skill isolation; avoid cross-domain coupling.
- Treat SQLite as system of record; external sheets are reporting/export surfaces.
