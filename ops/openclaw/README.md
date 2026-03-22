# OpenClaw Integration

This project uses OpenClaw as control plane and Denkeeper as capability layer.

## Install The Expense Plugin

```bash
openclaw plugins install /home/ninadsapate21/workspace/projects/denkeeper/plugins/expense-tracker
cd /home/ninadsapate21/workspace/projects/denkeeper/plugins/expense-tracker
pnpm install
openclaw plugins enable expense-tracker
```

Restart OpenClaw after install/config changes.

## Plugin Config

```json
{
  "plugins": {
    "entries": {
      "expense-tracker": {
        "enabled": true,
        "config": {
          "workerBaseUrl": "http://127.0.0.1:8765",
          "apiToken": "<DENKEEPER_WORKER_TOKEN>",
          "defaultScope": "the-den",
          "requestTimeoutMs": 5000
        }
      }
    }
  }
}
```

## Tools Exposed

- `denkeeper_expense`
  - raw-text expense command handling
- `denkeeper_receipt`
  - structured itemized receipt ingestion

## Worker Runtime Requirement

The plugin requires the expense worker to be reachable at `workerBaseUrl`.

Host-process example:

```bash
cd /home/ninadsapate21/workspace/projects/denkeeper/workers/expense-worker
DENKEEPER_EXPENSE_DB_PATH=/home/ninadsapate21/workspace/projects/denkeeper/data/expenses.sqlite3 \
DENKEEPER_EXPENSE_API_TOKEN=<DENKEEPER_WORKER_TOKEN> \
DENKEEPER_EXPENSE_REQUIRE_API_TOKEN=true \
DENKEEPER_EXPENSE_TIMEZONE=America/Los_Angeles \
DENKEEPER_EXPENSE_ALLOWED_SCOPES=the-den \
.venv/bin/uvicorn expense_worker.main:app --app-dir ./src --host 127.0.0.1 --port 8765
```

Container path (full stack: OpenClaw + worker) is available at:

- `ops/docker/docker-compose.yml`
- `ops/docker/README.md`

## Current Ops Note

As of 2026-03-23:

- compose runtime is active and healthy:
  - `denkeeper-expense-worker` (healthy)
  - `denkeeper-openclaw` (healthy)
- full container runtime is managed from `ops/docker`
- reboot-safe startup templates are available in `ops/systemd`
- host-process commands in this file remain valid as a debug fallback
