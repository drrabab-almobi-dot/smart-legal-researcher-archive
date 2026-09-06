#!/usr/bin/env python3
"""Validate the private recovered-MOJ archive batch end to end."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "manifests" / "audit" / "moj-official-source-check-20260906T1450+0300.csv"
INDEX = ROOT / "indices" / "collector" / "recovered-case-review.ndjson"
FILE_REGISTER = ROOT / "manifests" / "collector" / "recovered-judgment-file-register.csv"
DUPLICATES = ROOT / "manifests" / "collector" / "recovered-case-duplicates.csv"
PENDING_DUPLICATES = ROOT / "manifests" / "collector" / "recovered-pending-case-duplicates.csv"
PROCESSING = ROOT / "manifests" / "collector" / "recovered-processing-log.csv"
REPORT = ROOT / "manifests" / "collector" / "recovered-validation-report.json"
EXISTING = [
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
]
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")


def normalise(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(DIGITS)
    text = BIDI.sub("", DIACRITICS.sub("", text).replace("ـ", ""))
    return re.sub(r"\s+", " ", text).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        errors="ignore",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return hashlib.sha256(normalise(result.stdout).encode("utf-8")).hexdigest()


def pdf_pages(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, errors="ignore", check=False
    )
    match = re.search(r"^Pages:\s*(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 0


def read_ndjson(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    errors: list[str] = []
    acquisition = read_csv(ACQUISITION)
    acquired = {row["source_file"]: row for row in acquisition if row["status"] == "acquired"}
    if len(acquired) != 24:
        errors.append(f"acquired_original_count:{len(acquired)}")
    for name, row in acquired.items():
        matches = list((ROOT / "archive-sources" / "moj").rglob(name))
        if len(matches) != 1:
            errors.append(f"original_path_count:{name}:{len(matches)}")
            continue
        path = matches[0]
        if path.read_bytes()[:4] != b"%PDF":
            errors.append(f"original_not_pdf:{name}")
        if sha256_file(path) != row["actual_sha256"] or row["actual_sha256"] != row["expected_sha256"]:
            errors.append(f"original_sha256:{name}")
        if path.stat().st_size != int(row["actual_bytes"]):
            errors.append(f"original_bytes:{name}")
        if pdf_pages(path) != int(row["pages"]):
            errors.append(f"original_pages:{name}")

    records = read_ndjson(INDEX)
    files = read_csv(FILE_REGISTER)
    duplicates = read_csv(DUPLICATES)
    pending = read_csv(PENDING_DUPLICATES)
    processing = read_csv(PROCESSING)
    existing_rows: list[dict[str, object]] = []
    for path in EXISTING:
        existing_rows.extend(read_ndjson(path))

    ids = [str(row.get("id")) for row in records]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_recovered_ids")
    existing_ids = {str(row["id"]) for row in existing_rows}
    if existing_ids & set(ids):
        errors.append("recovered_id_collision_with_existing")
    existing_file_hashes = {str(row.get("fileChecksum")) for row in existing_rows if row.get("fileChecksum")}
    existing_text_hashes = {str(row.get("textChecksum")) for row in existing_rows if row.get("textChecksum")}

    file_by_id = {row["id"]: row for row in files}
    duplicate_by_id = {row["candidate_id"]: row for row in duplicates}
    if len(file_by_id) != len(files):
        errors.append("duplicate_file_register_ids")
    if set(file_by_id) != set(ids) | set(duplicate_by_id):
        errors.append("file_register_identity_coverage")

    seen_file_hashes: set[str] = set()
    seen_text_hashes: set[str] = set()
    for number, record in enumerate(records, start=1):
        identifier = str(record.get("id"))
        if record.get("documentType") != "حكم قضائي":
            errors.append(f"document_type:{identifier}")
        if record.get("searchIndexEligibility") != "not_eligible":
            errors.append(f"search_eligibility:{identifier}")
        if record.get("reviewStatus") not in {
            "recovered_original_pending_metadata_review", "reference_collision_pending_review"
        }:
            errors.append(f"review_status:{identifier}")
        original = ROOT / str(record.get("sourcePath"))
        derived = ROOT / str(record.get("file"))
        archive = record.get("archive") or {}
        start = archive.get("originalStartPage")
        end = archive.get("originalEndPage")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"page_range:{identifier}")
            continue
        if not original.is_file() or sha256_file(original) != record.get("sourceChecksum"):
            errors.append(f"source_file:{identifier}")
        if not derived.is_file() or derived.read_bytes()[:4] != b"%PDF":
            errors.append(f"standalone_file:{identifier}")
            continue
        file_hash = sha256_file(derived)
        text_hash = text_sha256(derived)
        if file_hash != record.get("fileChecksum"):
            errors.append(f"standalone_sha256:{identifier}")
        if text_hash != record.get("textChecksum"):
            errors.append(f"text_sha256:{identifier}")
        if derived.stat().st_size != int(record.get("fileBytes") or -1):
            errors.append(f"standalone_bytes:{identifier}")
        if pdf_pages(derived) != int(record.get("pages") or 0) or int(record.get("pages") or 0) != end - start + 1:
            errors.append(f"standalone_pages:{identifier}")
        if file_hash in existing_file_hashes or file_hash in seen_file_hashes:
            errors.append(f"unregistered_file_duplicate:{identifier}")
        if text_hash in existing_text_hashes or text_hash in seen_text_hashes:
            errors.append(f"unregistered_text_duplicate:{identifier}")
        seen_file_hashes.add(file_hash)
        seen_text_hashes.add(text_hash)
        manifest_row = file_by_id.get(identifier)
        if not manifest_row or manifest_row["file_sha256"] != file_hash or manifest_row["text_sha256"] != text_hash:
            errors.append(f"file_register_row:{identifier}")
        if number % 200 == 0:
            print(f"validated={number}/{len(records)}", flush=True)

    all_known_ids = existing_ids | set(ids)
    for row in duplicates:
        path = ROOT / row["candidate_file"]
        if not path.is_file() or sha256_file(path) != row["file_sha256"]:
            errors.append(f"duplicate_candidate_file:{row['candidate_id']}")
        if row["canonical_id"] not in all_known_ids:
            errors.append(f"duplicate_canonical_id:{row['candidate_id']}")
        if row["match_method"] not in {"exact_file_sha256", "exact_normalized_text"}:
            errors.append(f"duplicate_match_method:{row['candidate_id']}")
    for row in pending:
        if row["candidate_id"] not in set(ids):
            errors.append(f"pending_candidate_id:{row['candidate_id']}")
        for related in filter(None, row["related_record_ids"].split(";")):
            if related not in all_known_ids:
                errors.append(f"pending_related_id:{row['candidate_id']}:{related}")

    classifications = Counter(row["classification"] for row in processing)
    if classifications != Counter({"materialized": 23, "reference_only": 1}):
        errors.append(f"processing_classifications:{dict(classifications)}")
    reference_only = [row for row in processing if row["classification"] == "reference_only"]
    if len(reference_only) != 1 or reference_only[0]["source_file"] != "moj-judgments-1434-volume-30.pdf":
        errors.append("reference_only_volume")

    report = {
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "acquired_original_files": len(acquired),
        "review_records": len(records),
        "records_by_type": dict(Counter(str(row.get("documentType")) for row in records)),
        "standalone_pdf_files": len(files),
        "exact_duplicate_candidates": len(duplicates),
        "reference_collision_rows": len(pending),
        "duplicate_ids": 0 if len(ids) == len(set(ids)) else len(ids) - len(set(ids)),
        "duplicate_file_hashes": len(files) - len({row["file_sha256"] for row in files}),
        "duplicate_text_hashes": len(files) - len({row["text_sha256"] for row in files}),
        "reference_only_codices": classifications["reference_only"],
        "legal_search_eligible": 0,
        "public_downloads_enabled": 0,
        "platform_database_modified": False,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
