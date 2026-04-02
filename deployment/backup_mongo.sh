#!/usr/bin/env bash
# ============================================================================
# Amarktai MongoDB Backup Script
# ============================================================================
# Creates a compressed mongodump of the trading database and retains the
# last N backups.  Safe to run manually or from cron.
#
# Cron example (daily at 03:00):
#   0 3 * * * /var/amarktai/app/Amarktai-Crypto/deployment/backup_mongo.sh >> /var/log/amarktai/backup.log 2>&1
#
# Usage:
#   ./deployment/backup_mongo.sh [--db DB_NAME] [--keep N] [--dest DIR]
# ============================================================================
set -euo pipefail

# ── Defaults (override via env or flags) ─────────────────────────────────────
MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"
DB_NAME="${DB_NAME:-amarktai_trading}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/amarktai}"
KEEP_DAYS="${KEEP_DAYS:-14}"

# ── Parse optional flags ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)    DB_NAME="$2"; shift 2 ;;
        --keep)  KEEP_DAYS="$2"; shift 2 ;;
        --dest)  BACKUP_DIR="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_PATH="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}"
ARCHIVE="${BACKUP_PATH}.tar.gz"

# ── Ensure backup directory exists ───────────────────────────────────────────
mkdir -p "${BACKUP_DIR}"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting MongoDB backup: db=${DB_NAME} → ${ARCHIVE}"

# ── Run mongodump ─────────────────────────────────────────────────────────────
if ! command -v mongodump &>/dev/null; then
    echo "ERROR: mongodump not found. Install mongodb-database-tools."
    exit 1
fi

mongodump \
    --uri="${MONGO_URL}" \
    --db="${DB_NAME}" \
    --out="${BACKUP_PATH}" \
    --quiet

# ── Compress ──────────────────────────────────────────────────────────────────
tar -czf "${ARCHIVE}" -C "${BACKUP_DIR}" "$(basename "${BACKUP_PATH}")"
rm -rf "${BACKUP_PATH}"

SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup complete: ${ARCHIVE} (${SIZE})"

# ── Prune old backups ─────────────────────────────────────────────────────────
find "${BACKUP_DIR}" -name "${DB_NAME}_*.tar.gz" -mtime "+${KEEP_DAYS}" -delete
REMAINING=$(find "${BACKUP_DIR}" -name "${DB_NAME}_*.tar.gz" | wc -l)
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup pruning done. ${REMAINING} backup(s) retained."
