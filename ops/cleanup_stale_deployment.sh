#!/usr/bin/env bash
###############################################################################
# ops/cleanup_stale_deployment.sh – Amarktai Crypto Safe Stale Deployment Cleanup
#
# USAGE
#   sudo bash ops/cleanup_stale_deployment.sh [--dry-run]
#
# This script is CAUTIOUS and VERBOSE. It will:
#   • Disable and remove stale amarktai.service (old unit name)
#   • Remove stale nginx symlinks: default, amarktai-spa, amarktai-websocket
#   • Remove old venv at /var/amarktai/venv  (NOT the canonical one)
#   • Remove old duplicate webroots: /var/www/amarktai, /opt/amarktai (only
#     if they are confirmed non-canonical and confirmed not nginx roots)
#
# WHAT IT WILL NOT TOUCH:
#   • /var/amarktai/app/Amarktai-Crypto (canonical app root)
#   • /var/amarktai/app/Amarktai-Crypto/backend/.venv (canonical venv)
#   • /etc/amarktai/amarktai.env (secrets file)
#   • /etc/nginx/sites-available/amarktai (canonical nginx config)
#   • /etc/nginx/sites-enabled/amarktai (canonical nginx symlink)
#   • /etc/systemd/system/amarktai-api.service (canonical systemd unit)
#   • /var/log/amarktai (log files)
###############################################################################
set -uo pipefail

DRY_RUN=false
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
  esac
done

# ── Colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'
BOLD='\033[1m'; NC='\033[0m'
ok()    { echo -e "${GREEN}  ✓ $*${NC}"; }
warn()  { echo -e "${YELLOW}  ⚠ $*${NC}"; }
err()   { echo -e "${RED}  ✗ $*${NC}"; }
info()  { echo -e "${CYAN}  → $*${NC}"; }
skip()  { echo -e "  - SKIP: $*"; }
dryrun(){ echo -e "${YELLOW}  [DRY-RUN] would: $*${NC}"; }

act() {
  # act <description> <command...>
  local desc="$1"; shift
  if [[ "$DRY_RUN" == "true" ]]; then
    dryrun "$desc"
  else
    eval "$@" && ok "$desc" || warn "Failed: $desc"
  fi
}

echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}${CYAN}  AMARKTAI CRYPTO – STALE DEPLOYMENT CLEANUP${NC}"
if [[ "$DRY_RUN" == "true" ]]; then
  echo -e "${BOLD}${YELLOW}  MODE: DRY RUN (no changes will be made)${NC}"
fi
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Canonical (protected) paths:"
echo "    App:     /var/amarktai/app/Amarktai-Crypto"
echo "    Venv:    /var/amarktai/app/Amarktai-Crypto/backend/.venv"
echo "    Env:     /etc/amarktai/amarktai.env"
echo "    Nginx:   /etc/nginx/sites-available/amarktai"
echo "    Service: /etc/systemd/system/amarktai-api.service"
echo ""

###############################################################################
echo -e "${BOLD}[ 1. Stale systemd services ]${NC}"
###############################################################################

# amarktai.service (old unit – was the pre-v2 name)
for stale_unit in amarktai.service amarktai-api-old.service; do
  unit_path="/etc/systemd/system/$stale_unit"
  if systemctl list-unit-files "$stale_unit" 2>/dev/null | grep -q "$stale_unit"; then
    warn "Found stale systemd unit: $stale_unit"
    if systemctl is-active "$stale_unit" &>/dev/null; then
      act "Stop $stale_unit" "systemctl stop '$stale_unit'"
    fi
    if systemctl is-enabled "$stale_unit" &>/dev/null; then
      act "Disable $stale_unit" "systemctl disable '$stale_unit'"
    fi
    if [[ -f "$unit_path" ]]; then
      act "Remove $unit_path" "rm -f '$unit_path'"
    fi
  else
    ok "No stale unit: $stale_unit"
  fi
done

act "Reload systemd daemon" "systemctl daemon-reload"

# Also disable .disabled files left from previous cleanup
for disabled in /etc/systemd/system/amarktai.service.disabled; do
  if [[ -f "$disabled" ]]; then
    warn "Removing leftover disabled unit: $disabled"
    act "Remove $disabled" "rm -f '$disabled'"
  fi
done

###############################################################################
echo ""
echo -e "${BOLD}[ 2. Stale nginx symlinks ]${NC}"
###############################################################################

for stale_link in default amarktai-spa amarktai-websocket; do
  link="/etc/nginx/sites-enabled/$stale_link"
  if [[ -L "$link" || -e "$link" ]]; then
    warn "Stale nginx site enabled: $link"
    act "Remove $link" "rm -f '$link'"
  else
    ok "No stale nginx site: $link"
  fi
