FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y --no-install-recommends dumb-init ca-certificates git \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g openclaw@2026.3.13

WORKDIR /opt/denkeeper/plugins/expense-tracker
COPY plugins/expense-tracker/package.json plugins/expense-tracker/package-lock.json ./
RUN npm ci
COPY plugins/expense-tracker ./

COPY ops/docker/openclaw/openclaw.base.json /opt/denkeeper/openclaw.base.json
COPY ops/docker/openclaw/entrypoint.sh /usr/local/bin/denkeeper-openclaw-entrypoint
RUN chmod +x /usr/local/bin/denkeeper-openclaw-entrypoint

ENV OPENCLAW_STATE_DIR=/openclaw/state \
  OPENCLAW_CONFIG_PATH=/openclaw/state/openclaw.json \
  OPENCLAW_GATEWAY_PORT=1455 \
  DENKEEPER_WORKER_BASE_URL=http://denkeeper-expense-worker:8765 \
  DENKEEPER_DEFAULT_SCOPE=the-den \
  DENKEEPER_REQUEST_TIMEOUT_MS=5000 \
  OPENCLAW_ASSISTANT_NAME=Kyoto \
  OPENCLAW_PRIMARY_MODEL=openai-codex/gpt-5.4 \
  OPENCLAW_WHATSAPP_ENABLED=true \
  OPENCLAW_WHATSAPP_DM_POLICY=disabled \
  OPENCLAW_WHATSAPP_GROUP_POLICY=allowlist \
  OPENCLAW_WHATSAPP_GROUP_ALLOW_FROM_JSON=[] \
  OPENCLAW_WHATSAPP_GROUPS_JSON={}

VOLUME ["/openclaw/state"]
EXPOSE 1455

ENTRYPOINT ["dumb-init", "--", "/usr/local/bin/denkeeper-openclaw-entrypoint"]
