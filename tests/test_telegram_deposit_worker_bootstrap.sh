#!/usr/bin/env bash
# Offline test: the worker automatically creates a latest-post cursor after an
# authorized session exists, without touching historical documents or Git state.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d -t legal-telegram-worker-test-XXXXXX)"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

WORKER="$TMP/worker"
REPO="$TMP/repo"
REMOTE="$TMP/remote.git"
mkdir -p "$WORKER/telegram-deposit" "$WORKER/logs" "$REPO/scripts"
git init --bare "$REMOTE" >/dev/null
git -C "$REPO" init >/dev/null
git -C "$REPO" config user.name test
git -C "$REPO" config user.email test@example.invalid
git -C "$REPO" checkout -b collector-import >/dev/null
git -C "$REPO" remote add origin "$REMOTE"

cat >"$REPO/scripts/pull_telegram_deposit.py" <<'PY'
#!/usr/bin/env python3
import json
import sys
from pathlib import Path
args = sys.argv[1:]
if "--bootstrap-latest" not in args:
    raise SystemExit("expected automatic bootstrap")
state = Path(args[args.index("--state") + 1])
state.parent.mkdir(parents=True, exist_ok=True)
state.write_text('{"last_scanned_post_id": 99, "failed_post_ids": []}\n', encoding="utf-8")
print(json.dumps({"status": "cursor_bootstrapped", "last_scanned_post_id": 99, "public_search_enabled": False, "platform_database_modified": False}))
PY
cat >"$REPO/scripts/process_telegram_deposit.py" <<'PY'
raise SystemExit("processor must not run during empty first-run bootstrap")
PY
cat >"$REPO/scripts/validate_telegram_deposit.py" <<'PY'
raise SystemExit("validator must not run during empty first-run bootstrap")
PY
cat >"$REPO/scripts/validate_collector_archive.py" <<'PY'
raise SystemExit("collector validator must not run during empty first-run bootstrap")
PY
cp "$REPO_ROOT/scripts/run_telegram_deposit_worker.sh" "$REPO/scripts/run_telegram_deposit_worker.sh"
chmod 700 "$REPO/scripts/run_telegram_deposit_worker.sh"
git -C "$REPO" add scripts
git -C "$REPO" commit -m test >/dev/null
git -C "$REPO" push -u origin collector-import >/dev/null

cat >"$WORKER/telegram-deposit/worker.env" <<'ENV'
TELEGRAM_API_ID='1'
TELEGRAM_API_HASH='test'
TELEGRAM_PHONE='+10000000000'
TELEGRAM_CHANNEL='test'
ARCHIVE_WORKER_PUSH='0'
ENV
printf 'authorized-test-session' >"$WORKER/telegram-deposit/telegram-account.session"

ARCHIVE_WORKER_ROOT="$WORKER" ARCHIVE_REPOSITORY="$REPO" ARCHIVE_PRIVATE_DIR="$WORKER/telegram-deposit" ARCHIVE_LOG_DIR="$WORKER/logs" \
  "$REPO/scripts/run_telegram_deposit_worker.sh" >/tmp/legal-telegram-worker-bootstrap-test.out

python3 - "$WORKER/telegram-deposit/status/last-cycle.json" "$WORKER/telegram-deposit/state.json" <<'PY'
import json
import sys
from pathlib import Path
status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
state = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
assert status["outcome"] == "succeeded", status
assert status["detail"] == "cursor_bootstrapped_at_latest_post_no_historical_collection", status
assert status["public_search_enabled"] is False, status
assert status["platform_database_modified"] is False, status
assert state["last_scanned_post_id"] == 99, state
print(json.dumps({"status": "passed", "cursor": state["last_scanned_post_id"]}))
PY

test -z "$(git -C "$REPO" status --porcelain)"
