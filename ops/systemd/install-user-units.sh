#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.config/systemd/user"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

mkdir -p "${TARGET_DIR}"

sed "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  "${SCRIPT_DIR}/denkeeper-compose.service" > "${TARGET_DIR}/denkeeper-compose.service"
sed "s|__PROJECT_ROOT__|${PROJECT_ROOT}|g" \
  "${SCRIPT_DIR}/denkeeper-healthcheck.service" > "${TARGET_DIR}/denkeeper-healthcheck.service"
cp "${SCRIPT_DIR}/denkeeper-healthcheck.timer" "${TARGET_DIR}/denkeeper-healthcheck.timer"

chmod +x "${PROJECT_ROOT}/ops/docker/healthcheck.sh"

systemctl --user daemon-reload
systemctl --user enable --now denkeeper-compose.service
systemctl --user enable --now denkeeper-healthcheck.timer

echo "Installed and enabled:"
echo "  - denkeeper-compose.service"
echo "  - denkeeper-healthcheck.timer"
echo
echo "For reboot-start without active login, run:"
echo "  sudo loginctl enable-linger \"${USER}\""
