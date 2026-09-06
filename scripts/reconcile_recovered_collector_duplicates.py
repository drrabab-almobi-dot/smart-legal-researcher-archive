#!/usr/bin/env python3
"""Route recovered MOJ records duplicated by the current collector into review.

A duplicate is confirmed only when an existing collector record has the identical
immutable source checksum, source filename, original page span, and normalized
text checksum. Derived PDFs are retained unchanged and are moved only from the
recovered review index into the recovered duplicate register.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CURRENT = (
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
)
RECOVERED_INDEX = ROOT / "indices" / "collector" / "recovered-case-review.ndjson"
FILE_REGISTER = ROOT / "manifests" / "collector" / "recovered-judgment-file-register.csv"
DUPLICATES = ROOT / "manifests" / "collector" / "recovered-case-duplicates.csv"
PENDING_DUPLICATES = ROOT / "manifests" / "collector" / "recovered-pending-case-duplicates.csv"
PROCESSING = ROOT / "manifests" / "collector" / "recovered-processing-log.csv"
SUMMARY = ROOT / "manifests" / "collector" / "recovered-judgment-summary.json"
AUDIT = ROOT / "manifests" / "audit" / "recovered-current-duplicate-reconciliation-20260906T1542+0300.json"


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def key(row: dict[str, Any]) -> tuple[str, str, int, int, str]:
    archive = row.get("archive") or {}
    return (
        str(row.get("sourceFile") or ""),
        str(row.get("sourceChecksum") or ""),
        int(archive.get("originalStartPage") or 0),
        int(archive.get("originalEndPage") or 0),
        str(row.get("textChecksum") or ""),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write reconciled index and review registers.")
    args = parser.parse_args()

    current = [row for path in CURRENT for row in read_ndjson(path)]
    recovered = read_ndjson(RECOVERED_INDEX)
    if len({str(row["id"]) for row in current}) != len(current):
        raise SystemExit("Current collector IDs are not unique")
    if len({str(row["id"]) for row in recovered}) != len(recovered):
        raise SystemExit("Recovered collector IDs are not unique")

    current_by_key: dict[tuple[str, str, int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in current:
        current_by_key[key(row)].append(row)

    duplicate_map: dict[str, dict[str, Any]] = {}
    kept: list[dict[str, Any]] = []
    for row in recovered:
        matches = current_by_key.get(key(row), [])
        if len(matches) > 1:
            raise SystemExit(f"Ambiguous canonical duplicate for {row['id']}")
        if not matches:
            kept.append(row)
            continue
        canonical = matches[0]
        derived = ROOT / str(row["file"])
        if not derived.is_file() or sha256_file(derived) != row["fileChecksum"]:
            raise SystemExit(f"Recovered candidate file verification failed: {row['id']}")
        duplicate_map[str(row["id"])] = {
            "candidate_id": str(row["id"]),
            "candidate_file": str(row["file"]),
            "source_file": str(row["sourceFile"]),
            "start_page": str((row.get("archive") or {}).get("originalStartPage")),
            "end_page": str((row.get("archive") or {}).get("originalEndPage")),
            "file_sha256": str(row["fileChecksum"]),
            "text_sha256": str(row["textChecksum"]),
            "match_method": "exact_source_page_span_and_normalized_text",
            "canonical_id": str(canonical["id"]),
            "disposition": "candidate_file_retained_outside_search_index",
        }

    _, old_duplicates = read_csv(DUPLICATES)
    combined_duplicates = {row["candidate_id"]: row for row in old_duplicates}
    overlap = set(combined_duplicates) & set(duplicate_map)
    if overlap:
        raise SystemExit(f"Duplicate candidates already registered: {sorted(overlap)[:3]}")
    combined_duplicates.update(duplicate_map)

    register_fields, file_rows = read_csv(FILE_REGISTER)
    file_ids = {row["id"] for row in file_rows}
    recovered_ids = {str(row["id"]) for row in recovered}
    if file_ids != recovered_ids:
        raise SystemExit("Recovered file register does not cover recovered index")
    for row in file_rows:
        if row["id"] in duplicate_map:
            row["status"] = "exact_duplicate_review"

    pending_fields, pending_rows = read_csv(PENDING_DUPLICATES)
    remaining_pending = [row for row in pending_rows if row["candidate_id"] not in duplicate_map]

    processing_fields, processing_rows = read_csv(PROCESSING)
    kept_per_source = Counter(str(row["sourceFile"]) for row in kept)
    for row in processing_rows:
        if row.get("classification") == "materialized":
            row["review_records_added"] = str(kept_per_source.get(row["source_file"], 0))

    summary = {
        "schema_version": "1.0",
        "scope": "private_archive_recovered_moj_originals",
        "acquired_original_files": len(processing_rows),
        "judgment_codices": sum(row.get("classification") == "materialized" for row in processing_rows),
        "reference_only_codices": sum(row.get("classification") == "reference_only" for row in processing_rows),
        "boundary_records_examined": len(recovered),
        "standalone_pdf_files_preserved": len(file_rows),
        "review_records_added": len(kept),
        "exact_duplicate_candidates": len(combined_duplicates),
        "reference_collision_rows": len(remaining_pending),
        "records_by_type": {"judgment": len(kept)},
        "records_by_source_file": dict(sorted(kept_per_source.items())),
        "legal_search_eligible": 0,
        "public_downloads_enabled": False,
        "platform_database_modified": False,
        "deduplication_note": "Exact source checksum, page span, and normalized-text matches are retained as candidate PDFs and registered outside the search index.",
    }
    audit = {
        "schema_version": "1.0",
        "scope": "private_archive_cross_index_duplicate_reconciliation",
        "current_collector_records": len(current),
        "recovered_records_before": len(recovered),
        "confirmed_exact_source_page_text_duplicates": len(duplicate_map),
        "recovered_records_remaining_for_metadata_review": len(kept),
        "candidate_pdfs_retained": len(duplicate_map),
        "pending_reference_collisions_remaining": len(remaining_pending),
        "duplicates_by_source_file": dict(sorted(Counter(row["source_file"] for row in duplicate_map.values()).items())),
        "rule": "same immutable original checksum, same source page span, and same normalized text checksum",
        "search_eligible_records_created": 0,
        "originals_deleted": 0,
    }
    print(json.dumps({"summary": summary, "audit": audit}, ensure_ascii=False, indent=2))

    if not args.apply:
        return
    write_ndjson(RECOVERED_INDEX, kept)
    write_csv(DUPLICATES, [
        "candidate_id", "candidate_file", "source_file", "start_page", "end_page",
        "file_sha256", "text_sha256", "match_method", "canonical_id", "disposition",
    ], [combined_duplicates[key] for key in sorted(combined_duplicates)])
    write_csv(FILE_REGISTER, register_fields, file_rows)
    write_csv(PENDING_DUPLICATES, pending_fields, remaining_pending)
    write_csv(PROCESSING, processing_fields, processing_rows)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    AUDIT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