done

# Test and reload nginx if we changed anything
if nginx -t 2>/dev/null; then
  act "Reload nginx" "systemctl reload nginx"
else
  warn "Nginx config test failed – not reloading nginx. Check: sudo nginx -t"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ 3. Old venv at /var/amarktai/venv ]${NC}"
###############################################################################

OLD_VENV=/var/amarktai/venv
if [[ -d "$OLD_VENV" ]]; then
  warn "Found old venv: $OLD_VENV (NOT the canonical one)"
  info "Canonical venv is: /var/amarktai/app/Amarktai-Crypto/backend/.venv"
  # Safety: make sure uvicorn is not running from this path
  if pgrep -a uvicorn 2>/dev/null | grep -q "$OLD_VENV"; then
    err "uvicorn is currently running from $OLD_VENV – WILL NOT DELETE"
    err "Fix: run sudo bash ops/redeploy_production.sh first"
  else
    act "Remove old venv $OLD_VENV" "rm -rf '$OLD_VENV'"
  fi
else
  ok "No old venv at $OLD_VENV"
fi

###############################################################################
echo ""
echo -e "${BOLD}[ 4. Old webroots ]${NC}"
###############################################################################

CANONICAL_NGINX_ROOT=/var/amarktai/app/Amarktai-Crypto/frontend/build
STALE_ROOTS=(/var/www/amarktai /opt/amarktai)

for root in "${STALE_ROOTS[@]}"; do
  if [[ ! -d "$root" ]]; then
    ok "No stale webroot: $root"
    continue
  fi

  warn "Found potential stale webroot: $root"

  # Safety: confirm nginx is NOT serving from this path
  NGINX_IS_ROOT=false
  for conf in /etc/nginx/sites-enabled/*; do
    if [[ -f "$conf" ]] && grep -qF "$root" "$conf" 2>/dev/null; then
      NGINX_IS_ROOT=true
      err "Nginx config $conf references $root – will NOT delete"
      break
    fi
  done

  if [[ "$NGINX_IS_ROOT" == "true" ]]; then
    warn "Skipping $root (nginx is serving from it)"
    continue
  fi

  # Confirm it is not the canonical path
  if [[ "$root" == "$CANONICAL_NGINX_ROOT" ]]; then
    skip "$root (this IS the canonical nginx root)"
    continue
  fi

  act "Remove stale webroot $root" "rm -rf '$root'"
done

###############################################################################
echo ""
echo -e "${BOLD}[ 5. Old /var/amarktai/app/backend path (non-Amarktai-Crypto) ]${NC}"
###############################################################################

# If the repo was previously cloned directly into /var/amarktai/app (without
# the Amarktai-Crypto subdirectory), there may be a stale backend directory
OLD_FLAT_BACKEND=/var/amarktai/app/backend
OLD_FLAT_FRONTEND=/var/amarktai/app/frontend

for stale_dir in "$OLD_FLAT_BACKEND" "$OLD_FLAT_FRONTEND"; do
  if [[ -d "$stale_dir" ]]; then
    # Make sure it's not inside the canonical app root
    CANONICAL_REAL=$(realpath /var/amarktai/app/Amarktai-Crypto 2>/dev/null || echo "/var/amarktai/app/Amarktai-Crypto")
    STALE_REAL=$(realpath "$stale_dir" 2>/dev/null || echo "$stale_dir")
    if [[ "$STALE_REAL" == "$CANONICAL_REAL"* ]]; then
      skip "$stale_dir is inside canonical root"
      continue
    fi
    warn "Found stale directory: $stale_dir"
    # Safety: make sure uvicorn is not running from here
    if pgrep -a uvicorn 2>/dev/null | grep -q "$stale_dir"; then
      err "uvicorn running from $stale_dir – will NOT delete. Run redeploy first."
    else
      act "Remove stale dir $stale_dir" "rm -rf '$stale_dir'"
    fi
  else
    ok "No stale dir: $stale_dir"
  fi
done

###############################################################################
echo ""
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
if [[ "$DRY_RUN" == "true" ]]; then
  echo -e "${BOLD}${YELLOW}  DRY RUN COMPLETE – no changes were made${NC}"
  echo "  Re-run without --dry-run to apply changes"
else
  echo -e "${BOLD}${GREEN}  ✅  CLEANUP COMPLETE${NC}"
  echo ""
  echo "  Run verify: sudo bash ops/verify_production.sh"
fi
echo -e "${BOLD}${CYAN}══════════════════════════════════════════════════════════════${NC}"
echo ""
