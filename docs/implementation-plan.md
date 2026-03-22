# Denkeeper Implementation Plan

## Goal

Deliver a stable OpenClaw-integrated household expense capability that is easy to extend with isolated future skills.

## Progress Status

### Phase 1: Repository Skeleton

Status: completed

- project structure, docs, ops folders, plugin/worker boundaries

### Phase 2: Expense Vertical Slice

Status: completed

- OpenClaw plugin (`expense-tracker`) with worker-backed tools
- SQLite persistence (`expenses`, `expense_items`, `expense_audit_events`)
- raw-text expense command handling
- category inference + explicit overrides
- today list, totals, item totals, category list
- undo/delete flows
- itemized receipt ingestion and line-item storage
- line-item recategorization in latest receipt
- delete-last-receipt support

### Phase 3: Reliability Hardening

Status: in progress

- parser and service regression tests in place (`46 passed`)
- TypeScript plugin compile checks passing
- full container topology added (`OpenClaw + expense-worker`) with health checks and persistent state volume
- container stack is currently running healthy in compose mode
- systemd user-unit templates added for reboot-safe compose startup
- stack healthcheck script added with optional webhook alert
- remaining:
  - enable and verify user units on target VM (`loginctl linger`, service/timer active)
  - production runbook for secrets rotation and state backup

### Phase 4: Intent Quality Hardening

Status: pending

- add stronger intent canonicalizer layer (schema-constrained parse + confidence + clarifications)
- preserve fixed handlers while improving natural-language coverage

### Phase 5: Scope Safety Hardening

Status: in progress

- completed:
  - env-driven scope allowlist guard (`DENKEEPER_EXPENSE_ALLOWED_SCOPES`)
- remaining:
  - derive scope from chat/group identity mapping
  - prevent manual scope input at runtime boundary

### Phase 6: Reporting Extensions

Status: pending

- monthly rollups from SQLite
- Google Sheets export/reporting (not source of truth)
- credential and ownership model finalization

## Technical Baseline

- OpenClaw as control plane and WhatsApp interface
- Denkeeper plugin + worker split
- FastAPI + SQLite for deterministic domain path
- Docker Compose path for full-stack deployment

## Immediate Next Steps

1. Enable and verify reboot-safe compose supervision on target VM.
2. Add scope derivation from group-id mapping at plugin boundary.
3. Add operator runbooks for backup/restore and incident reconciliation.
4. Continue parser/intent hardening without expanding handler surface.
