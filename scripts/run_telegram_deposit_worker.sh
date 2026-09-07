#!/usr/bin/env bash
# Private, pull-only continuous intake worker for a controlled Telegram deposit.
# It never enables search, downloads, platform imports, or public publication.
set -Eeuo pipefail
umask 077

WORKER_ROOT="${ARCHIVE_WORKER_ROOT:-/home/ubuntu/legal-archive-worker}"
REPO="${ARCHIVE_REPOSITORY:-$WORKER_ROOT/repo/smart-legal-researcher-archive}"
PRIVATE_DIR="${ARCHIVE_PRIVATE_DIR:-$WORKER_ROOT/telegram-deposit}"
ENV_FILE="${ARCHIVE_ENV_FILE:-$PRIVATE_DIR/worker.env}"
LOG_DIR="${ARCHIVE_LOG_DIR:-$WORKER_ROOT/logs}"
STATUS_DIR="$PRIVATE_DIR/status"
STATUS_FILE="$STATUS_DIR/last-cycle.json"
LAST_SUCCESS_FILE="$STATUS_DIR/last-success.json"
LOCK_FILE="$PRIVATE_DIR/worker.lock"
BRANCH="${ARCHIVE_BRANCH:-collector-import}"
MAX_POSTS="${TELEGRAM_MAX_POSTS_PER_CYCLE:-25}"
MAX_FILE_BYTES="${TELEGRAM_MAX_FILE_BYTES:-262144000}"
PUSH_ENABLED="${ARCHIVE_WORKER_PUSH:-0}"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PHASE="starting"
PULL_RESULT=""
PROCESS_RESULT=""
VALIDATE_RESULT=""
COLLECTOR_RESULT=""
COMMIT_ID=""

mkdir -p "$LOG_DIR" "$STATUS_DIR"
chmod 700 "$PRIVATE_DIR" "$STATUS_DIR" 2>/dev/null || true

log() {
  printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$RUN_ID" "$*"
}

write_status() {
  local outcome="$1"
  local detail="$2"
  local completed_at
  completed_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$STATUS_FILE" "$LAST_SUCCESS_FILE" "$RUN_ID" "$STARTED_AT" "$completed_at" "$PHASE" "$outcome" "$detail" "$BRANCH" "$PUSH_ENABLED" "$COMMIT_ID" "$PULL_RESULT" "$PROCESS_RESULT" "$VALIDATE_RESULT" "$COLLECTOR_RESULT" <<'PY'
import json
import os
import sys
from pathlib import Path

(
    status_path, success_path, run_id, started_at, completed_at, phase, outcome,
    detail, branch, push_enabled, commit_id, pull_path, process_path, validate_path,
    collector_path,
) = sys.argv[1:]

def load_json(path):
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

payload = {
    "schema_version": "1.0",
    "run_id": run_id,
    "started_at": started_at,
    "completed_at": completed_at,
    "phase": phase,
    "outcome": outcome,
    "detail": detail,
    "branch": branch,
    "push_enabled": push_enabled == "1",
    "commit_id": commit_id or None,
    "public_search_enabled": False,
    "public_downloads_enabled": False,
    "platform_database_modified": False,
    "pull": load_json(pull_path),
    "processing": load_json(process_path),
    "validation": load_json(validate_path),
    "collector_validation": load_json(collector_path),
}
for output in (Path(status_path), Path(success_path) if outcome == "succeeded" else None):
    if output is None:
        continue
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    os.replace(temp, output)
PY
}

defer() {
  local detail="$1"
  log "deferred:$detail"
  write_status "deferred" "$detail" || true
  exit 0
}

on_error() {
  local exit_code=$?
  set +e
  log "failed:phase=$PHASE:exit=$exit_code"
  write_status "failed" "phase=${PHASE};exit=${exit_code}" || true
  exit "$exit_code"
}
trap on_error ERR

