#!/bin/bash
set -euo pipefail

COMPOSE_FILE="/opt/rdpproxy/docker-compose.yml"
DEST="/opt/rdpproxy/deploy/haproxy/certs/rdp.pem"

# 1) Explicit argument, 2) DB public_host, 3) fail
if [ -n "${1:-}" ]; then
    DOMAIN="$1"
else
    DOMAIN="$(
        docker compose -f "${COMPOSE_FILE}" exec -T postgres \
            psql -U rdpproxy -d rdpproxy -At \
            -c "SELECT value->>'public_host' FROM portal_settings WHERE key='proxy'" 2>/dev/null
    )"
fi

if [ -z "${DOMAIN}" ]; then
    echo "ERROR: Could not determine domain. Pass it as argument or set proxy.public_host in admin panel." >&2
    exit 1
fi

LE_DIR="/etc/letsencrypt/live/${DOMAIN}"

if [ ! -f "${LE_DIR}/fullchain.pem" ] || [ ! -f "${LE_DIR}/privkey.pem" ]; then
    echo "ERROR: Let's Encrypt files not found in ${LE_DIR}" >&2
    exit 1
fi

cat "${LE_DIR}/fullchain.pem" "${LE_DIR}/privkey.pem" > "${DEST}"

docker compose -f "${COMPOSE_FILE}" kill -s HUP haproxy 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" restart rdp-relay 2>/dev/null || true

echo "[$(date)] Certificate renewed and services reloaded for ${DOMAIN}"
