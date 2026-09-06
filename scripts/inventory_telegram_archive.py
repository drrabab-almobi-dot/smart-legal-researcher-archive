#!/usr/bin/env python3
"""Inventory, but never legal-index, public Telegram archive attachments.

The public Telegram preview is an access layer, not an official legal source.  This
workflow preserves each fetched HTML preview as received, records attachment metadata,
and queues binaries for an authorised Telegram download session.  It intentionally never
adds Telegram-derived files to the legal search index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = "robiai33"
BASE_URL = f"https://t.me/s/{CHANNEL}"
RAW_DIR = ROOT / "originals" / "telegram-preview" / CHANNEL
MANIFEST_DIR = ROOT / "manifests" / "collector"
POST_REGISTER = MANIFEST_DIR / "telegram-source-register.csv"
ACQUISITION = MANIFEST_DIR / "telegram-acquisition-status.csv"
PENDING = ROOT / "indices" / "collector" / "pending-telegram-sources.ndjson"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; legal-archive-collector/1.0)"}
MESSAGE_RE = re.compile(
    r'<div class="tgme_widget_message[^>]*?data-post="(?P<post>[^"?#]+)(?:[^>]*)>(?P<body>.*?)(?=<div class="tgme_widget_message_wrap|</body>)',
    re.DOTALL,
)
DOCUMENT_RE = re.compile(
    r'<a class="tgme_widget_message_document_wrap" href="(?P<url>[^"]+)"[^>]*>.*?'
    r'<div class="tgme_widget_message_document_title[^>]*>(?P<title>.*?)</div>\s*'
    r'<div class="tgme_widget_message_document_extra[^>]*>(?P<size>.*?)</div>',
    re.DOTALL,
)
TIME_RE = re.compile(r'<time datetime="(?P<date>[^"]+)"', re.DOTALL)
FORWARD_RE = re.compile(
    r'tgme_widget_message_forwarded_from_name[^>]*>.*?<a href="(?P<url>[^"]+)"[^>]*>\s*(?P<name>.*?)\s*</a>',
    re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Attachment:
    post_id: int
    post_url: str
    filename: str
    display_size: str
    posted_at: str
    forwarded_from_name: str
    forwarded_from_url: str


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(TAG_RE.sub("", value))).strip()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def classification(filename: str) -> str:
    filename = filename.lower()
    if "فهرس" in filename or "index" in filename:
        return "فهرس/مدونة مرجعية غير مستقلة"
    if "تعميم" in filename:
        return "تعميم مرشح غير متحقق"
    if "قرار" in filename:
        return "قرار مرشح غير متحقق"
    if "صك" in filename:
        return "صك مرشح غير متحقق"
    if "حكم" in filename or "قضائ" in filename:
        return "حكم/مبدأ مرشح غير متحقق"
    return "مادة قانونية غير مصنفة وغير متحققة"


def fetch(url: str) -> bytes:
    request = Request(url, headers=HEADERS)
    with urlopen(request, timeout=60) as response:
        return response.read()


def parse(raw: str) -> list[Attachment]:
    attachments: list[Attachment] = []
    for message in MESSAGE_RE.finditer(raw):
        post_value = message.group("post")
        match = re.search(r"/(\d+)$", post_value)
        if not match:
            continue
        post_id = int(match.group(1))
        body = message.group("body")
        time_match = TIME_RE.search(body)
        forward_match = FORWARD_RE.search(body)
        for document in DOCUMENT_RE.finditer(body):
            attachments.append(Attachment(
                post_id=post_id,
                post_url=unescape(document.group("url")),
                filename=clean(document.group("title")),
                display_size=clean(document.group("size")),
                posted_at=time_match.group("date") if time_match else "",
                forwarded_from_name=clean(forward_match.group("name")) if forward_match else "",
                forwarded_from_url=unescape(forward_match.group("url")) if forward_match else "",
            ))
    return attachments


def message_ids(raw: str) -> list[int]:
    """Return every message boundary, including non-document posts.

    Telegram often places ordinary text and media posts between document posts.  Those
    messages still advance the `before` cursor, so pagination cannot be based solely
    on attachments.
    """
    ids = set()
    for value in re.findall(r'data-post="[^"/]+/(\d+)"', raw):
        ids.add(int(value))
    return sorted(ids)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-pages", type=int, default=150)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    PENDING.parent.mkdir(parents=True, exist_ok=True)

    all_attachments: dict[tuple[int, str], Attachment] = {}
    snapshots: list[dict[str, object]] = []
    before: int | None = None
    seen_minimums: set[int] = set()
    stopped_reason = "max_pages_reached"

    for page_no in range(1, args.max_pages + 1):
        query = "" if before is None else "?" + urlencode({"before": before})
        url = BASE_URL + query
        raw_bytes = fetch(url)
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        filename = f"page-{page_no:04d}" + ("-latest" if before is None else f"-before-{before}") + ".html"
        snapshot_path = RAW_DIR / filename
        snapshot_path.write_bytes(raw_bytes)
        parsed = parse(raw_text)
        post_ids = message_ids(raw_text)
        snapshots.append({
            "url": url,
            "file": snapshot_path.relative_to(ROOT).as_posix(),
            "bytes": len(raw_bytes),
            "sha256": sha256_bytes(raw_bytes),
            "attachment_count": len(parsed),
            "post_ids": post_ids,
        })
        for attachment in parsed:
            all_attachments[(attachment.post_id, attachment.filename)] = attachment
        if not post_ids:
            stopped_reason = "no_document_posts_returned"
            break
        next_before = min(post_ids)
        if next_before in seen_minimums:
            stopped_reason = "repeated_page_boundary"
            break
        seen_minimums.add(next_before)
        if before is not None and next_before >= before:
            stopped_reason = "non_decreasing_page_boundary"
            break
        before = next_before
        time.sleep(args.sleep_seconds)

    ordered = sorted(all_attachments.values(), key=lambda item: (item.post_id, item.filename))
    with POST_REGISTER.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([
            "telegram_channel", "post_id", "post_url", "filename_as_published", "display_size",
            "posted_at", "forwarded_from_name", "forwarded_from_url", "provisional_document_class",
            "binary_original_status", "official_source_status", "import_eligibility", "reason",
        ])
        for item in ordered:
            writer.writerow([
                CHANNEL, item.post_id, item.post_url, item.filename, item.display_size, item.posted_at,
                item.forwarded_from_name, item.forwarded_from_url, classification(item.filename),
                "not_downloaded", "unverified", "not_eligible",
                "Telegram preview supplies metadata only; download original and verify official provenance before indexing",
            ])
    with ACQUISITION.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["post_url", "filename_as_published", "status", "failure_or_next_step"])
        for item in ordered:
            writer.writerow([
                item.post_url, item.filename, "pending_authorized_download",
                "Telegram public preview has no binary download URL; use an authorised Telegram session, then preserve binary and SHA-256",
            ])
    with PENDING.open("w", encoding="utf-8") as handle:
        for item in ordered:
            record = {
                "sourceChannel": CHANNEL,
                "postId": item.post_id,
                "postUrl": item.post_url,
                "filenameAsPublished": item.filename,
                "displaySize": item.display_size,
                "postedAt": item.posted_at or None,
                "forwardedFrom": {"name": item.forwarded_from_name or None, "url": item.forwarded_from_url or None},
                "provisionalDocumentClass": classification(item.filename),
                "binaryOriginalStatus": "not_downloaded",
                "officialSourceStatus": "unverified",
                "searchIndexEligibility": "not_eligible",
                "reason": "Telegram preview metadata is not a legal final source; original binary and official provenance are required",
            }
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    report = {
        "channel": CHANNEL,
        "channel_preview_url": BASE_URL,
        "fetched_preview_pages": len(snapshots),
        "attachment_metadata_rows": len(ordered),
        "snapshots": snapshots,
        "stopped_reason": stopped_reason,
        "binaries_downloaded": 0,
        "records_admitted_to_legal_search_index": 0,
        "next_step": "authorised Telegram binary download followed by SHA-256, file integrity, type, reference, and official-source verification",
    }
    (MANIFEST_DIR / "telegram-inventory-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
