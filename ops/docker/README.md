# Denkeeper Container Runtime

This directory runs the full stack in containers:

- `denkeeper-expense-worker` (FastAPI + SQLite)
- `denkeeper-openclaw` (Gateway + WhatsApp/plugin runtime)

## 1. Configure Environment

```bash
cd /home/ninadsapate21/workspace/projects/denkeeper/ops/docker
cp .env.example .env
```

`ops/docker/.env` is local-only and must not be committed.

Set at least:

- `OPENCLAW_GATEWAY_TOKEN`
- `DENKEEPER_WORKER_TOKEN`

Recommended:

- `DENKEEPER_EXPENSE_ALLOWED_SCOPES=the-den`
- `DENKEEPER_EXPENSE_REQUIRE_API_TOKEN=true`
- `OPENCLAW_PRIMARY_MODEL=openai-codex/gpt-5.4`
- `OPENCLAW_WHATSAPP_GROUP_ALLOW_FROM_JSON`
- `OPENCLAW_WHATSAPP_GROUPS_JSON`
- `OPENCLAW_BOOTSTRAP_HOST_DIR` (optional auth bootstrap source)

## 2. (Optional) Reuse Existing OpenClaw Auth/State

If you already authenticated OpenClaw on host and want to keep WhatsApp + OAuth sessions:

```bash
./migrate-openclaw-state.sh
```

For model auth only (for example `openai-codex` OAuth), you can also seed just
`auth-profiles.json` without full state migration:

```bash
mkdir -p /home/ninadsapate21/workspace/projects/denkeeper/.denkeeper-bootstrap/agents/main/agent
cp ~/.openclaw/agents/main/agent/auth-profiles.json \
  /home/ninadsapate21/workspace/projects/denkeeper/.denkeeper-bootstrap/agents/main/agent/auth-profiles.json
```

At startup, `denkeeper-openclaw` bootstraps that file only when
`/openclaw/state/agents/main/agent/auth-profiles.json` is missing. Existing state
is never overwritten.

## 3. Start

```bash
docker compose --env-file .env up -d --build
```

## 4. Verify

```bash
docker compose ps
docker compose logs -f denkeeper-openclaw
docker compose logs -f denkeeper-expense-worker
```

Health checks:

- worker: `GET http://127.0.0.1:${DENKEEPER_WORKER_HOST_PORT:-8765}/health`
- gateway container health: TCP probe to `127.0.0.1:1455` inside the container

Optional local stack health script:

```bash
./healthcheck.sh
```

The script validates:

- both containers exist and are healthy/running
- worker HTTP health endpoint
- gateway TCP reachability on configured host port
- recent OpenClaw model-auth errors (token refresh failures) in container logs

Optional alert hook:

- set `DENKEEPER_ALERT_WEBHOOK_URL` in `.env`
- on failure, `healthcheck.sh` sends a JSON POST alert payload

Auth hardening envs:

- `DENKEEPER_ENFORCE_MODEL_AUTH_HEALTH=true`
- `DENKEEPER_AUTH_ERROR_LOOKBACK_MINUTES=15`
- optional `DENKEEPER_MODEL_AUTH_ERROR_PATTERNS=...`

## OAuth Recovery (openai-codex)

If Kyoto replies with an OAuth refresh failure, run:

```bash
cd /home/ninadsapate21/workspace/projects/denkeeper/ops/docker
./recover-openclaw-auth.sh
```

This script:

- runs interactive `openclaw models auth login` inside `denkeeper-openclaw`
- syncs fresh `auth-profiles.json` back to bootstrap
- restarts OpenClaw
- runs `healthcheck.sh`

Manual sync only (without login):

```bash
./sync-openclaw-auth-bootstrap.sh
```

## 5. Stop

```bash
docker compose down
```

To clear OpenClaw container state:

```bash
docker volume rm denkeeper_openclaw_state
```

If you clear the state volume and still want model auth to come back
automatically, keep `.denkeeper-bootstrap/agents/main/agent/auth-profiles.json`
available (or set `OPENCLAW_BOOTSTRAP_HOST_DIR` to your preferred host path).

## 6. Reboot-Safe Startup (systemd user units)

Unit templates are available in:

- `../systemd/denkeeper-compose.service`
- `../systemd/denkeeper-healthcheck.service`
- `../systemd/denkeeper-healthcheck.timer`
- `../systemd/install-user-units.sh`

Install and enable:

```bash
cd /home/ninadsapate21/workspace/projects/denkeeper/ops/systemd
./install-user-units.sh
```

The installer renders unit templates with your local repository path, then enables the compose service and healthcheck timer.

To run user units on VM reboot without login:

```bash
sudo loginctl enable-linger "$USER"
```
