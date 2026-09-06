#!/usr/bin/env python3
"""Build circular records from the preserved legacy metadata export.

The export is not represented as an original circular.  Every record stays
review-only until the signed/original document is acquired and hashed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "manifests" / "exports" / "moj-circulars-metadata-20260906.ndjson"
OUTPUT = ROOT / "indices" / "target-schema" / "moj-circulars-review"
BATCH_DIR = ROOT / "manifests" / "batches"
EXPECTED = 339
EXPECTED_EXPORT_SHA = "92c83bfb64b5d1b6ada6c7ea7ba30f377a841749b9c0f2546d7ef006bcddf6a4"
NAMESPACE = uuid.UUID("417bfc7f-99a6-4d57-8c42-f70d74024d08")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(DIGIT_TRANS)
    return re.sub(r"\s+", " ", BIDI.sub("", DIACRITICS.sub("", text)).replace("ـ", " ")).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{value}"))


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
    if sha256_file(EXPORT) != EXPECTED_EXPORT_SHA:
        raise SystemExit("Circular metadata export checksum mismatch")
    raw = [json.loads(line) for line in EXPORT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(raw) != EXPECTED:
        raise SystemExit(f"Expected {EXPECTED} circular metadata rows, found {len(raw)}")

    source_id = stable_id("source", "moj-circular-portal")
    source_file_id = stable_id("source-file", EXPECTED_EXPORT_SHA)
    sources = [{
        "id": source_id,
        "name": "بوابة التعاميم بوزارة العدل",
        "source_type": "official_web_portal",
        "organization": "وزارة العدل السعودية",
        "url": "https://portaleservices.moj.gov.sa/TameemPortal/",
        "channel_url": None,
        "description": "Official circular portal; current batch comes from a preserved legacy database export and lacks signed originals.",
        "is_official": True,
        "review_status": "verified",
    }]
    source_files = [{
        "id": source_file_id,
        "source_id": source_id,
        "original_filename": EXPORT.name,
        "storage_path": str(EXPORT.relative_to(ROOT)),
        "original_url": None,
        "mime_type": "application/x-ndjson",
        "file_size": EXPORT.stat().st_size,
        "sha256": EXPECTED_EXPORT_SHA,
        "page_count": None,
        "acquisition_source": "legacy_production_database_export",
        "acquired_at": None,
        "processing_status": "review",
    }]

    documents: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    duplicates: list[dict[str, object]] = []
    first_by_exact: dict[str, str] = {}
    first_by_reference: dict[str, str] = {}
    ids: set[str] = set()
    for row in raw:
        portal_id = str(row["tameem_id"])
        document_id = stable_id("document", f"moj-circular:{portal_id}")
        if document_id in ids:
            raise ValueError(f"Duplicate UUID for portal id {portal_id}")
        ids.add(document_id)
        number = normalize(row["tameem_no"])
        hdate = normalize(row["hdate"])
        subject = normalize(row["subject"])
        body = str(row["body_text"] or "")
        exact_key = sha256_text(normalize(f"{number}|{hdate}|{body}"))
        reference_key = normalize(f"{number}|{hdate}")
        exact_canonical = first_by_exact.get(exact_key)
        reference_canonical = first_by_reference.get(reference_key)
        status = "duplicate" if exact_canonical else "review"
        review_status = "exact_duplicate_confirmed" if exact_canonical else "original_document_missing"
        documents.append({
            "id": document_id,
            "document_type": "circular",
            "category": "administrative",
            "subcategory": subject or "general",
            "title": f"تعميم رقم {number} — {subject}",
            "document_number": number,
            "case_number": None,
            "judgment_number": None,
            "decision_number": None,
            "circular_number": number,
            "court": None,
            "circuit": None,
            "issuing_authority": "وزارة العدل السعودية",
            "document_date": None,
            "hijri_date": hdate,
            "year": normalize(row["hdate_year"]),
            "subject": subject,
            "summary": None,
            "facts": None,
            "claims": None,
            "reasoning": None,
            "ruling": None,
            "principle_text": None,
            "full_text": body,
            "legal_articles": [],
            "source_id": source_id,
            "source_file_id": source_file_id,
            "source_page_start": None,
            "source_page_end": None,
            "original_source": "وزارة العدل السعودية — بوابة التعاميم",
            "acquisition_source": "legacy_production_database_export; official_portal_record",
            "source_url": row["source_url"],
            "content_hash": sha256_text(body),
            "normalized_text_hash": exact_key,
            "status": status,
            "review_status": review_status,
            "legal_search_eligibility": False,
            "legacy_id": row["id"],
            "portal_id": row["tameem_id"],
            "legacy_status": row["status"],
            "related_tameem_ids": row["related_tameem_ids"],
        })
        review_rows.append({
            "document_id": document_id,
            "portal_id": row["tameem_id"],
            "source_url": row["source_url"],
            "review_status": review_status,
            "reasons": ["signed_original_missing", "portal_text_may_be_truncated"],
            "decision": "review" if not exact_canonical else "duplicate",
        })
        if exact_canonical:
            duplicates.append({
                "id": stable_id("duplicate-candidate", f"{document_id}:exact"),
                "document_id": document_id,
                "matched_document_id": exact_canonical,
                "matched_external_id": None,
                "match_type": "exact_hash",
                "similarity_score": 1,
                "decision": "duplicate",
                "reason": "Normalized circular number, date, and portal body are identical.",
            })
        elif reference_canonical:
            duplicates.append({
                "id": stable_id("duplicate-candidate", f"{document_id}:reference"),
                "document_id": document_id,
                "matched_document_id": reference_canonical,
                "matched_external_id": None,
                "match_type": "same_document_number",
                "similarity_score": None,
                "decision": "review",
                "reason": "Same circular number and Hijri date but different portal body or subject.",
            })
        first_by_exact.setdefault(exact_key, document_id)
        first_by_reference.setdefault(reference_key, document_id)

    write_ndjson(OUTPUT / "sources.ndjson", sources)
    write_ndjson(OUTPUT / "source-files.ndjson", source_files)
    write_ndjson(OUTPUT / "legal-documents.ndjson", documents)
    write_ndjson(OUTPUT / "document-files.ndjson", [])
    write_ndjson(OUTPUT / "field-review.ndjson", review_rows)
    write_ndjson(OUTPUT / "duplicate-candidates.ndjson", duplicates)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "1.0",
        "batch_id": "moj-circular-metadata-review-001",
        "batch_status": "review",
        "source_file_count": 1,
        "metadata_records": len(documents),
        "documents_by_type": {"circular": len(documents)},
        "exact_duplicates": sum(1 for row in documents if row["status"] == "duplicate"),
        "duplicate_candidates": len(duplicates),
        "original_document_files": 0,
        "standalone_document_files": 0,
        "originals_missing": len(documents),
        "legal_search_eligible": 0,
        "public_downloads_enabled": False,
        "failed_count": 0,
    }
    (BATCH_DIR / "moj-circular-metadata-review-001.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
