#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:-/opt/rdpproxy-v2/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/rdpproxy_v2_${TIMESTAMP}.sql.gz"
KEEP_DAYS="${KEEP_DAYS:-7}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting PostgreSQL backup…"
docker compose -f /opt/rdpproxy-v2/docker-compose.yml exec -T postgres \
    pg_dump -U rdpproxy -d rdpproxy_v2 --clean --if-exists | gzip > "$BACKUP_FILE"

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "[$(date)] Backup complete: $BACKUP_FILE ($SIZE)"

DELETED=$(find "$BACKUP_DIR" -name "rdpproxy_v2_*.sql.gz" -mtime +"$KEEP_DAYS" -delete -print | wc -l)
if [ "$DELETED" -gt 0 ]; then
    echo "[$(date)] Cleaned up $DELETED old backup(s)"
fi
