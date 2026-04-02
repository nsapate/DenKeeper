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
OPENCLAW_STATE_AUTH_PATH="${OPENCLAW_STATE_AUTH_PATH:-/openclaw/state/agents/main/agent/auth-profiles.json}"
OPENCLAW_BOOTSTRAP_HOST_DIR="${OPENCLAW_BOOTSTRAP_HOST_DIR:-../../.denkeeper-bootstrap}"

BOOTSTRAP_ABS_DIR="$(cd "${SCRIPT_DIR}" && cd "${OPENCLAW_BOOTSTRAP_HOST_DIR}" && pwd)"
TARGET_AUTH_PATH="${BOOTSTRAP_ABS_DIR}/agents/main/agent/auth-profiles.json"
TMP_AUTH_PATH="$(mktemp)"
trap 'rm -f "${TMP_AUTH_PATH}"' EXIT

docker cp "${OPENCLAW_CONTAINER_NAME}:${OPENCLAW_STATE_AUTH_PATH}" "${TMP_AUTH_PATH}"
python3 -m json.tool "${TMP_AUTH_PATH}" >/dev/null

mkdir -p "$(dirname "${TARGET_AUTH_PATH}")"
install -m 600 "${TMP_AUTH_PATH}" "${TARGET_AUTH_PATH}"

echo "Synced OpenClaw auth profile to bootstrap: ${TARGET_AUTH_PATH}"
