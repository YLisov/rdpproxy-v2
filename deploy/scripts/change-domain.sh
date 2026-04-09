#!/bin/bash
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-/opt/rdpproxy/docker-compose.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-rdpproxy}"
DEST="${CERT_DEST:-/opt/rdpproxy/deploy/haproxy/certs/rdp.pem}"
EMAIL="${CERTBOT_EMAIL:-}"

DOMAIN="${1:-}"
if [ -z "${DOMAIN}" ]; then
    echo "Usage: $0 <domain>" >&2
    exit 1
fi

echo "[$(date)] Requesting certificate for ${DOMAIN}..."

CERTBOT_ARGS=(
    certonly --standalone --non-interactive --agree-tos
    -d "${DOMAIN}"
    --preferred-challenges http
)
if [ -n "${EMAIL}" ]; then
    CERTBOT_ARGS+=(--email "${EMAIL}")
else
    CERTBOT_ARGS+=(--register-unsafely-without-email)
fi

certbot "${CERTBOT_ARGS[@]}" 2>&1

LE_DIR="/etc/letsencrypt/live/${DOMAIN}"
if [ ! -f "${LE_DIR}/fullchain.pem" ] || [ ! -f "${LE_DIR}/privkey.pem" ]; then
    echo "ERROR: Certificate files not found in ${LE_DIR}" >&2
    exit 1
fi

cat "${LE_DIR}/fullchain.pem" "${LE_DIR}/privkey.pem" > "${DEST}"

docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" kill -s HUP haproxy 2>/dev/null || true
docker compose -f "${COMPOSE_FILE}" -p "${COMPOSE_PROJECT}" restart rdp-relay 2>/dev/null || true

echo "[$(date)] Certificate issued and services reloaded for ${DOMAIN}"
