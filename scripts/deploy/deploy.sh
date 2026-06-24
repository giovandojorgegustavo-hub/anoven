#!/bin/bash
# Anoven atomic deploy with verify + automatic rollback
# M4 of the bitacora-port course (2026-06-23)
#
# Usage:
#   sudo ./scripts/deploy/deploy.sh           # full deploy
#   sudo ./scripts/deploy/deploy.sh --dry-run # plan only, no changes
#
# Steps:
#   1) Pre-checks (branch=main, clean tree)
#   2) Capture rollback commit
#   3) git pull (fast-forward only)
#   4) Backend deps (if requirements.txt changed)
#   5) Frontend deps (if package.json changed)
#   6) Frontend build (if frontend/ changed)
#   7) Migrations (apply pending; track in schema_migrations table)
#   8) Restart services
#   9) Wait + verify (services active + HTTPS + backend respond)
#  10) On verify fail: ROLLBACK + alert Telegram + exit !=0

set -euo pipefail

readonly REPO_DIR="/home/anoven/anoven-app"
readonly BACKEND_DIR="${REPO_DIR}/backend"
readonly FRONTEND_DIR="${REPO_DIR}/frontend"
readonly MIGRATIONS_DIR="${BACKEND_DIR}/migrations"
readonly ENV_FILE="${REPO_DIR}/.env.monitoring"
readonly LOG_FILE="/var/log/anoven-deploy.log"
readonly TS="$(date -Iseconds)"
readonly DRY_RUN="${1:-}"

# ---- Helpers ----

log() {
  echo "$TS [deploy] $*" | tee -a "$LOG_FILE"
}

run() {
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    log "DRY-RUN would execute: $*"
  else
    log "executing: $*"
    "$@"
  fi
}

telegram_alert() {
  local msg="$1"
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
      curl -s --max-time 10 -X POST \
        "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=${msg}" > /dev/null 2>&1 || true
    fi
  fi
}

rollback() {
  local prev_commit="$1"
  local reason="$2"
  log "ROLLBACK initiated: $reason"
  log "Resetting to commit $prev_commit"
  sudo -u anoven git -C "$REPO_DIR" reset --hard "$prev_commit"
  log "Restarting services"
  systemctl restart anoven-app-backend.service anoven-app-frontend.service || true
  telegram_alert "DEPLOY ROLLBACK on $(hostname) at $TS — reason: $reason. Rolled back to $prev_commit. Services restarted."
  log "Rollback complete"
}

# ---- 1) Pre-checks ----

log "==== Deploy started ===="
cd "$REPO_DIR"

current_branch=$(sudo -u anoven git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD)
if [[ "$current_branch" != "main" ]]; then
  log "FATAL: branch is '$current_branch', expected 'main'"
  exit 2
fi
log "branch=main OK"

if [[ -n "$(sudo -u anoven git -C "$REPO_DIR" status --porcelain)" ]]; then
  log "FATAL: working tree dirty. Commit or stash before deploy."
  sudo -u anoven git -C "$REPO_DIR" status --short
  exit 2
fi
log "working tree clean OK"

# ---- 2) Capture rollback commit ----

ROLLBACK_COMMIT=$(sudo -u anoven git -C "$REPO_DIR" rev-parse HEAD)
log "current HEAD (rollback target if needed): $ROLLBACK_COMMIT"

# ---- 3) Git pull (ff-only) ----

PRE_PULL_COMMIT="$ROLLBACK_COMMIT"
run sudo -u anoven git -C "$REPO_DIR" fetch origin main
NEW_COMMIT=$(sudo -u anoven git -C "$REPO_DIR" rev-parse origin/main)
if [[ "$PRE_PULL_COMMIT" == "$NEW_COMMIT" ]]; then
  log "Already up to date with origin/main. Nothing to deploy."
  exit 0
fi
log "new commit available: $NEW_COMMIT"

# Check what files changed (BEFORE pulling, to plan steps)
CHANGED_FILES=$(sudo -u anoven git -C "$REPO_DIR" diff --name-only "$PRE_PULL_COMMIT" "$NEW_COMMIT")
log "changed files:"
echo "$CHANGED_FILES" | sed 's/^/  /' | tee -a "$LOG_FILE"

run sudo -u anoven git -C "$REPO_DIR" merge --ff-only origin/main

# ---- 4) Backend deps ----

if echo "$CHANGED_FILES" | grep -qE "^backend/requirements.*\.txt$"; then
  if [[ -f "${BACKEND_DIR}/requirements.txt" ]]; then
    log "requirements.txt changed → pip install"
    run sudo -u anoven "${BACKEND_DIR}/.venv/bin/pip" install -r "${BACKEND_DIR}/requirements.txt"
  fi
else
  log "no backend deps change"
fi

# ---- 5) Frontend deps ----

if echo "$CHANGED_FILES" | grep -qE "^frontend/package(-lock)?\.json$"; then
  log "package.json changed → npm ci"
  cd "$FRONTEND_DIR"
  run sudo -u anoven npm ci
  cd "$REPO_DIR"
