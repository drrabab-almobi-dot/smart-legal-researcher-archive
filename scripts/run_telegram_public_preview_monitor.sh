#!/usr/bin/env bash
# Private worker cycle for public Telegram preview monitoring only.
# It never uses an account session, downloads attachment binaries, promotes records,
# writes to RABAB LEGAL AI, or changes public search/download eligibility.
set -Eeuo pipefail

REPO="${ARCHIVE_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
BRANCH="${ARCHIVE_BRANCH:-collector-import}"
PRIVATE_DIR="${ARCHIVE_WORKER_PRIVATE_DIR:-/home/ubuntu/legal-archive-worker/telegram-public-preview}"
CHANNEL="${TELEGRAM_PUBLIC_CHANNEL:-robiai33}"
MAX_PAGES="${TELEGRAM_PUBLIC_MAX_PAGES:-4}"
SLEEP_SECONDS="${TELEGRAM_PUBLIC_SLEEP_SECONDS:-1}"
LOCK_FILE="$PRIVATE_DIR/monitor.lock"
STATUS_FILE="$PRIVATE_DIR/status.json"
LOG_DIR="${ARCHIVE_WORKER_LOG_DIR:-/home/ubuntu/legal-archive-worker/logs}"
LOG_FILE="$LOG_DIR/telegram-public-preview.log"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$PRIVATE_DIR" "$LOG_DIR"
chmod 700 "$PRIVATE_DIR"

log() { printf '%s [%s] %s\n' "$(date -u +%FT%TZ)" "$RUN_ID" "$*" | tee -a "$LOG_FILE"; }
write_status() {
  local outcome="$1" detail="$2"
  python3 - "$STATUS_FILE" "$outcome" "$detail" "$RUN_ID" "$CHANNEL" <<'PY'
import json, sys
from datetime import datetime, timezone
path, outcome, detail, run_id, channel = sys.argv[1:]
payload = {
  "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
  "run_id": run_id,
  "mode": "public_preview_metadata_only",
  "channel": channel,
  "outcome": outcome,
  "detail": detail,
  "binary_downloads": 0,
  "legal_search_admissions": 0,
  "platform_database_writes": 0,
}
with open(path + ".tmp", "w", encoding="utf-8") as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
import os
os.replace(path + ".tmp", path)
PY
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  write_status "skipped" "another_public_preview_cycle_is_active"
  exit 0
fi

cd "$REPO"
if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
  write_status "deferred" "unexpected_branch"
  exit 0
fi
if [[ -n "$(git status --porcelain)" ]]; then
  write_status "deferred" "repository_contains_uncommitted_changes"
  exit 0
fi

# Synchronize only when a fast-forward is possible. Do not overwrite worker state.
git fetch origin "$BRANCH" >>"$LOG_FILE" 2>&1 || log "fetch_deferred"
read -r ahead behind < <(git rev-list --left-right --count "HEAD...origin/$BRANCH")
if [[ "$ahead" == "0" && "$behind" != "0" ]]; then
  git merge --ff-only "origin/$BRANCH" >>"$LOG_FILE" 2>&1 || {
    write_status "deferred" "fast_forward_failed"; exit 0;
  }
elif [[ "$ahead" != "0" || "$behind" != "0" ]]; then
  write_status "deferred" "remote_divergence_or_local_commits"
  exit 0
fi

before_register_hash="$(sha256sum manifests/collector/telegram-source-register.csv | awk '{print $1}')"
result_file="$PRIVATE_DIR/run-${RUN_ID}.json"
if ! python3 scripts/inventory_telegram_archive.py --max-pages "$MAX_PAGES" --sleep-seconds "$SLEEP_SECONDS" >"$result_file"; then
  git restore -- manifests/collector/telegram-inventory-summary.json manifests/collector/telegram-source-register.csv manifests/collector/telegram-acquisition-status.csv indices/collector/pending-telegram-sources.ndjson 2>/dev/null || true
  write_status "failed" "public_preview_fetch_failed"
  exit 1
fi

after_register_hash="$(sha256sum manifests/collector/telegram-source-register.csv | awk '{print $1}')"
if [[ "$before_register_hash" == "$after_register_hash" ]]; then
  # Inventory code refreshes page-count telemetry even where no channel post changed.
  # Revert it so an empty cycle remains immutable and does not trigger a commit.
  git restore -- manifests/collector/telegram-inventory-summary.json manifests/collector/telegram-source-register.csv manifests/collector/telegram-acquisition-status.csv indices/collector/pending-telegram-sources.ndjson
  write_status "succeeded" "no_new_public_preview_metadata"
  log "succeeded:no_new_public_preview_metadata"
  exit 0
fi

# Never auto-commit public-channel metadata: it is provisional and may need legal review.
# Preserve only changed preview evidence privately, then reset the worker repository so the
# next polling cycle remains independent and can detect later posts.
DETECTION_DIR="$PRIVATE_DIR/detections/$RUN_ID"
mkdir -p "$DETECTION_DIR"
while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    manifests/collector/telegram-inventory-summary.json|\
    manifests/collector/telegram-source-register.csv|\
    manifests/collector/telegram-acquisition-status.csv|\
    indices/collector/pending-telegram-sources.ndjson|\
    originals/telegram-preview/robiai33/*)
      mkdir -p "$DETECTION_DIR/$(dirname "$path")"
      cp -p "$path" "$DETECTION_DIR/$path"
      ;;
  esac
done < <(git status --porcelain | sed -E 's/^.. //; s/^[^ ]+ -> //')
cp -p "$result_file" "$DETECTION_DIR/inventory-result.json"
git restore -- manifests/collector/telegram-inventory-summary.json manifests/collector/telegram-source-register.csv manifests/collector/telegram-acquisition-status.csv indices/collector/pending-telegram-sources.ndjson
git clean -f -- originals/telegram-preview/robiai33 >>"$LOG_FILE" 2>&1 || true
write_status "review_required" "new_public_preview_metadata_preserved_privately_no_binary_download_or_indexing"
log "review_required:new_public_preview_metadata_preserved_privately"
