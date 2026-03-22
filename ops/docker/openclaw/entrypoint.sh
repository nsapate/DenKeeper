#!/usr/bin/env bash
set -euo pipefail

: "${OPENCLAW_STATE_DIR:=/openclaw/state}"
: "${OPENCLAW_CONFIG_PATH:=${OPENCLAW_STATE_DIR}/openclaw.json}"
: "${OPENCLAW_GATEWAY_PORT:=1455}"
: "${OPENCLAW_BOOTSTRAP_DIR:=/opt/denkeeper/bootstrap}"
: "${DENKEEPER_WORKER_BASE_URL:=http://denkeeper-expense-worker:8765}"
: "${DENKEEPER_DEFAULT_SCOPE:=the-den}"
: "${DENKEEPER_REQUEST_TIMEOUT_MS:=5000}"
: "${OPENCLAW_ASSISTANT_NAME:=Kyoto}"
: "${OPENCLAW_PRIMARY_MODEL:=openai-codex/gpt-5.4}"
: "${OPENCLAW_WHATSAPP_ENABLED:=true}"
: "${OPENCLAW_WHATSAPP_DM_POLICY:=disabled}"
: "${OPENCLAW_WHATSAPP_GROUP_POLICY:=allowlist}"
: "${OPENCLAW_WHATSAPP_GROUP_ALLOW_FROM_JSON:=[]}"
: "${OPENCLAW_WHATSAPP_GROUPS_JSON:={}}"
: "${OPENCLAW_GROUP_MENTION_PATTERNS_JSON:=[]}"

if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]]; then
  echo "OPENCLAW_GATEWAY_TOKEN is required."
  exit 1
fi

if [[ -z "${DENKEEPER_WORKER_TOKEN:-}" ]]; then
  echo "DENKEEPER_WORKER_TOKEN is required."
  exit 1
fi

mkdir -p "${OPENCLAW_STATE_DIR}"

# One-time bootstrap for model auth profiles. This keeps container rebuild/recreate flows
# deterministic without requiring manual in-container copy operations.
TARGET_AUTH_PROFILES="${OPENCLAW_STATE_DIR}/agents/main/agent/auth-profiles.json"
if [[ ! -f "${TARGET_AUTH_PROFILES}" ]]; then
  for SOURCE_AUTH_PROFILES in \
    "${OPENCLAW_BOOTSTRAP_DIR}/agents/main/agent/auth-profiles.json" \
    "${OPENCLAW_BOOTSTRAP_DIR}/auth-profiles.json"; do
    if [[ -s "${SOURCE_AUTH_PROFILES}" ]]; then
      mkdir -p "$(dirname "${TARGET_AUTH_PROFILES}")"
      cp "${SOURCE_AUTH_PROFILES}" "${TARGET_AUTH_PROFILES}"
      chmod 600 "${TARGET_AUTH_PROFILES}" || true
      echo "Bootstrapped auth-profiles.json from ${SOURCE_AUTH_PROFILES}"
      break
    fi
  done
fi

node <<'NODE'
const fs = require("fs");
const path = require("path");

const configPath = process.env.OPENCLAW_CONFIG_PATH;
const basePath = "/opt/denkeeper/openclaw.base.json";

const parseJsonEnv = (name, fallback) => {
  const raw = process.env[name];
  if (raw === undefined || raw === "") return fallback;
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw new Error(`Invalid JSON in ${name}: ${error.message}`);
  }
};

const readJson = (target) => JSON.parse(fs.readFileSync(target, "utf8"));
const cfg = fs.existsSync(configPath) ? readJson(configPath) : readJson(basePath);

cfg.ui = cfg.ui ?? {};
cfg.ui.assistant = cfg.ui.assistant ?? {};
cfg.ui.assistant.name = process.env.OPENCLAW_ASSISTANT_NAME;