retry() {
  local label="$1"
  shift
  local attempt rc=1
  for attempt in 1 2 3; do
    if "$@"; then
      return 0
    fi
    rc=$?
    log "retryable_failure:$label:attempt=$attempt:exit=$rc"
    sleep "$((attempt * 10))"
  done
  return "$rc"
}

run_json() {
  local label="$1"
  local output="$2"
  shift 2
  local temporary="${output}.tmp"
  local attempt rc=1
  rm -f "$temporary"
  for attempt in 1 2 3; do
    if "$@" >"$temporary" 2>&1; then
      if python3 -m json.tool "$temporary" >/dev/null 2>&1; then
        mv -f "$temporary" "$output"
        cat "$output"
        return 0
      fi
      log "invalid_json_output:$label:attempt=$attempt"
    else
      rc=$?
      log "retryable_failure:$label:attempt=$attempt:exit=$rc"
    fi
    sleep "$((attempt * 10))"
  done
  rm -f "$temporary"
  return "$rc"
}

contains_only_worker_outputs() {
  local unexpected
  unexpected="$(git status --porcelain | awk '{print substr($0,4)}' | while IFS= read -r path; do
    case "$path" in
      originals/telegram-deposit/*|\
      extracted/telegram-deposit-review/*|\
      indices/collector/pending-telegram-deposit-documents.ndjson|\
      manifests/collector/telegram-deposit-file-register.csv|\
      manifests/collector/telegram-deposit-failures.csv|\
      manifests/collector/telegram-deposit-binary-duplicates.csv|\
      manifests/collector/telegram-deposit-duplicates.csv|\
      manifests/collector/telegram-deposit-processing-log.csv|\
      manifests/collector/telegram-deposit-summary.json|\
      manifests/collector/telegram-deposit-validation-report.json)
        ;;
      *) printf '%s\n' "$path" ;;
    esac
  done)"
  [[ -z "$unexpected" ]]
}

stage_worker_outputs() {
  git add -A -- \
    originals/telegram-deposit \
    extracted/telegram-deposit-review \
    indices/collector/pending-telegram-deposit-documents.ndjson \
    manifests/collector/telegram-deposit-file-register.csv \
    manifests/collector/telegram-deposit-failures.csv \
    manifests/collector/telegram-deposit-binary-duplicates.csv \
    manifests/collector/telegram-deposit-duplicates.csv \
    manifests/collector/telegram-deposit-processing-log.csv \
    manifests/collector/telegram-deposit-summary.json \
    manifests/collector/telegram-deposit-validation-report.json
}

mkdir -p "$PRIVATE_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  log "cycle_skipped:another_cycle_is_active"
  write_status "skipped" "another_cycle_is_active" || true
  exit 0
fi

if [[ ! -r "$ENV_FILE" ]]; then
  defer "missing_private_environment"
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${TELEGRAM_API_ID:?missing TELEGRAM_API_ID}"
: "${TELEGRAM_API_HASH:?missing TELEGRAM_API_HASH}"
: "${TELEGRAM_PHONE:?missing TELEGRAM_PHONE}"
: "${TELEGRAM_CHANNEL:=robiai33}"
: "${ARCHIVE_WORKER_PUSH:=$PUSH_ENABLED}"
PUSH_ENABLED="$ARCHIVE_WORKER_PUSH"

if [[ ! -d "$REPO/.git" ]]; then
  defer "missing_repository"
fi
cd "$REPO"
if [[ "$(git branch --show-current)" != "$BRANCH" ]]; then
  defer "unexpected_repository_branch"
fi
if ! contains_only_worker_outputs; then
  defer "repository_contains_non_worker_changes"
fi

PHASE="synchronizing"
if retry "git_fetch" git fetch origin "$BRANCH"; then
  read -r ahead behind < <(git rev-list --left-right --count "HEAD...origin/$BRANCH")
  if [[ "$ahead" == "0" && "$behind" != "0" ]]; then
    retry "git_fast_forward" git merge --ff-only "origin/$BRANCH" || defer "remote_fast_forward_failed"
  elif [[ "$ahead" != "0" && "$behind" != "0" ]]; then
    if ! git rebase "origin/$BRANCH"; then
      git rebase --abort || true
      defer "remote_divergence_requires_manual_resolution"
    fi
  elif [[ "$ahead" != "0" && "$PUSH_ENABLED" == "1" ]]; then
    if retry "push_pending_commits" git -c http.version=HTTP/1.1 push origin "$BRANCH"; then
      log "pending_local_commits_pushed"
    else
      log "pending_local_commits_retained_for_later_push"
    fi
  fi
else
  log "remote_sync_deferred_using_last_verified_repository_snapshot"
fi

# LFS access is helpful for baseline validation, but a transient LFS failure must
# not erase or replace a received Telegram original.
retry "git_lfs_pull" git lfs pull || log "lfs_sync_deferred"

PHASE="retrieving_authorized_deposit"
CYCLE_DIR="$PRIVATE_DIR/runs/$RUN_ID"
mkdir -p "$CYCLE_DIR"
PULL_RESULT="$CYCLE_DIR/pull.json"
PROCESS_RESULT="$CYCLE_DIR/process.json"
VALIDATE_RESULT="$CYCLE_DIR/telegram-validation.json"
COLLECTOR_RESULT="$CYCLE_DIR/collector-validation.json"
run_json "telegram_pull" "$PULL_RESULT" python3 scripts/pull_telegram_deposit.py \
  --apply --channel "$TELEGRAM_CHANNEL" \
  --session "$PRIVATE_DIR/telegram-account.session" \
  --state "$PRIVATE_DIR/state.json" \
  --limit "$MAX_POSTS" --max-file-bytes "$MAX_FILE_BYTES"

PHASE="processing_private_documents"
run_json "telegram_process" "$PROCESS_RESULT" python3 scripts/process_telegram_deposit.py --apply

PHASE="validating_private_documents"
run_json "telegram_validation" "$VALIDATE_RESULT" python3 scripts/validate_telegram_deposit.py
run_json "collector_validation" "$COLLECTOR_RESULT" python3 scripts/validate_collector_archive.py

PHASE="committing_validated_outputs"
if [[ -z "$(git status --porcelain)" ]]; then
  write_status "succeeded" "no_new_archive_changes" || true
  log "succeeded:no_new_archive_changes"
  exit 0
fi
if ! contains_only_worker_outputs; then
  defer "validated_worker_outputs_present_but_repository_contains_non_worker_changes"
fi
stage_worker_outputs
if git diff --cached --quiet; then
  defer "unstaged_or_unexpected_changes_after_worker_staging"
fi
git diff --cached --check
git config user.name "${ARCHIVE_GIT_AUTHOR_NAME:-RABAB Legal Archive Worker}"
git config user.email "${ARCHIVE_GIT_AUTHOR_EMAIL:-archive-worker@rabab-legal.invalid}"
git commit -m "collector: أرشفة إيداع Telegram الخاص"
COMMIT_ID="$(git rev-parse --short HEAD)"

PHASE="pushing_private_archive"
if [[ "$PUSH_ENABLED" == "1" ]]; then
  if retry "git_push" git -c http.version=HTTP/1.1 push origin "$BRANCH"; then
    write_status "succeeded" "validated_archive_changes_committed_and_pushed" || true
    log "succeeded:committed_and_pushed:$COMMIT_ID"
  else
    write_status "succeeded" "validated_archive_changes_committed_locally_push_deferred" || true
    log "succeeded:committed_locally_push_deferred:$COMMIT_ID"
  fi
else
  write_status "succeeded" "validated_archive_changes_committed_locally_push_disabled" || true
  log "succeeded:committed_locally_push_disabled:$COMMIT_ID"
fi

# Keep 31 daily folders of structured run evidence. This affects only private
# worker runtime state, never originals or versioned archive evidence.
find "$PRIVATE_DIR/runs" -mindepth 1 -maxdepth 1 -type d -mtime +31 -exec rm -rf {} +
exit 0
