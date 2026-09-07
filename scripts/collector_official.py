#!/usr/bin/env python3
"""Incremental collector for authorized official legal-source URLs.

Reads URLs from manifests/incoming/collector-official-urls.txt, downloads only
allow-listed official Saudi legal/government sources, hashes every payload,
keeps a durable checkpoint, prevents duplicate storage by SHA-256, and writes
an append-only processing log. It never scrapes albaheth.app or other third-
party platforms.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "manifests" / "incoming" / "collector-official-urls.txt"
CHECKPOINT = ROOT / "manifests" / "collector" / "official-checkpoint.json"
LOG = ROOT / "manifests" / "collector" / "official-processing-log.csv"
DUP = ROOT / "manifests" / "collector" / "official-duplicates.csv"
OUT = ROOT / "archive-sources" / "official-incremental"

ALLOWED_SUFFIXES = (
    "moj.gov.sa",
    "laws.moj.gov.sa",
    "bog.gov.sa",
    "saip.gov.sa",
    "uqn.gov.sa",
)

BATCH_LIMIT = int(os.environ.get("COLLECTOR_BATCH_LIMIT", "25"))
SLEEP_SECONDS = float(os.environ.get("COLLECTOR_SLEEP_SECONDS", "1.5"))
UA = "RababLegalArchive/1.0 (+authorized official-source archival)"


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(host == suffix or host.endswith("." + suffix) for suffix in ALLOWED_SUFFIXES)


def safe_name(url: str, idx: int, content_type: str) -> str:
    path = urlparse(url).path
    base = Path(path).name or f"record-{idx:06d}"
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.") or f"record-{idx:06d}"
    if "." not in base:
        if "pdf" in content_type.lower():
            base += ".pdf"
        else:
            base += ".html"
    return f"{idx:06d}-{base}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_checkpoint() -> dict:
    if CHECKPOINT.exists():
        return json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    return {"next_index": 0, "processed": 0, "saved": 0, "duplicates": 0, "failed": 0}


def save_checkpoint(cp: dict) -> None:
    CHECKPOINT.parent.mkdir(parents=True, exist_ok=True)
    CHECKPOINT.write_text(json.dumps(cp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_csv(path: Path, header: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(header)


def known_hashes() -> dict[str, str]:
    found: dict[str, str] = {}
    if LOG.exists():
        with LOG.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                h = row.get("sha256") or ""
                p = row.get("saved_path") or ""
                if h and p and row.get("status") == "saved":
                    found[h] = p
    return found


def main() -> int:
    if not INPUT.exists():
        print(f"Missing input manifest: {INPUT}", file=sys.stderr)
        return 2

    entries = [
        line.strip() for line in INPUT.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    cp = load_checkpoint()
    start = int(cp.get("next_index", 0))
    if start >= len(entries):
        print("Collector already caught up.")
        return 0

    ensure_csv(LOG, ["index","url","sha256","bytes","content_type","status","saved_path","note"])
    ensure_csv(DUP, ["index","url","sha256","canonical_path","decision"])
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = known_hashes()

    stop = min(len(entries), start + BATCH_LIMIT)
    for idx in range(start, stop):
        raw = entries[idx]
        url = raw.split("\t", 1)[0].strip()
        cp["processed"] = int(cp.get("processed", 0)) + 1

        if not host_allowed(url):
            with LOG.open("a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow([idx, url, "", 0, "", "rejected", "", "host not allow-listed"])
            cp["failed"] = int(cp.get("failed", 0)) + 1
            cp["next_index"] = idx + 1
            save_checkpoint(cp)
            continue

        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urlopen(req, timeout=90) as resp:
                data = resp.read()
                ctype = resp.headers.get("Content-Type", "application/octet-stream")
            digest = sha256_bytes(data)

            if digest in hashes:
                with DUP.open("a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([idx, url, digest, hashes[digest], "exclude duplicate; retain canonical"])
                with LOG.open("a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([idx, url, digest, len(data), ctype, "duplicate", "", hashes[digest]])
                cp["duplicates"] = int(cp.get("duplicates", 0)) + 1
            else:
                name = safe_name(url, idx, ctype)
                dest = OUT / name
                dest.write_bytes(data)
                rel = dest.relative_to(ROOT).as_posix()
                hashes[digest] = rel
                with LOG.open("a", encoding="utf-8", newline="") as f:
                    csv.writer(f).writerow([idx, url, digest, len(data), ctype, "saved", rel, "original payload preserved"])
                cp["saved"] = int(cp.get("saved", 0)) + 1

        except Exception as exc:
            with LOG.open("a", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow([idx, url, "", 0, "", "failed", "", type(exc).__name__])
            cp["failed"] = int(cp.get("failed", 0)) + 1

        cp["next_index"] = idx + 1
        save_checkpoint(cp)
        time.sleep(SLEEP_SECONDS)

    cp["remaining"] = max(0, len(entries) - int(cp.get("next_index", 0)))
    save_checkpoint(cp)
    print(json.dumps(cp, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
