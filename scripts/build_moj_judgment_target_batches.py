#!/usr/bin/env python3
"""Transform verified collector judgment PDFs into strict target-schema batches.

Only records already routed to the collector review-ready register are handled.
Questionable court/circuit strings are set to null rather than propagated.
Every output remains review-only and non-downloadable in the public platform.
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
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "indices" / "collector" / "case-register.ndjson"
OUTPUT = ROOT / "indices" / "target-schema" / "moj-judgments-review"
BATCH_DIR = ROOT / "manifests" / "batches"
SOURCE_ROOT = ROOT / "archive-sources" / "moj"
NAMESPACE = uuid.UUID("d702a836-69be-486b-8c7f-cf6ee3a3b7f2")
EXPECTED_RECORDS = 191
ALLOWED_SOURCE_FILES = {
    "moj-judgments-1434-volume-1.pdf",
    "moj-judgments-1434-volume-2.pdf",
    "moj-judgments-1434-volume-5.pdf",
    "moj-judgments-1434-volume-11.pdf",
    "moj-judgments-1434-volume-13.pdf",
}
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


def extract_pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def pdf_page_count(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], check=True, capture_output=True, text=True
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to determine PDF page count: {path}")
    return int(match.group(1))


def stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{value}"))


def trustworthy_court(value: object) -> str | None:
    text = normalize(value)
    if re.fullmatch(r"(?:المحكمة|محكمة)\s+[^،؛]{3,100}", text) and not text.startswith("محكمة الاستئناف على"):
        return text
    return None


def trustworthy_circuit(value: object) -> str | None:
    text = normalize(value)
    if re.fullmatch(r"الدائرة\s+[^،؛]{2,70}", text):
        return text
    return None


def source_path(filename: str) -> Path:
    matches = list(SOURCE_ROOT.rglob(filename))
    if len(matches) != 1:
        raise ValueError(f"Expected one canonical source for {filename}, found {len(matches)}")
    return matches[0]


def write_ndjson(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace", action="store_true")
    parser.add_argument(
        "--all-verified",
        action="store_true",
        help="Build a review-only batch from every verified collector judgment. This never imports or activates search.",
    )
    args = parser.parse_args()
    if args.replace:
        shutil.rmtree(OUTPUT, ignore_errors=True)

    all_records = [json.loads(line) for line in INPUT.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.all_verified:
        raw = all_records
        batch_id = "moj-all-verified-judgments-review-002"
        batch_manifest = BATCH_DIR / "moj-all-verified-judgments-review-002.json"
        expected_sources = {item["sourceFile"] for item in raw}
    else:
        raw = [item for item in all_records if item["sourceFile"] in ALLOWED_SOURCE_FILES]
        batch_id = "moj-1434-five-volumes-review-001"
        batch_manifest = BATCH_DIR / "moj-1434-five-volumes-review-001.json"
        expected_sources = ALLOWED_SOURCE_FILES
        if len(raw) != EXPECTED_RECORDS:
            raise SystemExit(
                f"Expected {EXPECTED_RECORDS} records in the five-volume review batch, found {len(raw)}. "
                "Use --all-verified to create an expanded review-only batch explicitly."
            )
    if not raw:
        raise SystemExit("No verified collector records available")
    unexpected = sorted({item["sourceFile"] for item in raw} - expected_sources)
    if unexpected:
        raise SystemExit(f"Unexpected collector sources: {unexpected}")

    source_id = stable_id("source", "ministry-of-justice-saudi-judgments")
    source_record = {
        "id": source_id,
        "name": "مجموعات الأحكام القضائية المنشورة",
        "source_type": "government_publication",
        "organization": "وزارة العدل السعودية",
        "url": "https://www.moj.gov.sa/",
        "channel_url": None,
        "description": "Official Ministry of Justice judgment codices preserved in the private central archive.",
        "is_official": True,
        "review_status": "verified",
    }
    source_files: list[dict[str, object]] = []
    source_file_ids: dict[str, str] = {}
    source_sha_by_name: dict[str, str] = {}
    for filename in sorted(expected_sources):
        path = source_path(filename)
        digest = sha256_file(path)
        represented = {item["sourceChecksum"] for item in raw if item["sourceFile"] == filename}
        if represented != {digest}:
            raise ValueError(f"Source checksum mismatch for {filename}: {represented} != {digest}")
        source_file_id = stable_id("source-file", digest)
        source_file_ids[filename] = source_file_id
        source_sha_by_name[filename] = digest
        pages = pdf_page_count(path)
        source_files.append({
            "id": source_file_id,
            "source_id": source_id,
            "original_filename": filename,
            "storage_path": str(path.relative_to(ROOT)),
            "original_url": None,
            "mime_type": "application/pdf",
            "file_size": path.stat().st_size,
            "sha256": digest,
            "page_count": pages,
            "acquisition_source": "official_ministry_download_preserved_in_central_archive",
            "acquired_at": None,
            "processing_status": "processed",
        })

    documents: list[dict[str, object]] = []
    document_files: list[dict[str, object]] = []
    field_review: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    for item in raw:
        pdf_path = ROOT / item["file"]
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        if sha256_file(pdf_path) != item["fileChecksum"]:
            raise ValueError(f"Derived PDF checksum mismatch: {pdf_path}")
        full_text = extract_pdf_text(pdf_path)
        if not normalize(full_text):
            raise ValueError(f"No extractable text in standalone PDF: {pdf_path}")
        normalized_text = normalize(full_text)
        normalized_hash = sha256_text(normalized_text)
        if normalized_hash in seen_hashes:
            raise ValueError(f"Duplicate normalized text: {item['id']}")
        seen_hashes.add(normalized_hash)
        document_id = stable_id("document", f"{item['sourceChecksum']}:{item['id']}")
        if document_id in seen_ids:
            raise ValueError(f"Duplicate document UUID: {item['id']}")
        seen_ids.add(document_id)
        start_page = int(item["archive"]["originalStartPage"])
        end_page = int(item["archive"]["originalEndPage"])
        deed = normalize(item.get("deedNumber")) or None
        lawsuit = normalize(item.get("lawsuitNumber")) or None
        decision_date = normalize(item.get("decisionDate")) or None
        court = trustworthy_court(item.get("court"))
        circuit = trustworthy_circuit(item.get("circuit"))
        download_ref = deed or lawsuit or item["id"]
        download_filename = f"حكم-قضائي-رقم-{download_ref}.pdf"
        documents.append({
            "id": document_id,
            "document_type": "judgment",
            "category": "judicial",
            "subcategory": "general",
            "title": item["title"],
            "document_number": deed,
            "case_number": lawsuit,
            "judgment_number": normalize(item.get("judgmentNumber")) or None,
            "decision_number": None,
            "circular_number": None,
            "court": court,
            "circuit": circuit,
            "issuing_authority": "وزارة العدل السعودية",
            "document_date": None,
            "hijri_date": decision_date,
            "year": normalize(item.get("year")) or (decision_date[:4] if decision_date else None),
            "subject": item.get("subject"),
            "summary": None,
            "facts": None,
            "claims": None,
            "reasoning": None,
            "ruling": None,
            "principle_text": None,
            "full_text": full_text,
            "legal_articles": [],
            "source_id": source_id,
            "source_file_id": source_file_ids[item["sourceFile"]],
            "source_page_start": start_page,
            "source_page_end": end_page,
            "original_source": "وزارة العدل السعودية",
            "acquisition_source": "official_ministry_download_preserved_in_central_archive",
            "source_url": None,
            "content_hash": sha256_text(full_text),
            "normalized_text_hash": normalized_hash,
            "status": "review",
            "review_status": "manual_field_review_pending",
            "legal_search_eligibility": False,
            "legacy_id": item["id"],
        })
        document_files.append({
            "id": stable_id("document-file", document_id),
            "document_id": document_id,
            "file_type": "standalone_pdf",
            "storage_path": str(pdf_path.relative_to(ROOT)),
            "download_filename": download_filename,
            "mime_type": "application/pdf",
            "file_size": pdf_path.stat().st_size,
            "sha256": item["fileChecksum"],
            "page_count": int(item["pages"]),
            "is_downloadable": False,
            "download_block_reason": "manual_field_review_pending",
        })
        if court is None or circuit is None or not item.get("judgmentNumber"):
            field_review.append({
                "document_id": document_id,
                "legacy_id": item["id"],
                "source_file": item["sourceFile"],
                "missing_or_rejected_fields": [
                    name for name, missing in (
                        ("court", court is None),
                        ("circuit", circuit is None),
                        ("judgment_number", not bool(item.get("judgmentNumber"))),
                    ) if missing
                ],
                "original_court_candidate": item.get("court"),
                "original_circuit_candidate": item.get("circuit"),
                "decision": "review",
            })

    write_ndjson(OUTPUT / "sources.ndjson", [source_record])
    write_ndjson(OUTPUT / "source-files.ndjson", source_files)
    write_ndjson(OUTPUT / "legal-documents.ndjson", documents)
    write_ndjson(OUTPUT / "document-files.ndjson", document_files)
    write_ndjson(OUTPUT / "field-review.ndjson", field_review)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    by_source = Counter(item["sourceFile"] for item in raw)
    summary = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "batch_status": "review",
        "source_file_count": len(source_files),
        "documents_detected": len(documents),
        "documents_by_type": {"judgment": len(documents)},
        "documents_by_source_file": dict(sorted(by_source.items())),
        "standalone_document_files": len(document_files),
        "field_review_records": len(field_review),
        "legal_search_eligible": 0,
        "public_downloads_enabled": False,
        "failed_count": 0,
        "notes": "Questionable court/circuit values were not propagated; all rows remain review-only.",
    }
    batch_manifest.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
