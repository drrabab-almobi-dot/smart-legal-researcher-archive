#!/usr/bin/env python3
"""Materialize standalone case PDFs for newly recovered MOJ codices.

The script reuses only page boundaries and metadata already recorded in
``indices/case-register.ndjson``. It never invents metadata, never modifies an
original PDF, keeps every derived duplicate candidate, and routes every new
record to a private review-only index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_INDEX = ROOT / "indices" / "case-register.ndjson"
EXISTING_COLLECTOR = [
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
]
OUTPUT_DIR = ROOT / "extracted" / "recovered-moj-judgments-pdf"
STAGING_DIR = ROOT / "extracted" / ".recovered-moj-judgments-pdf.staging"
INDEX = ROOT / "indices" / "collector" / "recovered-case-review.ndjson"
FILE_REGISTER = ROOT / "manifests" / "collector" / "recovered-judgment-file-register.csv"
DUPLICATES = ROOT / "manifests" / "collector" / "recovered-case-duplicates.csv"
PENDING_DUPLICATES = ROOT / "manifests" / "collector" / "recovered-pending-case-duplicates.csv"
PROCESSING = ROOT / "manifests" / "collector" / "recovered-processing-log.csv"
SUMMARY = ROOT / "manifests" / "collector" / "recovered-judgment-summary.json"
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")
REFERENCE_ONLY = {"moj-judgments-1434-volume-30.pdf"}


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def pdf_pages(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, errors="ignore", check=False
    )
    match = re.search(r"^Pages:\s*(\d+)", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to read PDF page count: {path}")
    return int(match.group(1))


def page_texts(path: Path, page_count: int) -> list[str]:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        errors="ignore",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftotext failed for {path}: {result.stderr[:300]}")
    pieces = result.stdout.split("\f")
    if len(pieces) > page_count:
        pieces = pieces[:page_count]
    if len(pieces) < page_count:
        pieces.extend([""] * (page_count - len(pieces)))
    return pieces


def make_pdf(source: Path, start: int, end: int, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="case-", suffix=".pdf", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        result = subprocess.run(
            ["qpdf", "--empty", "--pages", str(source), f"{start}-{end}", "--", str(temporary)],
            capture_output=True,
            text=True,
            errors="ignore",
            check=False,
        )
        if result.returncode != 0 or temporary.stat().st_size < 100 or temporary.read_bytes()[:4] != b"%PDF":
            raise RuntimeError((result.stderr or result.stdout or "qpdf_failed")[:500])
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_ndjson(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_ndjson_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def write_csv_atomic(path: Path, header: list[str], rows: list[list[object]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acquisition-csv", type=Path, required=True)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    if shutil.which("qpdf") is None:
        raise SystemExit("qpdf is required")
    if OUTPUT_DIR.exists() and not args.replace:
        raise SystemExit(f"Output exists: {OUTPUT_DIR}; use --replace for a deliberate rebuild")

    with args.acquisition_csv.open(encoding="utf-8", newline="") as handle:
        acquisition_rows = list(csv.DictReader(handle))
    acquired = {row["source_file"]: row for row in acquisition_rows if row["status"] == "acquired"}
    if not acquired:
        raise SystemExit("No newly acquired source rows found")

    source_paths: dict[str, Path] = {}
    for name, acquisition in acquired.items():
        matches = list((ROOT / "archive-sources" / "moj").rglob(name))
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one recovered source for {name}, found {len(matches)}")
        source = matches[0]
        actual = sha256_file(source)
        if actual != acquisition["actual_sha256"] or actual != acquisition["expected_sha256"]:
            raise ValueError(f"Source checksum mismatch for {name}")
        source_paths[name] = source

    legacy = read_ndjson(LEGACY_INDEX)
    candidates = [row for row in legacy if str(row.get("sourceFile")) in acquired]
    represented_sources = {str(row["sourceFile"]) for row in candidates}
    expected_judgment_sources = set(acquired) - REFERENCE_ONLY
    if represented_sources != expected_judgment_sources:
        raise ValueError(
            f"Recovered source/index mismatch: records={sorted(represented_sources)}, "
            f"expected={sorted(expected_judgment_sources)}"
        )

    existing_rows: list[dict[str, object]] = []
    for path in EXISTING_COLLECTOR:
        existing_rows.extend(read_ndjson(path))
    seen_ids = {str(row["id"]): str(row["id"]) for row in existing_rows}
    seen_file_hashes = {
        str(row["fileChecksum"]): str(row["id"])
        for row in existing_rows
        if row.get("fileChecksum")
    }
    seen_text_hashes = {
        str(row["textChecksum"]): str(row["id"])
        for row in existing_rows
        if row.get("textChecksum")
    }
    references: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in existing_rows:
        for field in ("deedNumber", "judgmentNumber", "lawsuitNumber"):
            value = normalise(row.get(field))
            if value:
                references[(field, value)].add(str(row["id"]))

    source_pages: dict[str, int] = {}
    source_text: dict[str, list[str]] = {}
    for name, source in sorted(source_paths.items()):
        count = pdf_pages(source)
        source_pages[name] = count
        source_text[name] = page_texts(source, count)

    shutil.rmtree(STAGING_DIR, ignore_errors=True)
    STAGING_DIR.mkdir(parents=True)
    records: list[dict[str, object]] = []
    file_rows: list[list[object]] = []
    duplicate_rows: list[list[object]] = []
    pending_rows: list[list[object]] = []
    per_source: Counter[str] = Counter()
    failed = False
    try:
        for position, row in enumerate(candidates, start=1):
            source_name = str(row["sourceFile"])
            source = source_paths[source_name]
            archive = row.get("archive") or {}
            start = archive.get("originalStartPage")
            end = archive.get("originalEndPage")
            if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
                raise ValueError(f"Invalid page boundaries for {row.get('id')}: {start}-{end}")
            if end > source_pages[source_name]:
                raise ValueError(f"Page range exceeds source for {row.get('id')}: {end}")
            source_sha = sha256_file(source)
            if source_sha != row.get("sourceChecksum"):
                raise ValueError(f"Legacy source checksum mismatch for {row.get('id')}")
            candidate_id = "recovered-" + re.sub(r"[^A-Za-z0-9_-]", "-", str(row["id"]))
            if candidate_id in seen_ids:
                raise ValueError(f"Duplicate record id: {candidate_id}")
            destination = STAGING_DIR / f"{candidate_id}.pdf"
            make_pdf(source, start, end, destination)
            file_hash = sha256_file(destination)
            pages = pdf_pages(destination)
            expected_pages = end - start + 1
            if pages != expected_pages:
                raise ValueError(f"Derived page count mismatch for {candidate_id}: {pages} != {expected_pages}")
            extracted = subprocess.run(
                ["pdftotext", "-layout", str(destination), "-"],
                capture_output=True,
                text=True,
                errors="ignore",
                check=False,
            )
            if extracted.returncode != 0:
                raise RuntimeError(f"pdftotext failed for {candidate_id}")
            source_span = "\f".join(source_text[source_name][start - 1:end])
            text_hash = sha256_text(source_span)
            if sha256_text(extracted.stdout) != text_hash:
                raise ValueError(f"Derived PDF text differs from source page span: {candidate_id}")

            final_relpath = (OUTPUT_DIR / destination.name).relative_to(ROOT).as_posix()
            duplicate_method = ""
            canonical_id = ""
            if file_hash in seen_file_hashes:
                duplicate_method = "exact_file_sha256"
                canonical_id = seen_file_hashes[file_hash]
            elif text_hash in seen_text_hashes:
                duplicate_method = "exact_normalized_text"
                canonical_id = seen_text_hashes[text_hash]
            if duplicate_method:
                duplicate_rows.append([
                    candidate_id, final_relpath, source_name, start, end,
                    file_hash, text_hash, duplicate_method, canonical_id,
                    "candidate_file_retained_outside_search_index",
                ])
            else:
                missing = [
                    field for field in ("deedNumber", "judgmentNumber", "lawsuitNumber")
                    if not row.get(field)
                ]
                missing.extend(["court", "circuit", "decisionDate"])
                record: dict[str, object] = {
                    "id": candidate_id,
                    "legacyId": row["id"],
                    "documentType": "حكم قضائي",
                    "title": row.get("title") or None,
                    "subject": row.get("title") or None,
                    "deedNumber": row.get("deedNumber"),
                    "judgmentNumber": row.get("judgmentNumber"),
                    "lawsuitNumber": row.get("lawsuitNumber"),
                    "court": None,
                    "circuit": None,
                    "decisionDate": None,
                    "hijriDate": None,
                    "year": 1434,
                    "volume": row.get("volume"),
                    "issuingAuthority": "وزارة العدل السعودية",
                    "sourceUrl": acquisition_rows[[x["source_file"] for x in acquisition_rows].index(source_name)]["official_url"],
                    "officialSourceUrl": acquisition_rows[[x["source_file"] for x in acquisition_rows].index(source_name)]["official_url"],
                    "acquiredAt": acquisition_rows[[x["source_file"] for x in acquisition_rows].index(source_name)]["acquired_at"],
                    "sourceFile": source_name,
                    "sourcePath": source.relative_to(ROOT).as_posix(),
                    "sourceChecksum": source_sha,
                    "sourceBytes": source.stat().st_size,
                    "file": final_relpath,
                    "fileChecksum": file_hash,
                    "fileBytes": destination.stat().st_size,
                    "textChecksum": text_hash,
                    "pages": pages,
                    "reviewStatus": "recovered_original_pending_metadata_review",
                    "searchIndexEligibility": "not_eligible",
                    "missingRequiredMetadata": sorted(set(missing)),
                    "archive": {
                        "granularity": "case",
                        "originalSourceFile": source_name,
                        "originalSourceChecksum": source_sha,
                        "originalStartPage": start,
                        "originalEndPage": end,
                        "preservedOriginalPages": True,
                        "derivedPdfContainsOnlyOriginalPages": True,
                    },
                }
                records.append(record)
                seen_ids[candidate_id] = candidate_id
                seen_file_hashes[file_hash] = candidate_id
                seen_text_hashes[text_hash] = candidate_id
                for field in ("deedNumber", "judgmentNumber", "lawsuitNumber"):
                    value = normalise(record.get(field))
                    if value:
                        related = sorted(references[(field, value)])
                        if related:
                            record["reviewStatus"] = "reference_collision_pending_review"
                            record["missingRequiredMetadata"] = sorted(
                                set(record["missingRequiredMetadata"]) | {f"reference_collision:{field}"}
                            )
                            pending_rows.append([
                                candidate_id, source_name, start, end, field, value,
                                text_hash, "shared_reference_distinct_text_pending_review",
                                ";".join(related),
                            ])
                        references[(field, value)].add(candidate_id)
                per_source[source_name] += 1

            file_rows.append([
                candidate_id, final_relpath, source_name, source.relative_to(ROOT).as_posix(),
                source_sha, source.stat().st_size, start, end, pages, file_hash,
                destination.stat().st_size, text_hash,
                "exact_duplicate_review" if duplicate_method else "private_manual_review",
            ])
            if position % 100 == 0:
                print(f"processed={position}/{len(candidates)}", flush=True)
    except Exception:
        failed = True
        raise
    finally:
        if failed:
            shutil.rmtree(STAGING_DIR, ignore_errors=True)

    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    STAGING_DIR.replace(OUTPUT_DIR)
    write_ndjson_atomic(INDEX, records)
    write_csv_atomic(FILE_REGISTER, [
        "id", "file", "source_file", "source_path", "source_sha256", "source_bytes",
        "start_page", "end_page", "pages", "file_sha256", "file_bytes", "text_sha256", "status",
    ], file_rows)
    write_csv_atomic(DUPLICATES, [
        "candidate_id", "candidate_file", "source_file", "start_page", "end_page",
        "file_sha256", "text_sha256", "match_method", "canonical_id", "disposition",
    ], duplicate_rows)
    write_csv_atomic(PENDING_DUPLICATES, [
        "candidate_id", "source_file", "start_page", "end_page", "reference_field",
        "reference_value", "text_sha256", "reason", "related_record_ids",
    ], pending_rows)
    processing_rows = []
    for name, acquisition in sorted(acquired.items()):
        processing_rows.append([
            name, source_paths[name].relative_to(ROOT).as_posix(), acquisition["official_url"],
            acquisition["actual_sha256"], acquisition["actual_bytes"], acquisition["pages"],
            acquisition["acquired_at"], "reference_only" if name in REFERENCE_ONLY else "materialized",
            0 if name in REFERENCE_ONLY else sum(1 for row in candidates if row["sourceFile"] == name),
            per_source[name],
        ])
    write_csv_atomic(PROCESSING, [
        "source_file", "source_path", "official_url", "sha256", "bytes", "pages", "acquired_at",
        "classification", "boundary_records", "review_records_added",
    ], processing_rows)
    summary = {
        "schema_version": "1.0",
        "scope": "private_archive_recovered_moj_originals",
        "acquired_original_files": len(acquired),
        "judgment_codices": len(acquired) - len(set(acquired) & REFERENCE_ONLY),
        "reference_only_codices": len(set(acquired) & REFERENCE_ONLY),
        "boundary_records_examined": len(candidates),
        "standalone_pdf_files_preserved": len(file_rows),
        "review_records_added": len(records),
        "exact_duplicate_candidates": len(duplicate_rows),
        "reference_collision_rows": len(pending_rows),
        "records_by_type": {"judgment": len(records)},
        "records_by_source_file": dict(sorted(per_source.items())),
        "legal_search_eligible": 0,
        "public_downloads_enabled": False,
        "platform_database_modified": False,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
