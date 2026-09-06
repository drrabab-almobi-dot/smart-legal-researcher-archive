#!/usr/bin/env python3
"""Build a review-only batch of standalone SAIP decision/principle PDFs.

The historical source PDF is immutable.  Every derived PDF contains only the
pages recorded for one legacy record.  The batch is deliberately not eligible
for legal search until the source-checksum collision with the Nafa-derived
index has been reconciled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import unicodedata
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "archive-sources" / "saip" / "2019" / "saip-copyright-precedents-2019.pdf"
LEGACY_INDEX = ROOT / "legacy-artifacts" / "platform-main" / "indices" / "saip-copyright-index.json"
LEGACY_MANIFEST = ROOT / "legacy-artifacts" / "platform-main" / "manifests" / "saip-copyright-precedents-2019.json"
OUT_DIR = ROOT / "extracted" / "document-pdfs" / "saip-copyright-2019"
INDEX_DIR = ROOT / "indices" / "target-schema" / "saip-copyright-2019"
BATCH_DIR = ROOT / "manifests" / "batches"
EXPECTED_SOURCE_SHA = "a3a7f0680679198eaf58f7cc4a626aae60dd1d904dfbd2b4d3e2b846028088f2"
NAMESPACE = uuid.UUID("c5c9874e-2552-4a21-b3d4-d675b13d6bc2")
ALLOWED_TYPES = {"decision", "principle"}
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).translate(DIGIT_TRANS)
    text = BIDI.sub("", DIACRITICS.sub("", text)).replace("ـ", " ")
    return re.sub(r"\s+", " ", text).strip()


def text_hash(value: object) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def deterministic_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{value}"))


def classify(label: str) -> tuple[str, str, str, str]:
    if label == "قرار ملكية فكرية":
        return "decision", "intellectual_property", "copyright", "قرار-ملكية-فكرية"
    if label == "مبدأ قضائي دولي":
        return "principle", "judicial", "copyright_international", "مبدأ-قضائي-دولي"
    raise ValueError(f"Unsupported document type: {label}")


def first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, normalize_text(text), re.IGNORECASE)
    return normalize_text(match.group(1)) if match else None


def write_ndjson(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def extract_pdf(source: Path, start: int, end: int, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["qpdf", str(source), "--pages", ".", f"{start}-{end}", "--", str(output)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )


def pdf_page_count(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], check=True, capture_output=True, text=True
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to determine PDF page count: {path}")
    return int(match.group(1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true", help="Replace only this derived batch and its manifests")
    args = parser.parse_args()

    if shutil.which("qpdf") is None:
        raise SystemExit("qpdf is required")
    if sha256_file(SOURCE) != EXPECTED_SOURCE_SHA:
        raise SystemExit("Historical source SHA-256 mismatch; refusing to derive documents")

    legacy_manifest = json.loads(LEGACY_MANIFEST.read_text(encoding="utf-8"))
    legacy_records = json.loads(LEGACY_INDEX.read_text(encoding="utf-8"))
    if len(legacy_records) != 53:
        raise SystemExit(f"Expected 53 legacy records, found {len(legacy_records)}")
    if args.replace:
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        shutil.rmtree(INDEX_DIR, ignore_errors=True)

    actual_source_pages = pdf_page_count(SOURCE)
    source_id = deterministic_id("source", "saip-copyright-2019")
    source_file_id = deterministic_id("source-file", EXPECTED_SOURCE_SHA)
    source_record = {
        "id": source_id,
        "name": legacy_manifest["title"],
        "source_type": "government_publication",
        "organization": legacy_manifest["publishingAuthority"],
        "url": legacy_manifest["sourceUrl"],
        "channel_url": None,
        "description": "Historical source recovered byte-for-byte from the central repository main ref.",
        "is_official": None,
        "review_status": "review",
    }
    source_file_record = {
        "id": source_file_id,
        "source_id": source_id,
        "original_filename": SOURCE.name,
        "storage_path": str(SOURCE.relative_to(ROOT)),
        "original_url": legacy_manifest["sourceUrl"],
        "mime_type": "application/pdf",
        "file_size": SOURCE.stat().st_size,
        "sha256": EXPECTED_SOURCE_SHA,
        "page_count": actual_source_pages,
        "acquisition_source": "central_repository_origin_main; historical_google_drive_url",
        "acquired_at": None,
        "processing_status": "review",
    }

    documents: list[dict[str, object]] = []
    document_files: list[dict[str, object]] = []
    duplicate_candidates: list[dict[str, object]] = []
    used_names: set[str] = set()
    used_document_hashes: set[str] = set()

    for ordinal, legacy in enumerate(legacy_records, start=1):
        document_type, category, subcategory, filename_prefix = classify(str(legacy["documentType"]))
        if document_type not in ALLOWED_TYPES:
            raise AssertionError(document_type)
        start_page = int(legacy["startPage"])
        end_page = int(legacy["endPage"])
        boundary_adjustment = None
        if end_page == actual_source_pages + 1 and ordinal == len(legacy_records):
            boundary_adjustment = (
                f"legacy_end_page_{end_page}_clamped_to_actual_pdf_page_{actual_source_pages}"
            )
            end_page = actual_source_pages
        if not 1 <= start_page <= end_page <= actual_source_pages:
            raise ValueError(f"Invalid page range for {legacy['id']}: {start_page}-{end_page}")
        legacy_id = str(legacy["id"])
        document_id = deterministic_id("document", f"{EXPECTED_SOURCE_SHA}:{legacy_id}")
        document_file_id = deterministic_id("document-file", document_id)
        sequence = normalize_text(legacy.get("reference") or ordinal)
        filename = f"{filename_prefix}-رقم-{sequence}.pdf"
        if filename in used_names:
            raise ValueError(f"Duplicate output filename: {filename}")
        used_names.add(filename)
        output = OUT_DIR / filename
        extract_pdf(SOURCE, start_page, end_page, output)
        file_sha = sha256_file(output)
        full_text = str(legacy.get("searchText") or "")
        content_sha = text_hash(full_text)
        normalized_sha = text_hash(normalize_text(full_text))
        if normalized_sha in used_document_hashes:
            raise ValueError(f"Duplicate normalized text in source batch: {legacy_id}")
        used_document_hashes.add(normalized_sha)
        decision_number = first(r"(?:القرار\s*رقم|القراررقم)\s*[()]*\s*([0-9]+\s*/\s*[0-9]+)", full_text)
        hijri_date = first(r"\b(1[34][0-9]{2}\s*/\s*[0-9]{1,2}\s*/\s*[0-9]{1,2})\s*ه", full_text)
        subject = str(legacy.get("subject") or "").strip() or None
        document = {
            "id": document_id,
            "document_type": document_type,
            "category": category,
            "subcategory": subcategory,
            "title": legacy["title"],
            "document_number": None,
            "case_number": None,
            "judgment_number": None,
            "decision_number": decision_number if document_type == "decision" else None,
            "circular_number": None,
            "court": None,
            "circuit": None,
            "issuing_authority": legacy.get("originatingAuthority"),
            "document_date": None,
            "hijri_date": hijri_date,
            "year": hijri_date[:4] if hijri_date else None,
            "subject": subject,
            "summary": None,
            "facts": None,
            "claims": None,
            "reasoning": None,
            "ruling": None,
            "principle_text": full_text if document_type == "principle" else None,
            "full_text": full_text,
            "legal_articles": [],
            "source_id": source_id,
            "source_file_id": source_file_id,
            "source_page_start": start_page,
            "source_page_end": end_page,
            "original_source": legacy_manifest["publishingAuthority"],
            "acquisition_source": "central_repository_origin_main; historical_google_drive_url",
            "source_url": legacy_manifest["sourceUrl"],
            "content_hash": content_sha,
            "normalized_text_hash": normalized_sha,
            "status": "review",
            "review_status": "source_reconciliation_pending",
            "legal_search_eligibility": False,
            "legacy_id": legacy_id,
            "legacy_reference": legacy.get("reference"),
            "boundary_adjustment": boundary_adjustment,
        }
        document_file = {
            "id": document_file_id,
            "document_id": document_id,
            "file_type": "standalone_pdf",
            "storage_path": str(output.relative_to(ROOT)),
            "download_filename": filename,
            "mime_type": "application/pdf",
            "file_size": output.stat().st_size,
            "sha256": file_sha,
            "page_count": end_page - start_page + 1,
            "is_downloadable": False,
            "download_block_reason": "source_reconciliation_pending",
        }
        duplicate_candidate = {
            "id": deterministic_id("duplicate-candidate", document_id),
            "document_id": document_id,
            "matched_external_id": f"nafa-ip-copyright-2019-{ordinal:03d}",
            "match_type": "metadata_similarity",
            "similarity_score": None,
            "decision": "review",
            "reason": "Same publication and ordinal in Nafa-derived index, but source SHA-256 and record identifiers diverge.",
        }
        documents.append(document)
        document_files.append(document_file)
        duplicate_candidates.append(duplicate_candidate)

    write_ndjson(INDEX_DIR / "sources.ndjson", [source_record])
    write_ndjson(INDEX_DIR / "source-files.ndjson", [source_file_record])
    write_ndjson(INDEX_DIR / "legal-documents.ndjson", documents)
    write_ndjson(INDEX_DIR / "document-files.ndjson", document_files)
    write_ndjson(INDEX_DIR / "duplicate-candidates.ndjson", duplicate_candidates)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": "1.0",
        "batch_id": "saip-copyright-2019-review-001",
        "batch_status": "review",
        "platform_import_performed": False,
        "public_downloads_enabled": False,
        "source_file_sha256": EXPECTED_SOURCE_SHA,
        "source_file_count": 1,
        "documents_detected": len(documents),
        "documents_by_type": {
            "decision": sum(1 for record in documents if record["document_type"] == "decision"),
            "principle": sum(1 for record in documents if record["document_type"] == "principle"),
        },
        "standalone_document_files": len(document_files),
        "duplicate_candidates": len(duplicate_candidates),
        "review_count": len(documents),
        "legal_search_eligible": 0,
        "failed_count": 0,
        "boundary_adjustments": sum(1 for record in documents if record["boundary_adjustment"]),
        "notes": "Generated from recorded source page ranges. Held for source and duplicate reconciliation.",
    }
    (BATCH_DIR / "saip-copyright-2019-review-001.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
