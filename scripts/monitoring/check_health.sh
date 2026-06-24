#!/bin/bash
# Anoven health check + Telegram alerts
# M3 of the bitacora-port course (2026-06-23)
#
# Runs 9 checks; if any fail, sends a Telegram message to the configured chat_id.
# Logs every run (pass or fail) to /var/log/anoven-monitoring.log.

set -uo pipefail

readonly ENV_FILE="/home/anoven/anoven-app/.env.monitoring"
readonly LOG_FILE="/var/log/anoven-monitoring.log"
readonly HOSTNAME="$(hostname)"
readonly TS="$(date -Iseconds)"

# Load env (fail if missing — security: don't run without explicit config)
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

failed_checks=()

# ---- Check 1: Broken symlinks in /home/*/.claude/ ----
broken_links=$(find /home -path "*/.claude/*" -xtype l 2>/dev/null | wc -l)
if [[ "$broken_links" -gt 0 ]]; then
  failed_checks+=("broken_symlinks_in_claude_homes: $broken_links broken links found (run: find /home -path '*/.claude/*' -xtype l)")
fi

# ---- Check 2: Failed systemd services ----
failed_units=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | grep -v '^$' | tr '\n' ',' | sed 's/,$//')
if [[ -n "$failed_units" ]]; then
  failed_checks+=("failed_systemd_units: $failed_units")
fi

# ---- Check 3: HTTPS Layer 1 ----
if ! curl -sf --max-time 10 -o /dev/null https://anoven.ai; then
  failed_checks+=("https_anoven_ai: did not respond 200 within 10s")
fi

# ---- Check 4: FastAPI backend ----
if ! curl -sf --max-time 5 -o /dev/null http://127.0.0.1:8000/docs; then
  failed_checks+=("fastapi_backend: 127.0.0.1:8000/docs unreachable")
fi

# ---- Check 5: Frontend Next.js ----
if ! curl -sf --max-time 5 -o /dev/null http://127.0.0.1:3100; then
  failed_checks+=("frontend_nextjs: 127.0.0.1:3100 unreachable")
fi

# ---- Check 6: Postgres ready ----
if ! pg_isready -h 127.0.0.1 -p 5432 -q 2>/dev/null; then
  failed_checks+=("postgres: pg_isready failed on 127.0.0.1:5432")
fi

# ---- Check 7: Engram daemon ----
if ! ss -tln 2>/dev/null | awk '{print $4}' | grep -qE ":7437$"; then
  failed_checks+=("engram_daemon: not listening on :7437")
fi

# ---- Check 8: Disk usage of / ----
disk_pct=$(df / --output=pcent 2>/dev/null | tail -1 | tr -dc '0-9')
if [[ -n "$disk_pct" && "$disk_pct" -gt 80 ]]; then
  failed_checks+=("disk_root: ${disk_pct}% used (threshold 80%)")
fi

# ---- Check 9: Memory available ----
mem_avail=$(free -m | awk '/^Mem:/ {print $7}')
if [[ -n "$mem_avail" && "$mem_avail" -lt 200 ]]; then
  failed_checks+=("memory: only ${mem_avail}MB available (threshold 200MB)")
fi

# ---- Decide & alert ----
n_failed=${#failed_checks[@]}

if [[ "$n_failed" -eq 0 ]]; then
  echo "$TS [$HOSTNAME] all checks passed (9/9)" >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

# Build alert message
msg="Anoven alert — ${HOSTNAME} ${TS}
Failed checks (${n_failed}/9):"
for c in "${failed_checks[@]}"; do
  msg+="
- ${c}"
done

# Log it
{
  echo "$TS [$HOSTNAME] FAILED ${n_failed}/9 checks"
  for c in "${failed_checks[@]}"; do
    echo "  - $c"
  done
} >> "$LOG_FILE" 2>/dev/null || true

# Send to Telegram if configured
if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_CHAT_ID:-}" ]]; then
  response=$(curl -s --max-time 10 -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
    --data-urlencode "text=${msg}" 2>&1)
  if ! echo "$response" | grep -q '"ok":true'; then
    echo "ERROR: Telegram send failed. Response: $response" >&2
    echo "$TS [$HOSTNAME] TELEGRAM_FAILED: $response" >> "$LOG_FILE" 2>/dev/null || true
  fi
else
  echo "WARNING: TELEGRAM_CHAT_ID empty — alerts logged only (no notification sent)" >&2
  echo "$TS [$HOSTNAME] TELEGRAM_CHAT_ID empty, alert logged only" >> "$LOG_FILE" 2>/dev/null || true
fi

exit 1
