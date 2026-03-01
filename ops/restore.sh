#!/usr/bin/env bash
###############################################################################
# /ops/restore.sh – Amarktai Network restore script
#
# Restores from a backup created by ops/backup.sh:
#   1. /etc/amarktai/backend.env
#   2. MongoDB database (mongorestore)
#   3. Frontend web root
#
# USAGE
#   sudo bash ops/restore.sh <backup-dir>
#   sudo bash ops/restore.sh /var/backups/amarktai/20241215_143022
###############################################################################
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
err()  { echo -e "${RED}✗ $*${NC}"; }
info() { echo -e "${CYAN}→ $*${NC}"; }

BACKUP_DIR="${1:-}"
if [[ -z "$BACKUP_DIR" ]]; then
  err "Usage: $0 <backup-dir>"
  echo ""
  echo "  Available backups:"
  ls /var/backups/amarktai/ 2>/dev/null | while read d; do echo "    /var/backups/amarktai/$d"; done
  exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  err "Backup directory not found: $BACKUP_DIR"
  exit 1
fi

# ── Config ────────────────────────────────────────────────────────────────────
ENV_FILE="${ENV_FILE:-/etc/amarktai/backend.env}"
FRONTEND_WEBROOT="${FRONTEND_WEBROOT:-/var/www/amarktai}"
DB_NAME="${DB_NAME:-amarktai_trading}"
BACKEND_SERVICE="${BACKEND_SERVICE:-amarktai-api}"

echo ""
echo "══════════════════════════════════════════"
echo " 🔄  AMARKTAI NETWORK – RESTORE"
echo "══════════════════════════════════════════"
echo " Source: $BACKUP_DIR"
echo "══════════════════════════════════════════"
echo ""

# Show manifest if available
if [[ -f "$BACKUP_DIR/MANIFEST.txt" ]]; then
  cat "$BACKUP_DIR/MANIFEST.txt"
  echo ""
fi

read -r -p "Continue restore? This will overwrite current data. [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { warn "Restore cancelled."; exit 0; }

# ── 1. Stop service ───────────────────────────────────────────────────────────
info "Stopping $BACKEND_SERVICE..."
sudo systemctl stop "$BACKEND_SERVICE" 2>/dev/null || warn "Service not running"

# ── 2. Restore env file ───────────────────────────────────────────────────────
if [[ -f "$BACKUP_DIR/backend.env" ]]; then
  info "Restoring env file..."
  sudo mkdir -p "$(dirname "$ENV_FILE")"
  sudo cp "$BACKUP_DIR/backend.env" "$ENV_FILE"
  sudo chmod 600 "$ENV_FILE"
  ok "Env file restored: $ENV_FILE"
else
  warn "No env file in backup – skipping"
fi

# ── 3. Restore MongoDB ────────────────────────────────────────────────────────
if [[ -d "$BACKUP_DIR/db/$DB_NAME" ]]; then
  info "Restoring MongoDB ($DB_NAME)..."
  if command -v mongorestore &>/dev/null; then
    sudo mongorestore --db "$DB_NAME" --drop "$BACKUP_DIR/db/$DB_NAME" --quiet 2>/dev/null && ok "MongoDB restored" || warn "mongorestore failed"
  else
    warn "mongorestore not found – skipping database restore"
  fi
else
  warn "No database dump found in backup"
fi

# ── 4. Restore frontend ───────────────────────────────────────────────────────
if [[ -f "$BACKUP_DIR/frontend.tar.gz" ]]; then
  info "Restoring frontend..."
  PARENT="$(dirname "$FRONTEND_WEBROOT")"
  sudo tar -xzf "$BACKUP_DIR/frontend.tar.gz" -C "$PARENT" 2>/dev/null && ok "Frontend restored" || warn "Frontend restore failed"
  sudo chown -R www-data:www-data "$FRONTEND_WEBROOT"
else
  warn "No frontend archive in backup"
fi

# ── 5. Restart service ────────────────────────────────────────────────────────
info "Starting $BACKEND_SERVICE..."
sudo systemctl start "$BACKEND_SERVICE"
sleep 5
sudo systemctl is-active "$BACKEND_SERVICE" &>/dev/null && ok "Service started" || warn "Service may not have started – check: sudo journalctl -u $BACKEND_SERVICE -n 20"

# Reload nginx
sudo nginx -t 2>/dev/null && sudo systemctl reload nginx && ok "Nginx reloaded" || warn "Nginx reload skipped"

echo ""
echo "══════════════════════════════════════════"
echo -e "${GREEN} ✅  RESTORE COMPLETE${NC}"
echo "══════════════════════════════════════════"
echo ""
