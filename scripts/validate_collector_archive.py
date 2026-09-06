#!/usr/bin/env python3
"""Validate the private collector archive without creating platform-import data."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIED = ROOT / "indices" / "collector" / "case-register.ndjson"
PENDING = ROOT / "indices" / "collector" / "pending-case-review.ndjson"
TELEGRAM = ROOT / "indices" / "collector" / "pending-telegram-sources.ndjson"
FILE_REGISTER = ROOT / "manifests" / "collector" / "judgment-file-register.csv"
TELEGRAM_SUMMARY = ROOT / "manifests" / "collector" / "telegram-inventory-summary.json"
REPORT = ROOT / "manifests" / "collector" / "validation-report.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_ndjson(path: Path) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    if not path.exists():
        return rows, [f"missing:{path.relative_to(ROOT)}"]
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            errors.append(f"blank_line:{path.relative_to(ROOT)}:{number}")
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_json:{path.relative_to(ROOT)}:{number}:{exc.msg}")
            continue
        if not isinstance(obj, dict):
            errors.append(f"non_object:{path.relative_to(ROOT)}:{number}")
            continue
        rows.append(obj)
    return rows, errors


def unique_values(rows: list[dict], field: str) -> int:
    return len(rows) - len({str(row.get(field, "")) for row in rows})


def main() -> None:
    verified, errors = read_ndjson(VERIFIED)
    pending, pending_errors = read_ndjson(PENDING)
    telegram, telegram_errors = read_ndjson(TELEGRAM)
    errors.extend(pending_errors + telegram_errors)

    all_cases = verified + pending
    source_hashes: dict[Path, str] = {}
    required_verified = (
        "id", "documentType", "title", "subject", "deedNumber", "decisionDate", "court",
        "sourceFile", "sourceChecksum", "file", "fileChecksum", "textChecksum", "archive",
    )
    for row in verified:
        missing = [field for field in required_verified if not row.get(field)]
        if missing:
            errors.append(f"verified_missing_required:{row.get('id')}:{','.join(missing)}")
        if row.get("reviewStatus") != "metadata_complete_auto_extracted":
            errors.append(f"verified_wrong_status:{row.get('id')}:{row.get('reviewStatus')}")

    for row in all_cases:
        archive = row.get("archive") or {}
        for field in ("originalSourceFile", "originalSourceChecksum", "originalStartPage", "originalEndPage"):
            if not archive.get(field):
                errors.append(f"missing_archive_link:{row.get('id')}:{field}")
        if archive.get("originalStartPage", 0) > archive.get("originalEndPage", 0):
            errors.append(f"invalid_page_range:{row.get('id')}")
        source_path = ROOT / "archive-sources" / "moj" / str(row.get("year")) / str(row.get("sourceFile"))
        if not source_path.exists() or source_path.read_bytes()[:4] != b"%PDF":
            errors.append(f"missing_or_invalid_original_source:{row.get('id')}:{source_path.relative_to(ROOT)}")
        else:
            source_checksum = source_hashes.setdefault(source_path, digest(source_path))
            if source_checksum != row.get("sourceChecksum"):
                errors.append(f"source_checksum_mismatch:{row.get('id')}")
            if source_checksum != archive.get("originalSourceChecksum"):
                errors.append(f"archive_source_checksum_mismatch:{row.get('id')}")
        relative = row.get("file")
        if not relative:
            errors.append(f"missing_case_pdf:{row.get('id')}")
            continue
        file_path = ROOT / relative
        if not file_path.exists() or file_path.read_bytes()[:4] != b"%PDF":
            errors.append(f"missing_or_invalid_case_pdf:{row.get('id')}:{relative}")
            continue
        if digest(file_path) != row.get("fileChecksum"):
            errors.append(f"case_pdf_checksum_mismatch:{row.get('id')}")

    for field in ("id", "textChecksum"):
        duplicates = unique_values(all_cases, field)
        if duplicates:
            errors.append(f"duplicate_{field}:{duplicates}")
    verified_ids = {str(row.get("id")) for row in verified}
    if verified_ids & {str(row.get("id")) for row in pending}:
        errors.append("verified_pending_overlap")

    # Every Telegram preview record remains unavailable to the legal search index.
    for row in telegram:
        if row.get("searchIndexEligibility") != "not_eligible":
            errors.append(f"telegram_eligible_without_verification:{row.get('postId')}")
        if row.get("binaryOriginalStatus") != "not_downloaded":
            errors.append(f"telegram_binary_status_unexpected:{row.get('postId')}")
    if TELEGRAM_SUMMARY.exists():
        telegram_summary = json.loads(TELEGRAM_SUMMARY.read_text(encoding="utf-8"))
        for snapshot in telegram_summary.get("snapshots", []):
            path = ROOT / str(snapshot.get("file", ""))
            if not path.exists():
                errors.append(f"missing_telegram_preview_snapshot:{snapshot.get('file')}")
                continue
            if path.stat().st_size != snapshot.get("bytes") or digest(path) != snapshot.get("sha256"):
                errors.append(f"telegram_preview_snapshot_checksum_mismatch:{snapshot.get('file')}")
    else:
        errors.append("missing:manifests/collector/telegram-inventory-summary.json")

    if not FILE_REGISTER.exists():
        errors.append("missing:manifests/collector/judgment-file-register.csv")
        file_rows = []
    else:
        with FILE_REGISTER.open(encoding="utf-8", newline="") as handle:
            file_rows = list(csv.DictReader(handle))
    if len(file_rows) != len(all_cases):
        errors.append(f"file_register_count_mismatch:{len(file_rows)}!={len(all_cases)}")

    report = {
        "status": "passed" if not errors else "failed",
        "scope": "private_collector_only",
        "platform_import_modified": False,
        "verified_case_records_ready_for_review": len(verified),
        "case_records_pending_review": len(pending),
        "case_pdfs": len(all_cases),
        "case_pdf_source_counts": dict(sorted(Counter(str(row.get("sourceFile")) for row in all_cases).items())),
        "pending_telegram_metadata_rows": len(telegram),
        "telegram_records_admitted_to_search": sum(1 for row in telegram if row.get("searchIndexEligibility") != "not_eligible"),
        "duplicate_ids": unique_values(all_cases, "id"),
        "duplicate_text_checksums": unique_values(all_cases, "textChecksum"),
        "errors": errors,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
