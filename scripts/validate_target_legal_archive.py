#!/usr/bin/env python3
"""Validate all generated target-schema archive batches before publication."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "manifests" / "target-schema-validation.json"
IMPORTABLE_BATCHES = [
    ("saip", ROOT / "indices" / "target-schema" / "saip-copyright-2019", 53),
    ("moj_verified", ROOT / "indices" / "target-schema" / "moj-judgments-review", None),
    ("moj_pending", ROOT / "indices" / "target-schema" / "moj-judgments-pending-review", None),
    ("moj_circulars", ROOT / "indices" / "target-schema" / "moj-circulars-review", 339),
]
QUARANTINE = ROOT / "indices" / "target-schema" / "missing-originals-review"
COLLECTOR_VERIFIED = ROOT / "indices" / "collector" / "case-register.ndjson"
COLLECTOR_PENDING = ROOT / "indices" / "collector" / "pending-case-review.ndjson"


def read_ndjson(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid NDJSON {path}:{line_number}: {exc}") from exc
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    errors: list[str] = []
    all_documents: list[dict[str, object]] = []
    all_files: list[dict[str, object]] = []
    batch_summary: dict[str, object] = {}
    expected_by_batch = {
        "moj_verified": len(read_ndjson(COLLECTOR_VERIFIED)),
        "moj_pending": len(read_ndjson(COLLECTOR_PENDING)),
    }
    for name, directory, expected in IMPORTABLE_BATCHES:
        documents = read_ndjson(directory / "legal-documents.ndjson")
        files = read_ndjson(directory / "document-files.ndjson")
        expected = expected_by_batch.get(name, expected)
        if len(documents) != expected:
            errors.append(f"{name}: expected {expected} documents, found {len(documents)}")
        if name == "moj_circulars" and files:
            errors.append("moj_circulars: metadata-only records must not have document files")
        all_documents.extend(documents)
        all_files.extend(files)
        batch_summary[name] = {"documents": len(documents), "document_files": len(files)}

    ids = [str(row.get("id") or "") for row in all_documents]
    file_ids = [str(row.get("id") or "") for row in all_files]
    if len(ids) != len(set(ids)):
        errors.append("duplicate legal document UUID")
    if len(file_ids) != len(set(file_ids)):
        errors.append("duplicate document file UUID")
    document_ids = set(ids)
    if any(str(row.get("document_id")) not in document_ids for row in all_files):
        errors.append("orphan document file")
    if any(row.get("legal_search_eligibility") is not False for row in all_documents):
        errors.append("one or more records are unexpectedly search eligible")
    if any(not row.get("title") for row in all_documents):
        errors.append("one or more records have no title")
    allowed_types = {"judgment", "deed", "circular", "decision", "principle", "precedent", "blog_index"}
    if any(row.get("document_type") not in allowed_types for row in all_documents):
        errors.append("invalid document type")

    file_hash_errors = 0
    for row in all_files:
        path = ROOT / str(row["storage_path"])
        if not path.is_file() or sha256_file(path) != row["sha256"]:
            file_hash_errors += 1
        if row.get("is_downloadable") is not False:
            errors.append(f"public download unexpectedly enabled: {row.get('id')}")
    if file_hash_errors:
        errors.append(f"{file_hash_errors} missing or checksum-invalid standalone files")

    quarantined = []
    for filename in ("principles.ndjson", "precedents.ndjson", "judgments.ndjson"):
        quarantined.extend(read_ndjson(QUARANTINE / filename))
    if len(quarantined) != 3700:
        errors.append(f"expected 3700 quarantined records, found {len(quarantined)}")
    if any(row.get("database_import_eligible") is not False for row in quarantined):
        errors.append("quarantined record marked database import eligible")
    source_review = read_ndjson(QUARANTINE / "source-review.ndjson")
    if len(source_review) != 5:
        errors.append(f"expected 5 missing original sources, found {len(source_review)}")

    report = {
        "valid": not errors,
        "errors": errors,
        "target_documents": len(all_documents),
        "documents_by_type": dict(sorted(Counter(str(row["document_type"]) for row in all_documents).items())),
        "documents_by_status": dict(sorted(Counter(str(row["status"]) for row in all_documents).items())),
        "document_files": len(all_files),
        "document_file_hash_errors": file_hash_errors,
        "quarantined_missing_original_records": len(quarantined),
        "quarantined_by_type": dict(sorted(Counter(str(row["document_type"]) for row in quarantined).items())),
        "missing_original_sources": len(source_review),
        "batch_summary": batch_summary,
        "legal_search_eligible": 0,
        "public_downloads_enabled": 0,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
