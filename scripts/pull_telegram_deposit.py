#!/usr/bin/env python3
"""Retrieve new Telegram channel attachments through an authorized user session.

This is not a bot. It requires a Telegram account's own API application and an
interactive one-time authorization. It makes no outgoing calls to the channel,
never changes messages, and only writes immutable originals plus private intake
metadata. It never marks a record searchable or writes to any platform database.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHANNEL = "robiai33"
ORIGINALS_ROOT = ROOT / "originals" / "telegram-deposit"
MANIFEST_DIR = ROOT / "manifests" / "collector"
REGISTER = MANIFEST_DIR / "telegram-deposit-file-register.csv"
FAILURES = MANIFEST_DIR / "telegram-deposit-failures.csv"
BINARY_DUPLICATES = MANIFEST_DIR / "telegram-deposit-binary-duplicates.csv"
STATE_DEFAULT = ROOT / "work" / "telegram-deposit" / "state.json"
SESSION_DEFAULT = ROOT / "work" / "telegram-deposit" / "telegram-account.session"

URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.I)
OFFICIAL_HOSTS = {"moj.gov.sa", "laws.moj.gov.sa", "bog.gov.sa", "saip.gov.sa"}
REGISTER_HEADER = [
    "telegram_channel", "post_id", "post_url", "posted_at", "original_filename",
    "storage_path", "bytes", "sha256", "mime_type", "caption_as_received",
    "urls_as_posted", "official_url_as_posted_unverified", "acquired_at", "access_status",
    "binary_status", "official_source_status", "search_eligibility", "notes",
]
FAILURE_HEADER = ["attempted_at", "telegram_channel", "post_id", "post_url", "status", "reason", "next_step"]
BINARY_DUPLICATE_HEADER = [
    "duplicate_post_id", "duplicate_storage_path", "duplicate_sha256", "canonical_post_id",
    "canonical_storage_path", "detection_method", "disposition", "recorded_at",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(value: str, fallback: str) -> str:
    value = Path(value or fallback).name.strip().replace("\x00", "")
    return value or fallback


def urls_from_caption(caption: str) -> tuple[str, str]:
    urls = sorted(set(URL_RE.findall(caption or "")))
    official = ""
    for url in urls:
        host = re.sub(r"^www\.", "", url.split("/", 3)[2].lower())
        if host in OFFICIAL_HOSTS or any(host.endswith("." + item) for item in OFFICIAL_HOSTS):
            official = url
            break
    return ";".join(urls), official


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_scanned_post_id": 0, "failed_post_ids": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid state file: {path}: {exc}") from exc
    return {
        "last_scanned_post_id": int(data.get("last_scanned_post_id") or 0),
        "failed_post_ids": sorted({int(item) for item in data.get("failed_post_ids", []) if str(item).isdigit()}),
    }


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def api_settings() -> tuple[int, str, str | None]:
    raw_id = os.environ.get("TELEGRAM_API_ID", "").strip()
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    phone = os.environ.get("TELEGRAM_PHONE", "").strip() or None
    if not raw_id or not api_hash:
        raise SystemExit(
            "Missing TELEGRAM_API_ID or TELEGRAM_API_HASH. Create a personal Telegram API application at "
            "https://my.telegram.org/apps and keep its credentials outside Git."
        )
    try:
        return int(raw_id), api_hash, phone
    except ValueError as exc:
        raise SystemExit("TELEGRAM_API_ID must be numeric") from exc


def telethon() -> tuple[Any, Any]:
    try:
        from telethon import TelegramClient  # type: ignore
        from telethon.errors import SessionPasswordNeededError  # type: ignore
    except ImportError as exc:
        raise SystemExit("Telethon is required. Install from requirements-telegram-deposit.txt outside the repository runtime.") from exc
    return TelegramClient, SessionPasswordNeededError


async def authorize(session: Path) -> None:
    TelegramClient, _ = telethon()
    api_id, api_hash, phone = api_settings()
    if not phone:
        raise SystemExit("Set TELEGRAM_PHONE in the private environment before initial authorization.")
    session.parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(session), api_id, api_hash)
    await client.connect()
    try:
        if await client.is_user_authorized():
            print(json.dumps({"status": "already_authorized", "session": str(session)}, ensure_ascii=False))
            return
        await client.send_code_request(phone)
        code = input("Telegram login code: ").strip()
        try:
            await client.sign_in(phone=phone, code=code)
        except Exception as exc:
            if type(exc).__name__ != "SessionPasswordNeededError":
                raise
            password = input("Telegram two-step password: ")
            await client.sign_in(password=password)
        print(json.dumps({"status": "authorized", "session": str(session)}, ensure_ascii=False))
    finally:
        await client.disconnect()


def message_filename(message: Any) -> str:
    name = getattr(getattr(message, "file", None), "name", None)
    extension = getattr(getattr(message, "file", None), "ext", None) or ""
    if name:
        return safe_name(str(name), f"telegram-{message.id}{extension}")
    if getattr(message, "photo", None):
        return f"telegram-photo-{message.id}{extension or '.jpg'}"
    return f"telegram-attachment-{message.id}{extension or '.bin'}"


def target_path(channel: str, post_id: int, filename: str, file_sha: str) -> Path:
    folder = ORIGINALS_ROOT / channel / f"post-{post_id}"
    desired = folder / filename
    if not desired.exists() or digest(desired) == file_sha:
        return desired
    return folder / f"{desired.stem}--sha256-{file_sha[:12]}{desired.suffix}"


async def bootstrap(channel: str, session: Path, state_path: Path, apply: bool) -> dict[str, Any]:
    """Set the incremental cursor to the current newest message without downloading history."""
    TelegramClient, _ = telethon()
    api_id, api_hash, _ = api_settings()
    client = TelegramClient(str(session), api_id, api_hash)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            raise SystemExit("Telegram session is not authorized. Run this script once with --authorize in an interactive terminal.")
        entity = await client.get_entity(channel if channel.startswith("@") else f"@{channel}")
        messages = await client.get_messages(entity, limit=1)
        latest = int(messages[0].id) if messages else 0
        if apply:
            write_state(state_path, {"last_scanned_post_id": latest, "failed_post_ids": []})
        return {
            "status": "cursor_bootstrapped", "channel": channel.lstrip("@"), "last_scanned_post_id": latest,
            "new_binaries_preserved": 0, "applied": apply, "public_search_enabled": False,
            "platform_database_modified": False,
        }
    finally:
        await client.disconnect()


async def pull(channel: str, session: Path, state_path: Path, limit: int | None, apply: bool, from_post_id: int | None, max_file_bytes: int) -> dict[str, Any]:
    TelegramClient, _ = telethon()
    api_id, api_hash, _ = api_settings()
    state_exists = state_path.exists()
    state = read_state(state_path)
    if not state_exists and from_post_id is None:
        raise SystemExit(
            "No intake cursor exists. Run once with --bootstrap-latest --apply to collect only future channel posts, "
            "or provide --from-post-id after approving a bounded historical import."
        )
    if from_post_id is not None:
        state["last_scanned_post_id"] = from_post_id
    prior_rows = read_csv(REGISTER)
    failures = read_csv(FAILURES)
    binary_duplicates = read_csv(BINARY_DUPLICATES)
    recorded = {(row.get("post_id"), row.get("sha256")) for row in prior_rows}
    prior_by_sha = {row["sha256"]: row for row in prior_rows if row.get("sha256")}
    recorded_duplicate_keys = {
        (row.get("duplicate_post_id"), row.get("duplicate_sha256")) for row in binary_duplicates
    }
    client = TelegramClient(str(session), api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        raise SystemExit("Telegram session is not authorized. Run this script once with --authorize in an interactive terminal.")

    acquired: list[dict[str, str]] = []
    new_failures: list[dict[str, str]] = []
    new_binary_duplicates: list[dict[str, str]] = []
    failed_ids: set[int] = set(state["failed_post_ids"])
    latest_seen = int(state["last_scanned_post_id"])
    try:
        entity = await client.get_entity(channel if channel.startswith("@") else f"@{channel}")
        candidates: dict[int, Any] = {}
        for failed_id in sorted(failed_ids):
            message = await client.get_messages(entity, ids=failed_id)
            if message:
                candidates[int(message.id)] = message
        async for message in client.iter_messages(entity, min_id=latest_seen, reverse=True, limit=limit):
            candidates[int(message.id)] = message
            latest_seen = max(latest_seen, int(message.id))

        for post_id, message in sorted(candidates.items()):
            latest_seen = max(latest_seen, post_id)
            if not (getattr(message, "document", None) or getattr(message, "photo", None)):
                failed_ids.discard(post_id)
                continue
            post_url = f"https://t.me/{channel.lstrip('@')}/{post_id}"
            caption = str(getattr(message, "message", "") or "")
            filename = message_filename(message)
            posted_at = getattr(message, "date", None)
            posted_at_text = posted_at.isoformat() if posted_at else ""
            temp_root = Path(tempfile.mkdtemp(prefix="telegram-deposit-", dir=ROOT / "work"))
            try:
                declared_size = int(getattr(getattr(message, "file", None), "size", 0) or 0)
                if max_file_bytes > 0 and declared_size > max_file_bytes:
                    raise ValueError(
                        f"attachment_exceeds_configured_limit:{declared_size}>{max_file_bytes}"
                    )
                downloaded = await client.download_media(message, file=str(temp_root))
                if not downloaded:
                    raise RuntimeError("Telegram did not return an attachment binary")
                temporary = Path(downloaded)
                file_sha = digest(temporary)
                destination = target_path(channel.lstrip("@"), post_id, filename, file_sha)
                if apply and not destination.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(temporary, destination)
                if not apply:
                    destination = Path("<dry-run>") / destination.name
                stored_path = destination.relative_to(ROOT).as_posix() if apply else str(destination)
                if (str(post_id), file_sha) not in recorded:
                    urls, official = urls_from_caption(caption)
                    mime = getattr(getattr(message, "file", None), "mime_type", None) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
                    acquired.append({
                        "telegram_channel": channel.lstrip("@"), "post_id": str(post_id), "post_url": post_url,
                        "posted_at": posted_at_text, "original_filename": filename, "storage_path": stored_path,
                        "bytes": str(temporary.stat().st_size), "sha256": file_sha, "mime_type": str(mime),
                        "caption_as_received": caption, "urls_as_posted": urls,
                        "official_url_as_posted_unverified": official, "acquired_at": utc_now(),
                        "access_status": "authorized_telegram_account_session", "binary_status": "preserved_unmodified",
                        "official_source_status": "unverified", "search_eligibility": "not_eligible",
                        "notes": "Telegram deposit binary preserved; official provenance, type, reference, and boundaries require review",
                    })
                    canonical = prior_by_sha.get(file_sha)
                    duplicate_key = (str(post_id), file_sha)
                    if canonical and duplicate_key not in recorded_duplicate_keys:
                        new_binary_duplicates.append({
                            "duplicate_post_id": str(post_id),
                            "duplicate_storage_path": stored_path,
                            "duplicate_sha256": file_sha,
                            "canonical_post_id": canonical.get("post_id", ""),
                            "canonical_storage_path": canonical.get("storage_path", ""),
                            "detection_method": "sha256_exact_binary_match",
                            "disposition": "retain_each_received_original_and_route_duplicate_link_to_review",
                            "recorded_at": utc_now(),
                        })
                        recorded_duplicate_keys.add(duplicate_key)
                    recorded.add((str(post_id), file_sha))
                    prior_by_sha[file_sha] = acquired[-1]
                failed_ids.discard(post_id)
            except Exception as exc:
                failed_ids.add(post_id)
                new_failures.append({
                    "attempted_at": utc_now(), "telegram_channel": channel.lstrip("@"), "post_id": str(post_id),
                    "post_url": post_url, "status": "download_failed", "reason": f"{type(exc).__name__}: {exc}"[:1000],
                    "next_step": "retry with the same authorized account session; do not substitute another source binary",
                })
            finally:
                shutil.rmtree(temp_root, ignore_errors=True)
    finally:
        await client.disconnect()

    if apply:
        if acquired:
            write_csv(REGISTER, REGISTER_HEADER, prior_rows + acquired)
        if new_failures:
            write_csv(FAILURES, FAILURE_HEADER, failures + new_failures)
        if new_binary_duplicates:
            write_csv(BINARY_DUPLICATES, BINARY_DUPLICATE_HEADER, binary_duplicates + new_binary_duplicates)
        write_state(state_path, {"last_scanned_post_id": latest_seen, "failed_post_ids": sorted(failed_ids)})
    return {
        "status": "completed" if not new_failures else "completed_with_failures",
        "channel": channel.lstrip("@"), "new_binaries_preserved": len(acquired),
        "new_failures": len(new_failures), "new_exact_binary_duplicates": len(new_binary_duplicates), "last_scanned_post_id": latest_seen,
        "pending_retry_post_ids": sorted(failed_ids), "applied": apply,
        "public_search_enabled": False, "platform_database_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", default=DEFAULT_CHANNEL)
    parser.add_argument("--session", type=Path, default=SESSION_DEFAULT)
    parser.add_argument("--state", type=Path, default=STATE_DEFAULT)
    parser.add_argument("--limit", type=int, default=None, help="Maximum newly scanned messages; omit for all messages after cursor")
    parser.add_argument("--from-post-id", type=int, help="Explicit lower bound for a bounded historical import; never guessed")
    parser.add_argument(
        "--max-file-bytes", type=int,
        default=int(os.environ.get("TELEGRAM_MAX_FILE_BYTES", "262144000")),
        help="Hard ceiling per attachment; oversize files are logged for manual archival, never partially downloaded.",
    )
    parser.add_argument("--bootstrap-latest", action="store_true", help="Set cursor to the latest post without downloading history")
    parser.add_argument("--authorize", action="store_true", help="One-time interactive account authorization")
    parser.add_argument("--apply", action="store_true", help="Write preserved originals, registers, and cursor")
    args = parser.parse_args()
    if args.authorize:
        asyncio.run(authorize(args.session))
        return
    if args.bootstrap_latest:
        result = asyncio.run(bootstrap(args.channel, args.session, args.state, args.apply))
    else:
        result = asyncio.run(pull(args.channel, args.session, args.state, args.limit, args.apply, args.from_post_id, args.max_file_bytes))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
