#!/usr/bin/env bash
set -euo pipefail

SOURCE_STATE_DIR="${1:-$HOME/.openclaw}"
TARGET_VOLUME="denkeeper_openclaw_state"

if [[ ! -d "${SOURCE_STATE_DIR}" ]]; then
  echo "Source state directory not found: ${SOURCE_STATE_DIR}"
  exit 1
fi

docker volume create "${TARGET_VOLUME}" >/dev/null

docker run --rm \
  -v "${SOURCE_STATE_DIR}:/from:ro" \
  -v "${TARGET_VOLUME}:/to" \
  alpine:3.20 \
  sh -c 'mkdir -p /to && cp -a /from/. /to/'

echo "Migrated OpenClaw state from ${SOURCE_STATE_DIR} -> docker volume ${TARGET_VOLUME}."
