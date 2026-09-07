#!/usr/bin/env python3
"""Transform all remaining standalone MOJ judgment PDFs into review-only records."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "indices" / "collector" / "pending-case-review.ndjson"
OUTPUT = ROOT / "indices" / "target-schema" / "moj-judgments-pending-review"
SOURCE_ROOT = ROOT / "archive-sources" / "moj"
BATCH_DIR = ROOT / "manifests" / "batches"
NAMESPACE = uuid.UUID("d702a836-69be-486b-8c7f-cf6ee3a3b7f2")
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


def stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{value}"))


def pdf_page_count(path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(path)], check=True, capture_output=True, text=True)
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to determine page count: {path}")
    return int(match.group(1))


def source_path(filename: str) -> Path:
    matches = list(SOURCE_ROOT.rglob(filename))
    if len(matches) != 1:
        raise ValueError(f"Expected one source file for {filename}, found {len(matches)}")
    return matches[0]


def write_ndjson(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--batch-id",
        default="moj-remaining-judgments-pending-review-001",
        help="Review-batch identifier; use a new revision for a regenerated collector snapshot.",
    )
    args = parser.parse_args()
    if args.replace:
        shutil.rmtree(OUTPUT, ignore_errors=True)
    rows = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise SystemExit("No pending collector records available")

    source_id = stable_id("source", "ministry-of-justice-saudi-judgments")
    sources = [{
        "id": source_id,
        "name": "مجموعات الأحكام القضائية المنشورة",
        "source_type": "government_publication",
        "organization": "وزارة العدل السعودية",
        "url": "https://www.moj.gov.sa/",
        "channel_url": None,
        "description": "Official Ministry of Justice judgment codices preserved in the private central archive.",
        "is_official": True,
        "review_status": "verified",
    }]

    filenames = sorted({row["sourceFile"] for row in rows})
    source_files: list[dict[str, object]] = []
    source_file_ids: dict[str, str] = {}
    for filename in filenames:
        path = source_path(filename)
        digest = sha256_file(path)
        represented = {row["sourceChecksum"] for row in rows if row["sourceFile"] == filename}
        if represented != {digest}:
            raise ValueError(f"Source checksum mismatch for {filename}")
        source_file_id = stable_id("source-file", digest)
        source_file_ids[filename] = source_file_id
        source_files.append({
            "id": source_file_id,
            "source_id": source_id,
            "original_filename": filename,
            "storage_path": str(path.relative_to(ROOT)),
            "original_url": None,
            "mime_type": "application/pdf",
            "file_size": path.stat().st_size,
            "sha256": digest,
            "page_count": pdf_page_count(path),
            "acquisition_source": "official_ministry_download_preserved_in_central_archive",
            "acquired_at": None,
            "processing_status": "review",
        })

    documents: list[dict[str, object]] = []
    document_files: list[dict[str, object]] = []
    review_rows: list[dict[str, object]] = []
    duplicate_candidates: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_file_hashes: set[str] = set()
    seen_text_hashes: set[str] = set()
    for row in rows:
        pdf = ROOT / row["file"]
        if not pdf.is_file():
            raise FileNotFoundError(pdf)
        actual_pdf_hash = sha256_file(pdf)
        if actual_pdf_hash != row["fileChecksum"]:
            raise ValueError(f"Derived PDF checksum mismatch: {pdf}")
        if actual_pdf_hash in seen_file_hashes:
            raise ValueError(f"Duplicate derived PDF hash: {pdf}")
        seen_file_hashes.add(actual_pdf_hash)
        if row["textChecksum"] in seen_text_hashes:
            raise ValueError(f"Duplicate text hash: {row['id']}")
        seen_text_hashes.add(row["textChecksum"])
        document_id = stable_id("document", f"{row['sourceChecksum']}:{row['id']}")
        if document_id in seen_ids:
            raise ValueError(f"Duplicate document UUID: {row['id']}")
        seen_ids.add(document_id)
        deed = normalize(row.get("deedNumber")) or None
        lawsuit = normalize(row.get("lawsuitNumber")) or None
        decision_date = normalize(row.get("decisionDate")) or None
        start_page = int(row["archive"]["originalStartPage"])
        end_page = int(row["archive"]["originalEndPage"])
        page_count = int(row["pages"])
        if page_count != end_page - start_page + 1:
            raise ValueError(f"Page span mismatch: {row['id']}")
        reference = deed or lawsuit or f"غير-محدد-{row['id']}"
        reasons = list(row.get("missingRequiredMetadata") or [])
        reasons.extend(["court_unverified", "circuit_unverified", "judgment_number_missing"])
        reasons = sorted(set(reasons))
        review_status = "reference_collision_pending_review" if row["reviewStatus"] == "reference_collision_pending_review" else "metadata_incomplete_pending_review"
        documents.append({
            "id": document_id,
            "document_type": "judgment",
            "category": "judicial",
            "subcategory": "general",
            "title": row["title"],
            "document_number": deed,
            "case_number": lawsuit,
            "judgment_number": None,
            "decision_number": None,
            "circular_number": None,
            "court": None,
            "circuit": None,
            "issuing_authority": "وزارة العدل السعودية",
            "document_date": None,
            "hijri_date": decision_date,
            "year": normalize(row.get("year")) or (decision_date[:4] if decision_date else None),
            "subject": row.get("subject"),
            "summary": None,
            "facts": None,
            "claims": None,
            "reasoning": None,
            "ruling": None,
            "principle_text": None,
            "full_text": None,
            "legal_articles": [],
            "source_id": source_id,
            "source_file_id": source_file_ids[row["sourceFile"]],
            "source_page_start": start_page,
            "source_page_end": end_page,
            "original_source": "وزارة العدل السعودية",
            "acquisition_source": "official_ministry_download_preserved_in_central_archive",
            "source_url": None,
            "content_hash": row["textChecksum"],
            "normalized_text_hash": row["textChecksum"],
            "status": "review",
            "review_status": review_status,
            "legal_search_eligibility": False,
            "legacy_id": row["id"],
        })
        document_files.append({
            "id": stable_id("document-file", document_id),
            "document_id": document_id,
            "file_type": "standalone_pdf",
            "storage_path": str(pdf.relative_to(ROOT)),
            "download_filename": f"حكم-قضائي-{reference}-ص{start_page}.pdf",
            "mime_type": "application/pdf",
            "file_size": pdf.stat().st_size,
            "sha256": actual_pdf_hash,
            "page_count": page_count,
            "is_downloadable": False,
            "download_block_reason": review_status,
        })
        review_rows.append({
            "document_id": document_id,
            "legacy_id": row["id"],
            "source_file": row["sourceFile"],
            "review_status": review_status,
            "reasons": reasons,
            "decision": "review",
        })
        for reason in row.get("missingRequiredMetadata") or []:
            if str(reason).startswith("reference_collision:"):
                field = str(reason).split(":", 1)[1]
                duplicate_candidates.append({
                    "id": stable_id("duplicate-candidate", f"{document_id}:{field}"),
                    "document_id": document_id,
                    "matched_external_id": f"{field}:{normalize(row.get(field))}",
                    "match_type": "same_case_number" if field == "lawsuitNumber" else "same_document_number",
                    "similarity_score": None,
                    "decision": "review",
                    "reason": f"Collector detected a non-conclusive {field} collision.",
                })

    write_ndjson(OUTPUT / "sources.ndjson", sources)
    write_ndjson(OUTPUT / "source-files.ndjson", source_files)
    write_ndjson(OUTPUT / "legal-documents.ndjson", documents)
    write_ndjson(OUTPUT / "document-files.ndjson", document_files)
    write_ndjson(OUTPUT / "field-review.ndjson", review_rows)
    write_ndjson(OUTPUT / "duplicate-candidates.ndjson", duplicate_candidates)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "1.0",
        "batch_id": args.batch_id,
        "batch_status": "review",
        "source_file_count": len(source_files),
        "documents_detected": len(documents),
        "documents_by_type": {"judgment": len(documents)},
        "documents_by_source_file": dict(sorted(Counter(row["sourceFile"] for row in rows).items())),
        "standalone_document_files": len(document_files),
        "field_review_records": len(review_rows),
        "duplicate_candidates": len(duplicate_candidates),
        "legal_search_eligible": 0,
        "public_downloads_enabled": False,
        "failed_count": 0,
    }
    (BATCH_DIR / f"{args.batch_id}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