cfg.agents = cfg.agents ?? {};
cfg.agents.defaults = cfg.agents.defaults ?? {};
cfg.agents.defaults.model = cfg.agents.defaults.model ?? {};
cfg.agents.defaults.model.primary = process.env.OPENCLAW_PRIMARY_MODEL;
cfg.agents.defaults.compaction = cfg.agents.defaults.compaction ?? { mode: "safeguard" };

cfg.messages = cfg.messages ?? {};
cfg.messages.ackReactionScope = "group-mentions";
cfg.messages.groupChat = cfg.messages.groupChat ?? {};
const configuredMentionPatterns = parseJsonEnv("OPENCLAW_GROUP_MENTION_PATTERNS_JSON", []);
if (Array.isArray(configuredMentionPatterns) && configuredMentionPatterns.length > 0) {
  cfg.messages.groupChat.mentionPatterns = configuredMentionPatterns;
} else if (
  !Array.isArray(cfg.messages.groupChat.mentionPatterns) ||
  cfg.messages.groupChat.mentionPatterns.length === 0
) {
  const assistantName = String(process.env.OPENCLAW_ASSISTANT_NAME ?? "").trim();
  if (assistantName.length > 0) {
    const escapedAssistantName = assistantName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    // Enable "Kyoto ..." style invocation in groups without requiring native @-mention metadata.
    cfg.messages.groupChat.mentionPatterns = [`@?${escapedAssistantName}`];
  }
}

cfg.gateway = cfg.gateway ?? {};
cfg.gateway.mode = "local";
cfg.gateway.bind = "lan";
cfg.gateway.auth = cfg.gateway.auth ?? {};
cfg.gateway.auth.mode = "token";
cfg.gateway.auth.token = process.env.OPENCLAW_GATEWAY_TOKEN;

cfg.channels = cfg.channels ?? {};
cfg.channels.whatsapp = cfg.channels.whatsapp ?? {};
cfg.channels.whatsapp.enabled = process.env.OPENCLAW_WHATSAPP_ENABLED === "true";
cfg.channels.whatsapp.dmPolicy = process.env.OPENCLAW_WHATSAPP_DM_POLICY;
cfg.channels.whatsapp.groupPolicy = process.env.OPENCLAW_WHATSAPP_GROUP_POLICY;
cfg.channels.whatsapp.groupAllowFrom = parseJsonEnv("OPENCLAW_WHATSAPP_GROUP_ALLOW_FROM_JSON", []);
cfg.channels.whatsapp.groups = parseJsonEnv("OPENCLAW_WHATSAPP_GROUPS_JSON", {});
cfg.channels.whatsapp.debounceMs = cfg.channels.whatsapp.debounceMs ?? 0;
cfg.channels.whatsapp.mediaMaxMb = cfg.channels.whatsapp.mediaMaxMb ?? 50;

cfg.plugins = cfg.plugins ?? {};
cfg.plugins.allow = ["expense-tracker", "whatsapp"];
cfg.plugins.load = cfg.plugins.load ?? {};
cfg.plugins.load.paths = ["/opt/denkeeper/plugins/expense-tracker"];
cfg.plugins.entries = cfg.plugins.entries ?? {};
cfg.plugins.entries["expense-tracker"] = {
  enabled: true,
  config: {
    workerBaseUrl: process.env.DENKEEPER_WORKER_BASE_URL,
    apiToken: process.env.DENKEEPER_WORKER_TOKEN,
    defaultScope: process.env.DENKEEPER_DEFAULT_SCOPE,
    requestTimeoutMs: Number(process.env.DENKEEPER_REQUEST_TIMEOUT_MS ?? "5000"),
  },
};
cfg.plugins.entries.whatsapp = { enabled: true };

fs.mkdirSync(path.dirname(configPath), { recursive: true });
fs.writeFileSync(configPath, JSON.stringify(cfg, null, 2));
NODE

exec openclaw gateway run \
  --allow-unconfigured \
  --bind lan \
  --auth token \
  --token "${OPENCLAW_GATEWAY_TOKEN}" \
  --port "${OPENCLAW_GATEWAY_PORT}"
