#!/bin/bash
set -euo pipefail

DOMAIN="rdp.lisov.pro"
LE_DIR="/etc/letsencrypt/live/${DOMAIN}"
DEST="/opt/rdpproxy-v2/deploy/haproxy/certs/rdp.pem"

cat "${LE_DIR}/fullchain.pem" "${LE_DIR}/privkey.pem" > "${DEST}"
docker compose -f /opt/rdpproxy-v2/docker-compose.yml kill -s HUP haproxy 2>/dev/null || true
echo "[$(date)] Certificate renewed for ${DOMAIN}"
