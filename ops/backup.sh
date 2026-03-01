#!/usr/bin/env bash
###############################################################################
# /ops/backup.sh – Amarktai Network backup script
#
# Backs up:
#   1. /etc/amarktai/backend.env  → timestamped copy in /var/backups/amarktai/
#   2. MongoDB database           → mongodump to /var/backups/amarktai/db/
#   3. Frontend web root          → tar.gz snapshot
#
# USAGE
#   sudo bash ops/backup.sh [--label custom-label]
#
# RESTORE
#   sudo bash ops/restore.sh <backup-dir>
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Config ────────────────────────────────────────────────────────────────────
ENV_FILE="${ENV_FILE:-/etc/amarktai/backend.env}"
FRONTEND_WEBROOT="${FRONTEND_WEBROOT:-/var/www/amarktai}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/amarktai}"
DB_NAME="${DB_NAME:-amarktai_trading}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LABEL="${1:-}"
for arg in "$@"; do [[ "$arg" == "--label" ]] && shift && LABEL="$1"; done
BACKUP_DIR="$BACKUP_ROOT/${TIMESTAMP}${LABEL:+_$LABEL}"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
info() { echo -e "${CYAN}→ $*${NC}"; }

echo ""
echo "══════════════════════════════════════════"
echo " 💾  AMARKTAI NETWORK – BACKUP"
echo "══════════════════════════════════════════"
echo " Destination: $BACKUP_DIR"
echo "══════════════════════════════════════════"
echo ""

# ── Create backup dir ─────────────────────────────────────────────────────────
sudo mkdir -p "$BACKUP_DIR"

# ── 1. Env file ───────────────────────────────────────────────────────────────
info "Backing up env file..."
if [[ -f "$ENV_FILE" ]]; then
  sudo cp "$ENV_FILE" "$BACKUP_DIR/backend.env"
  sudo chmod 600 "$BACKUP_DIR/backend.env"
  ok "Env file backed up"
else
  warn "Env file not found: $ENV_FILE"
fi

# ── 2. MongoDB ────────────────────────────────────────────────────────────────
info "Dumping MongoDB ($DB_NAME)..."
if command -v mongodump &>/dev/null; then
  sudo mongodump --db "$DB_NAME" --out "$BACKUP_DIR/db" --quiet 2>/dev/null && ok "MongoDB dumped" || warn "mongodump failed"
else
  warn "mongodump not found – skipping database backup"
fi

# ── 3. Frontend web root ──────────────────────────────────────────────────────
info "Archiving frontend web root..."
if [[ -d "$FRONTEND_WEBROOT" ]]; then
  sudo tar -czf "$BACKUP_DIR/frontend.tar.gz" -C "$(dirname "$FRONTEND_WEBROOT")" "$(basename "$FRONTEND_WEBROOT")" 2>/dev/null && ok "Frontend archived" || warn "Frontend archive failed"
else
  warn "Web root not found: $FRONTEND_WEBROOT"
fi

# ── 4. Write manifest ─────────────────────────────────────────────────────────
sudo tee "$BACKUP_DIR/MANIFEST.txt" > /dev/null <<EOF
AMARKTAI BACKUP MANIFEST
========================
Timestamp:    $TIMESTAMP
Backup dir:   $BACKUP_DIR
Env file:     $ENV_FILE
Frontend:     $FRONTEND_WEBROOT
Database:     $DB_NAME
Git SHA:      $(git -C "$(dirname "$SCRIPT_DIR")" rev-parse --short HEAD 2>/dev/null || echo unknown)
EOF

echo ""
echo "══════════════════════════════════════════"
echo -e "${GREEN} ✅  BACKUP COMPLETE${NC}"
echo " Location: $BACKUP_DIR"
echo "══════════════════════════════════════════"
echo ""
echo " Restore with:"
echo "   sudo bash ops/restore.sh $BACKUP_DIR"
echo ""
