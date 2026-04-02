#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/.env}"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "${ENV_FILE}"
  set +a
fi

OPENCLAW_CONTAINER_NAME="${OPENCLAW_CONTAINER_NAME:-denkeeper-openclaw}"
SYNC_BOOTSTRAP_AFTER_LOGIN="${SYNC_BOOTSTRAP_AFTER_LOGIN:-true}"

echo "Starting OpenClaw OAuth recovery for openai-codex in container: ${OPENCLAW_CONTAINER_NAME}"
echo "Follow prompts, complete browser login locally, then paste callback URL into terminal."

docker exec -it "${OPENCLAW_CONTAINER_NAME}" \
  sh -lc 'openclaw models auth login --provider openai-codex --set-default'

if [[ "${SYNC_BOOTSTRAP_AFTER_LOGIN}" == "true" ]]; then
  "${SCRIPT_DIR}/sync-openclaw-auth-bootstrap.sh"
fi

echo "Restarting OpenClaw container to refresh runtime auth state..."
docker restart "${OPENCLAW_CONTAINER_NAME}" >/dev/null

echo "Running Denkeeper healthcheck..."
"${SCRIPT_DIR}/healthcheck.sh"

echo "OpenClaw OAuth recovery complete."