else
  log "no frontend deps change"
fi

# ---- 6) Frontend build ----

if echo "$CHANGED_FILES" | grep -qE "^frontend/"; then
  log "frontend/ changed → npm run build"
  cd "$FRONTEND_DIR"
  run sudo -u anoven npm run build
  cd "$REPO_DIR"
else
  log "no frontend code change"
fi

# ---- 7) Migrations ----

# Ensure schema_migrations table exists in anoven_app_dev
if [[ "$DRY_RUN" != "--dry-run" ]]; then
  sudo -u postgres psql -d anoven_app_dev -v ON_ERROR_STOP=1 -c "
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version VARCHAR(255) PRIMARY KEY,
      applied_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
  " > /dev/null

  # On first run (table just created or empty), seed with all existing .sql files as "applied"
  applied_count=$(sudo -u postgres psql -d anoven_app_dev -tAc "SELECT COUNT(*) FROM schema_migrations;")
  if [[ "$applied_count" == "0" ]]; then
    log "schema_migrations empty → seeding existing migrations as 'already applied' (first-run only)"
    for sql_file in "${MIGRATIONS_DIR}"/*.sql; do
      [[ -f "$sql_file" ]] || continue
      version=$(basename "$sql_file" .sql)
      sudo -u postgres psql -d anoven_app_dev -c "INSERT INTO schema_migrations (version) VALUES ('$version') ON CONFLICT DO NOTHING;" > /dev/null
    done
    log "seeded $(ls -1 "${MIGRATIONS_DIR}"/*.sql 2>/dev/null | wc -l) existing migrations"
  fi
fi

# Apply pending migrations (any .sql in migrations/ not in schema_migrations)
pending=()
for sql_file in "${MIGRATIONS_DIR}"/*.sql; do
  [[ -f "$sql_file" ]] || continue
  version=$(basename "$sql_file" .sql)
  if [[ "$DRY_RUN" == "--dry-run" ]]; then
    is_applied=$(sudo -u postgres psql -d anoven_app_dev -tAc "SELECT COUNT(*) FROM schema_migrations WHERE version='$version';" 2>/dev/null || echo "0")
  else
    is_applied=$(sudo -u postgres psql -d anoven_app_dev -tAc "SELECT COUNT(*) FROM schema_migrations WHERE version='$version';")
  fi
  if [[ "$is_applied" == "0" ]]; then
    pending+=("$sql_file")
  fi
done

if [[ ${#pending[@]} -eq 0 ]]; then
  log "no pending migrations"
else
  log "pending migrations: ${#pending[@]}"
  for m in "${pending[@]}"; do log "  - $m"; done

  for sql_file in "${pending[@]}"; do
    version=$(basename "$sql_file" .sql)
    log "applying migration: $version"
    if [[ "$DRY_RUN" != "--dry-run" ]]; then
      if sudo -u postgres psql -d anoven_app_dev -v ON_ERROR_STOP=1 -f "$sql_file"; then
        sudo -u postgres psql -d anoven_app_dev -c "INSERT INTO schema_migrations (version) VALUES ('$version');"
        log "  applied: $version"
      else
        log "FATAL: migration $version failed. Rolling back to $ROLLBACK_COMMIT."
        rollback "$ROLLBACK_COMMIT" "migration $version failed"
        exit 3
      fi
    fi
  done
fi

# ---- 8) Restart services ----

run systemctl restart anoven-app-backend.service anoven-app-frontend.service

# ---- 9) Wait + verify ----

if [[ "$DRY_RUN" == "--dry-run" ]]; then
  log "DRY-RUN: skipping verify"
  log "==== DRY-RUN complete (no changes applied) ===="
  exit 0
fi

log "waiting 5s for services to settle..."
sleep 5

verify_fail=()

if ! systemctl is-active --quiet anoven-app-backend.service; then
  verify_fail+=("anoven-app-backend.service not active")
fi
if ! systemctl is-active --quiet anoven-app-frontend.service; then
  verify_fail+=("anoven-app-frontend.service not active")
fi
if ! curl -sf --max-time 10 -o /dev/null https://anoven.ai; then
  verify_fail+=("https://anoven.ai did not respond 200 within 10s")
fi
if ! curl -sf --max-time 5 -o /dev/null http://127.0.0.1:8000/docs; then
  verify_fail+=("http://127.0.0.1:8000/docs unreachable")
fi

if [[ ${#verify_fail[@]} -eq 0 ]]; then
  log "==== Deploy complete: $PRE_PULL_COMMIT → $NEW_COMMIT ===="
  telegram_alert "Anoven deploy OK on $(hostname) at $TS — $PRE_PULL_COMMIT → $NEW_COMMIT"
  exit 0
fi

# ---- 10) Verify failed → ROLLBACK ----

reason="post-deploy verify failed: $(IFS='; '; echo "${verify_fail[*]}")"
log "$reason"
rollback "$ROLLBACK_COMMIT" "$reason"
exit 4
