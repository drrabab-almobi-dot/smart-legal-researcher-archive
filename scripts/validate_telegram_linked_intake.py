#!/usr/bin/env python3
"""Validate the review-only Telegram-linked OneDrive intake."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "manifests" / "collector" / "telegram-linked-file-register.csv"
PENDING = ROOT / "indices" / "collector" / "pending-telegram-linked-precedents.ndjson"
DUPLICATES = ROOT / "manifests" / "collector" / "telegram-linked-exact-text-duplicates.csv"
REFERENCES = ROOT / "manifests" / "collector" / "telegram-linked-reference-review.csv"
SUMMARY = ROOT / "manifests" / "collector" / "telegram-linked-import-summary.json"
OUTPUT = ROOT / "manifests" / "collector" / "telegram-linked-validation-report.json"
EXPECTED_NAMES = {
    "السوابق_نص_كامل.jsonl",
    "تقرير_المعالجة.csv",
    "فهرس_السوابق_القضائية.xlsx",
    "محرك_السوابق.html",
    "مواصفة_محرك_السوابق.md",
}
REQUIRED = {
    "id", "sourceChannel", "sourcePostId", "sourcePostUrl", "linkedPublicUrl",
    "linkedArtifactFile", "linkedArtifactSha256", "sourceFilenameAsRecorded",
    "textChecksum", "officialOriginalBinaryStatus", "officialSourceStatus",
    "pageRangeStatus", "reviewStatus", "searchIndexEligibility",
    "publicDownloadEligibility", "platformImportEligibility",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def load_ndjson(path: Path, errors: list[str]) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid_json:{path}:{number}:{exc}")
            continue
        if not isinstance(row, dict):
            errors.append(f"non_object:{path}:{number}")
            continue
        rows.append(row)
    return rows


def main() -> int:
    errors: list[str] = []
    file_rows = list(csv.DictReader(REGISTER.open(encoding="utf-8", newline="")))
    if {row["filename_as_received"] for row in file_rows} != EXPECTED_NAMES:
        errors.append("file_register_names_mismatch")
    for row in file_rows:
        path = ROOT / "originals" / "telegram-linked" / "robiai33" / "post-1302-onedrive" / row["filename_as_received"]
        if not path.is_file():
            errors.append(f"missing_preserved_file:{path}")
            continue
        if path.stat().st_size != int(row["bytes"]):
            errors.append(f"size_mismatch:{path}")
        if digest(path) != row["sha256"]:
            errors.append(f"sha256_mismatch:{path}")
        if row["search_eligibility"] != "not_eligible":
            errors.append(f"file_wrong_search_eligibility:{path}")
        if row["official_source_status"] != "unverified":
            errors.append(f"file_wrong_official_status:{path}")

    rows = load_ndjson(PENDING, errors)
    ids = [str(row.get("id") or "") for row in rows]
    missing_required = 0
    policy_errors = 0
    bad_hashes = 0
    for number, row in enumerate(rows, start=1):
        absent = REQUIRED - row.keys()
        if absent:
            missing_required += 1
            errors.append(f"missing_fields:{number}:{','.join(sorted(absent))}")
        if any(row.get(key) != "not_eligible" for key in (
            "searchIndexEligibility", "publicDownloadEligibility", "platformImportEligibility"
        )):
            policy_errors += 1
        if row.get("officialOriginalBinaryStatus") != "missing" or row.get("officialSourceStatus") != "unverified":
            policy_errors += 1
        text_hash = str(row.get("textChecksum") or "")
        if len(text_hash) != 64 or any(character not in "0123456789abcdef" for character in text_hash):
            bad_hashes += 1
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate_ids:{len(duplicate_ids)}")
    if policy_errors:
        errors.append(f"policy_errors:{policy_errors}")
    if bad_hashes:
        errors.append(f"bad_text_hashes:{bad_hashes}")

    duplicate_rows = list(csv.DictReader(DUPLICATES.open(encoding="utf-8", newline="")))
    reference_rows = list(csv.DictReader(REFERENCES.open(encoding="utf-8", newline="")))
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    if summary.get("unique_text_review_records") != len(rows):
        errors.append("summary_unique_text_record_count_mismatch")
    if summary.get("jsonl_records") != len(rows) + len(duplicate_rows):
        errors.append("summary_raw_record_count_mismatch")
    if summary.get("exact_text_duplicate_candidates") != len(duplicate_rows):
        errors.append("summary_duplicate_count_mismatch")
    if summary.get("reference_collision_candidates") != len(reference_rows):
        errors.append("summary_reference_count_mismatch")
    if any(summary.get(key) not in (0, False) for key in (
        "final_legal_records_added", "standalone_legal_pdfs_added",
        "search_eligible_records_added", "public_downloads_enabled",
        "platform_database_modified",
    )):
        errors.append("summary_policy_gate_mismatch")

    report = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "preserved_file_rows": len(file_rows),
        "nonempty_preserved_files": sum(int(row["bytes"]) > 0 for row in file_rows),
        "empty_preserved_files": [row["filename_as_received"] for row in file_rows if int(row["bytes"]) == 0],
        "raw_source_records": summary.get("jsonl_records"),
        "pending_unique_text_review_records": len(rows),
        "unique_ids": len(set(ids)),
        "records_missing_required_fields": missing_required,
        "bad_text_hashes": bad_hashes,
        "policy_errors": policy_errors,
        "exact_text_duplicate_candidates": len(duplicate_rows),
        "reference_collision_candidates": len(reference_rows),
        "final_legal_records_added": 0,
        "standalone_legal_pdfs_added": 0,
        "search_eligible_records_added": 0,
        "public_downloads_enabled": False,
        "platform_database_modified": False,
    }
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
