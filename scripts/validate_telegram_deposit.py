#!/usr/bin/env python3
"""Validate private outputs of the authorized Telegram deposit workflow."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "manifests" / "collector" / "telegram-deposit-file-register.csv"
RECORDS = ROOT / "indices" / "collector" / "pending-telegram-deposit-documents.ndjson"
DUPLICATES = ROOT / "manifests" / "collector" / "telegram-deposit-duplicates.csv"
BINARY_DUPLICATES = ROOT / "manifests" / "collector" / "telegram-deposit-binary-duplicates.csv"
PROCESSING = ROOT / "manifests" / "collector" / "telegram-deposit-processing-log.csv"
SUMMARY = ROOT / "manifests" / "collector" / "telegram-deposit-summary.json"
REPORT = ROOT / "manifests" / "collector" / "telegram-deposit-validation-report.json"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def csv_rows(path: Path, errors: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except csv.Error as exc:
        errors.append(f"invalid_csv:{path.relative_to(ROOT)}:{exc}")
        return []


def ndjson_rows(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            errors.append(f"blank_ndjson_line:{path.relative_to(ROOT)}:{line_number}")
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_ndjson:{path.relative_to(ROOT)}:{line_number}:{exc.msg}")
            continue
        if not isinstance(row, dict):
            errors.append(f"non_object_ndjson:{path.relative_to(ROOT)}:{line_number}")
            continue
        rows.append(row)
    return rows


def main() -> int:
    errors: list[str] = []
    rows = csv_rows(REGISTER, errors)
    records = ndjson_rows(RECORDS, errors)
    duplicates = csv_rows(DUPLICATES, errors)
    binary_duplicates = csv_rows(BINARY_DUPLICATES, errors)
    processing = csv_rows(PROCESSING, errors)
    summary: dict[str, Any] = {}
    if SUMMARY.exists():
        try:
            summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_json:{SUMMARY.relative_to(ROOT)}:{exc.msg}")
    elif rows or records:
        errors.append(f"missing:{SUMMARY.relative_to(ROOT)}")

    duplicate_pairs = {
        (str(row.get("duplicate_post_id") or ""), str(row.get("duplicate_sha256") or ""))
        for row in binary_duplicates
    }
    rows_by_post_sha = {(str(row.get("post_id") or ""), str(row.get("sha256") or "")): row for row in rows}
    known_sha: dict[str, str] = {}
    for row in rows:
        required = ("post_id", "post_url", "original_filename", "storage_path", "bytes", "sha256", "access_status", "binary_status", "official_source_status", "search_eligibility")
        missing = [key for key in required if not row.get(key)]
        if missing:
            errors.append(f"file_register_missing_fields:{row.get('post_id', '?')}:{','.join(missing)}")
            continue
        path = ROOT / row["storage_path"]
        if not path.is_file():
            errors.append(f"missing_original:{row['storage_path']}")
            continue
        if path.stat().st_size != int(row["bytes"]):
            errors.append(f"original_size_mismatch:{row['storage_path']}")
        actual = digest(path)
        if actual != row["sha256"]:
            errors.append(f"original_sha256_mismatch:{row['storage_path']}")
        if row["sha256"] in known_sha and known_sha[row["sha256"]] != row["storage_path"]:
            if (str(row.get("post_id") or ""), row["sha256"]) not in duplicate_pairs:
                errors.append(f"unrecorded_duplicate_original_sha256:{row['sha256']}")
        known_sha[row["sha256"]] = row["storage_path"]
        if row["search_eligibility"] != "not_eligible":
            errors.append(f"file_search_eligibility_violation:{row['storage_path']}")
        if row["official_source_status"] != "unverified":
            errors.append(f"file_official_status_violation:{row['storage_path']}")

    for row in binary_duplicates:
        required = (
            "duplicate_post_id", "duplicate_storage_path", "duplicate_sha256", "canonical_post_id",
            "canonical_storage_path", "detection_method", "disposition", "recorded_at",
        )
        missing = [key for key in required if not row.get(key)]
        if missing:
            errors.append(f"binary_duplicate_missing_fields:{row.get('duplicate_post_id', '?')}:{','.join(missing)}")
            continue
        duplicate = rows_by_post_sha.get((row["duplicate_post_id"], row["duplicate_sha256"]))
        canonical = rows_by_post_sha.get((row["canonical_post_id"], row["duplicate_sha256"]))
        if not duplicate or not canonical:
            errors.append(f"binary_duplicate_register_link_invalid:{row['duplicate_post_id']}")
            continue
        if duplicate.get("storage_path") != row["duplicate_storage_path"] or canonical.get("storage_path") != row["canonical_storage_path"]:
            errors.append(f"binary_duplicate_storage_link_invalid:{row['duplicate_post_id']}")

    ids = [str(row.get("id") or "") for row in records]
    text_hashes = [str(row.get("textChecksum") or "") for row in records]
    for row in records:
        required = ("id", "documentType", "sourcePath", "sourceChecksum", "textChecksum", "archive", "reviewStatus", "officialSourceStatus", "searchIndexEligibility", "publicDownloadEligibility", "platformImportEligibility")
        missing = [key for key in required if not row.get(key)]
        if missing:
            errors.append(f"record_missing_fields:{row.get('id', '?')}:{','.join(missing)}")
            continue
        source = ROOT / str(row["sourcePath"])
        if not source.is_file() or digest(source) != row["sourceChecksum"]:
            errors.append(f"record_source_link_invalid:{row['id']}")
        archive = row.get("archive") or {}
        start, end = archive.get("originalStartPage"), archive.get("originalEndPage")
        if not isinstance(start, int) or not isinstance(end, int) or start <= 0 or end < start:
            errors.append(f"record_page_range_invalid:{row['id']}")
        if any(row.get(key) != "not_eligible" for key in ("searchIndexEligibility", "publicDownloadEligibility", "platformImportEligibility")):
            errors.append(f"record_public_or_import_eligibility_violation:{row['id']}")
        if row.get("officialSourceStatus") != "unverified":
            errors.append(f"record_official_status_violation:{row['id']}")
        if len(str(row.get("textChecksum"))) != 64:
            errors.append(f"record_text_checksum_invalid:{row['id']}")
        derived = row.get("file")
        if derived:
            path = ROOT / str(derived)
            if not path.is_file() or path.read_bytes()[:4] != b"%PDF":
                errors.append(f"record_derived_pdf_missing_or_invalid:{row['id']}")
            elif digest(path) != row.get("fileChecksum") or path.stat().st_size != row.get("fileBytes"):
                errors.append(f"record_derived_pdf_integrity_mismatch:{row['id']}")
    duplicate_ids = [item for item, total in Counter(ids).items() if item and total > 1]
    duplicate_texts = [item for item, total in Counter(text_hashes).items() if item and total > 1]
    if duplicate_ids:
        errors.append(f"duplicate_ids:{len(duplicate_ids)}")
    # Duplicate text must be represented in the independent review register.
    duplicate_record_ids = {row.get("record_id") for row in duplicates}
    for item in duplicate_texts:
        matching = [row.get("id") for row in records if row.get("textChecksum") == item]
        if not all(str(identifier) in duplicate_record_ids for identifier in matching):
            errors.append(f"unregistered_duplicate_text_checksum:{item}")

    if summary:
        if summary.get("originals_registered") != len(rows):
            errors.append("summary_original_count_mismatch")
        if summary.get("new_review_records") is not None and summary.get("new_review_records") < 0:
            errors.append("summary_negative_records")
        if any(summary.get(key) not in (0, False) for key in ("search_eligible_records", "public_downloads_enabled", "platform_database_modified")):
            errors.append("summary_policy_gate_violation")

    report = {
        "status": "passed" if not errors else "failed",
        "scope": "authorized_telegram_deposit_private_review_only",
        "original_files_registered": len(rows), "records_in_private_review": len(records),
        "derived_private_pdfs": sum(1 for row in records if row.get("file")),
        "records_by_type": dict(sorted(Counter(str(row.get("documentTypeCode") or "unclassified_review") for row in records).items())),
        "duplicate_ids": len(duplicate_ids), "duplicate_text_checksums": len(duplicate_texts),
        "duplicate_review_rows": len(duplicates), "binary_duplicate_review_rows": len(binary_duplicates), "processing_rows": len(processing),
        "search_eligible_records": 0, "public_downloads_enabled": False, "platform_database_modified": False,
        "errors": errors,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
