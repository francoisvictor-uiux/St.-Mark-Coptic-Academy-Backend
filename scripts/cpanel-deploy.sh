#!/bin/bash
#
# Near-automatic backend deploy for cPanel (no SSH/webhook needed).
#
# Run from cron every few minutes. It fetches GitHub `main`; if there are new
# commits it fast-forwards the local clone and deploys exactly what .cpanel.yml
# does — sync code into the live app root, install deps, migrate, collectstatic,
# and restart Passenger. It exits early (cheap) when nothing has changed.
#
# --- One-time setup in cPanel ---
#   1. Create the repo via Git Version Control (clones GitHub `main`).
#   2. cPanel → Cron Jobs → add (adjust the path to your actual clone dir):
#        */5 * * * * /home/smca/repositories/backend/scripts/cpanel-deploy.sh >> /home/smca/deploy-backend.log 2>&1
#   3. First run: chmod +x this file (the cPanel clone preserves the git +x bit).
#
# Safe to run repeatedly; it only acts when origin/main moves.
set -euo pipefail

# Resolve the repo root as this script's parent-of-parent, so it works wherever
# cPanel cloned the repository.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPROOT=/home/smca/api.smcacademy.org
VBIN=/home/smca/virtualenv/api.smcacademy.org/3.11/bin

cd "$REPO"
git fetch --quiet origin main

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/main)"
if [ "$LOCAL" = "$REMOTE" ]; then
  exit 0   # already up to date — nothing to deploy
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') deploying ${LOCAL:0:7} -> ${REMOTE:0:7} ==="
git reset --hard origin/main

# 1) Sync code into the live app root (overlay; preserve server-only files).
/usr/bin/rsync -a \
  --exclude='.env' --exclude='.git/' --exclude='.htaccess' \
  --exclude='media/' --exclude='staticfiles/' --exclude='tmp/' \
  --exclude='db.sqlite3' --exclude='__pycache__/' --exclude='.venv/' \
  "$REPO/" "$APPROOT/"

# 2) Deps, 3) migrate, 4) static, 5) restart — same as .cpanel.yml.
"$VBIN/pip" install -r "$APPROOT/requirements.txt"
cd "$APPROOT" && DJANGO_ENV=prod "$VBIN/python" manage.py migrate --noinput
cd "$APPROOT" && DJANGO_ENV=prod "$VBIN/python" manage.py collectstatic --noinput
mkdir -p "$APPROOT/tmp" && touch "$APPROOT/tmp/restart.txt"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') deploy complete ==="
