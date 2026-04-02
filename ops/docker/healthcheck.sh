#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"
COMPOSE_FILE="${COMPOSE_FILE:-${SCRIPT_DIR}/docker-compose.yml}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-1455}"
DENKEEPER_WORKER_HOST_PORT="${DENKEEPER_WORKER_HOST_PORT:-8765}"
DENKEEPER_ALERT_WEBHOOK_URL="${DENKEEPER_ALERT_WEBHOOK_URL:-}"
DENKEEPER_OPENCLAW_CONTAINER="${DENKEEPER_OPENCLAW_CONTAINER:-denkeeper-openclaw}"
DENKEEPER_ENFORCE_MODEL_AUTH_HEALTH="${DENKEEPER_ENFORCE_MODEL_AUTH_HEALTH:-true}"
DENKEEPER_AUTH_ERROR_LOOKBACK_MINUTES="${DENKEEPER_AUTH_ERROR_LOOKBACK_MINUTES:-15}"
DENKEEPER_MODEL_AUTH_ERROR_PATTERNS="${DENKEEPER_MODEL_AUTH_ERROR_PATTERNS:-OAuth token refresh failed|refresh_token_reused|Failed to refresh OAuth token for openai-codex}"

fail() {
  local message="$1"
  echo "DENKEEPER_HEALTHCHECK_FAIL: ${message}" >&2
  if [[ -n "${DENKEEPER_ALERT_WEBHOOK_URL}" ]]; then
    curl -sS -X POST \
      -H "content-type: application/json" \
      -d "{\"service\":\"denkeeper\",\"status\":\"failed\",\"message\":\"${message}\"}" \
      "${DENKEEPER_ALERT_WEBHOOK_URL}" >/dev/null || true
  fi
  exit 1
}

ensure_container_state() {
  local container="$1"
  local state
  state="$(docker inspect --format '{{.State.Status}}' "${container}" 2>/dev/null || true)"
  [[ -n "${state}" ]] || fail "${container} container not found"
  [[ "${state}" == "running" ]] || fail "${container} state is ${state}"

  local health
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container}" 2>/dev/null || true)"
  if [[ "${health}" != "none" && "${health}" != "healthy" ]]; then
    fail "${container} health is ${health}"
  fi
}

ensure_tcp_port() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.create_connection(("127.0.0.1", port), timeout=2):
    pass
PY
}

ensure_model_auth_is_healthy() {
  if [[ "${DENKEEPER_ENFORCE_MODEL_AUTH_HEALTH}" != "true" ]]; then
    return
  fi

  local recent_logs
  recent_logs="$(
    docker logs --since "${DENKEEPER_AUTH_ERROR_LOOKBACK_MINUTES}m" "${DENKEEPER_OPENCLAW_CONTAINER}" 2>&1 || true
  )"
  if [[ -z "${recent_logs}" ]]; then
    return
  fi

  if grep -Eiq "${DENKEEPER_MODEL_AUTH_ERROR_PATTERNS}" <<<"${recent_logs}"; then
    fail "model auth failure detected in recent OpenClaw logs (last ${DENKEEPER_AUTH_ERROR_LOOKBACK_MINUTES}m)"
  fi
}

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps >/dev/null 2>&1 \
  || fail "docker compose stack is unavailable"

ensure_container_state "denkeeper-expense-worker"
ensure_container_state "denkeeper-openclaw"

curl -fsS "http://127.0.0.1:${DENKEEPER_WORKER_HOST_PORT}/health" >/dev/null \
  || fail "worker health endpoint failed"

ensure_tcp_port "${OPENCLAW_GATEWAY_PORT}" \
  || fail "gateway TCP check failed on port ${OPENCLAW_GATEWAY_PORT}"

ensure_model_auth_is_healthy

echo "DENKEEPER_HEALTHCHECK_OK"
