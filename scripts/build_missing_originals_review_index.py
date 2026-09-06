#!/usr/bin/env python3
"""Quarantine legal index records whose declared source PDFs are missing.

These records are never emitted as importable legal_documents because a
source_files foreign key must refer to a real, fingerprinted file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    ROOT / "indices" / "principle-precedent-register.ndjson",
    ROOT / "indices" / "specialized-case-register.ndjson",
]
OUTPUT = ROOT / "indices" / "target-schema" / "missing-originals-review"
BATCH = ROOT / "manifests" / "batches" / "missing-originals-legal-index-review-001.json"
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
TYPE_MAP = {
    "مبدأ قضائي": "principle",
    "سابقة قضائية": "precedent",
    "حكم قضائي": "judgment",
    "حكم قضائي دولي": "judgment",
}


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(DIGIT_TRANS)
    return re.sub(r"\s+", " ", BIDI.sub("", DIACRITICS.sub("", text)).replace("ـ", " ")).strip()


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_exists(filename: str) -> bool:
    return any((ROOT / base / filename).is_file() for base in ("archive-sources", "originals")) or any(
        (ROOT / base).exists() and next((ROOT / base).rglob(filename), None) is not None
        for base in ("archive-sources", "originals")
    )


def write_ndjson(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if args.replace:
        shutil.rmtree(OUTPUT, ignore_errors=True)
    raw: list[dict[str, object]] = []
    for path in INPUTS:
        raw.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    if len(raw) != 3700:
        raise SystemExit(f"Expected 3700 index records, found {len(raw)}")

    output: dict[str, list[dict[str, object]]] = defaultdict(list)
    source_reviews: dict[str, dict[str, object]] = {}
    ids: set[str] = set()
    hashes: set[str] = set()
    for row in raw:
        legacy_type = str(row["documentType"])
        document_type = TYPE_MAP.get(legacy_type)
        if not document_type:
            raise ValueError(f"Unsupported type: {legacy_type}")
        legacy_id = str(row["id"])
        if legacy_id in ids:
            raise ValueError(f"Duplicate record id: {legacy_id}")
        ids.add(legacy_id)
        source_file = str(row["sourceFile"])
        if source_exists(source_file):
            raise ValueError(f"Source unexpectedly exists; route separately: {source_file}")
        start_page = int(row["startPage"])
        end_page = int(row["endPage"])
        if start_page < 1 or end_page < start_page:
            raise ValueError(f"Invalid page range: {legacy_id}")
        fingerprint = content_hash(normalize("|".join([
            document_type, source_file, str(start_page), str(end_page), str(row.get("reference") or ""), str(row["title"])
        ])))
        if fingerprint in hashes:
            raise ValueError(f"Duplicate metadata fingerprint: {legacy_id}")
        hashes.add(fingerprint)
        normalized = {
            "legacy_id": legacy_id,
            "document_type": document_type,
            "legacy_document_type": legacy_type,
            "title": row["title"],
            "reference": row.get("reference"),
            "declared_original_source_file": source_file,
            "declared_source_page_start": start_page,
            "declared_source_page_end": end_page,
            "excluded_pages": row.get("excludedPages") or [],
            "metadata_fingerprint": fingerprint,
            "status": "review",
            "review_status": "declared_original_missing",
            "database_import_eligible": False,
            "legal_search_eligibility": False,
            "standalone_pdf_available": False,
        }
        output[document_type].append(normalized)
        source_reviews.setdefault(source_file, {
            "declared_original_source_file": source_file,
            "status": "missing",
            "review_status": "declared_original_not_physically_present",
            "database_import_eligible": False,
            "affected_records": 0,
            "document_types": [],
        })
        source_reviews[source_file]["affected_records"] = int(source_reviews[source_file]["affected_records"]) + 1
        source_reviews[source_file]["document_types"] = sorted(set(source_reviews[source_file]["document_types"] + [document_type]))

    write_ndjson(OUTPUT / "principles.ndjson", output["principle"])
    write_ndjson(OUTPUT / "precedents.ndjson", output["precedent"])
    write_ndjson(OUTPUT / "judgments.ndjson", output["judgment"])
    write_ndjson(OUTPUT / "source-review.ndjson", [source_reviews[key] for key in sorted(source_reviews)])
    summary = {
        "schema_version": "1.0",
        "batch_id": "missing-originals-legal-index-review-001",
        "batch_status": "review",
        "records": len(raw),
        "records_by_type": dict(sorted(Counter(TYPE_MAP[str(row["documentType"])] for row in raw).items())),
        "missing_declared_originals": len(source_reviews),
        "database_import_eligible": 0,
        "legal_search_eligible": 0,
        "standalone_document_files": 0,
        "notes": "Quarantined until each declared original is recovered and its registered SHA-256 is verified.",
    }
    BATCH.parent.mkdir(parents=True, exist_ok=True)
    BATCH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
