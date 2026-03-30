#!/bin/bash
set -euo pipefail

CERT_DIR="$(dirname "$0")/../haproxy/certs"
mkdir -p "$CERT_DIR"

CERT_FILE="$CERT_DIR/rdp.pem"
if [ -f "$CERT_FILE" ]; then
    echo "Certificate already exists at $CERT_FILE"
    exit 0
fi

echo "Generating self-signed development certificate…"
openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$CERT_DIR/rdp.key" \
    -out "$CERT_DIR/rdp.crt" \
    -days 365 \
    -subj "/CN=rdpproxy-dev/O=RDPProxy/OU=Dev" \
    2>/dev/null

cat "$CERT_DIR/rdp.crt" "$CERT_DIR/rdp.key" > "$CERT_FILE"
echo "Certificate created: $CERT_FILE"
