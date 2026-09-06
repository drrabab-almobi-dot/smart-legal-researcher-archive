#!/usr/bin/env python3
"""Extract official Ministry of Justice judgment pages into standalone PDF records.

The original PDF files are never modified.  Each accepted case receives a derived PDF
that contains only the source pages for that case and is linked to the immutable original
through its checksum and page range.  The script does not write to platform-import paths.
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
SOURCE_ROOT = ROOT / "archive-sources" / "moj"
OUT_DIR = ROOT / "extracted" / "collector-judgments-pdf"
INDEX = ROOT / "indices" / "collector" / "case-register.ndjson"
PENDING_INDEX = ROOT / "indices" / "collector" / "pending-case-review.ndjson"
MANIFEST_DIR = ROOT / "manifests" / "collector"
FILE_REGISTER = MANIFEST_DIR / "judgment-file-register.csv"
PROCESSING = MANIFEST_DIR / "processing-log.csv"
DUPLICATES = MANIFEST_DIR / "case-duplicates.csv"
PENDING_CASE_DUPLICATES = MANIFEST_DIR / "pending-case-duplicates.csv"
SOURCE_COUNTS = MANIFEST_DIR / "source-case-counts.csv"
SKIPPED = MANIFEST_DIR / "skipped-records.csv"
SUMMARY = MANIFEST_DIR / "judgment-summary.json"

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")
PAGE_NUMBER = re.compile(r"^\d{1,4}$")

DEED_PATTERNS = [
    re.compile(r"(?:ر\s*ق\s*م\s*)?(?:ال)?صك\s*[:：\-]?\s*([0-9/\-]{5,30})"),
    re.compile(r"ر\s*ق\s*م\s*(?:ال)?ص\s*ك\s*[:：\-]?\s*([0-9/\-]{5,30})"),
]
JUDGMENT_PATTERNS = [
    re.compile(r"(?:ر\s*ق\s*م\s*)?(?:ال)?حكم\s*[:：\-]?\s*([0-9/\-]{4,30})"),
]
LAWSUIT_PATTERNS = [
    re.compile(r"(?:ر\s*ق\s*م\s*)?(?:ال)?(?:دعوى|قضية)\s*[:：\-]?\s*([0-9/\-]{3,30})"),
]
DATE_PATTERNS = [
    re.compile(r"(?:تاريخ(?:ه)?|بتاريخ)\s*[:：\-]?\s*(1[34][0-9]{2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2})"),
    re.compile(r"(?:تاريخ(?:ه)?|بتاريخ)\s*[:：\-]?\s*([0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*1[34][0-9]{2})"),
    re.compile(r"(1[34][0-9]{2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2})\s*هـ?"),
    re.compile(r"([0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*1[34][0-9]{2})\s*هـ?"),
]

# A title must be sourced from the document rather than synthesized from the filename.
TITLE_REJECTS = (
    "رقم الصك", "رقم الحكم", "رقم الدعوى", "رقم القضية", "رقم قرار",
    "تاريخ", "تاريخه", "وزارة العدل", "المملكة العربية السعودية",
    "الحمد لله", "الحمد هلل", "فهرس", "الصفحة", "الفهارس",
    "مركز البحوث", "مجموعة الأحكام", "مجموعة األحكام",
)
REFERENCE_ONLY_SOURCE_FILENAMES = {
    # Confirmed against the source register and the original title/contents pages.
    "moj-judgments-1434-volume-29.pdf",
    "moj-judgments-1435-volume-14.pdf",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(DIGITS)
    value = BIDI.sub("", value)
    value = DIACRITICS.sub("", value).replace("ـ", "")
    return re.sub(r"\s+", " ", value).strip()


def output_relpath(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def pdf_pages(path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(path)], capture_output=True, text=True, errors="ignore", check=False
    )
    match = re.search(r"^Pages:\s*(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else 0


def source_page_texts(path: Path, pages: int) -> list[str]:
    """Extract once and retain exact page boundaries supplied by pdftotext."""
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
        errors="ignore",
        check=False,
    )
    pieces = result.stdout.split("\f")
    # pdftotext commonly emits one trailing empty chunk.
    if len(pieces) > pages:
        pieces = pieces[:pages]
    if len(pieces) < pages:
        pieces.extend([""] * (pages - len(pieces)))
    return pieces


def first_match(patterns: list[re.Pattern[str]], text: str) -> str | None:
    cleaned = normalise(text)
    for pattern in patterns:
        match = pattern.search(cleaned)
        if match:
            return normalise(match.group(1))
    return None


def line_list(text: str) -> list[str]:
    return [normalise(line) for line in text.splitlines() if normalise(line)]


def title_from_first_page(text: str) -> str | None:
    lines = line_list(text)
    for index, line in enumerate(lines[:55]):
        if PAGE_NUMBER.fullmatch(line) or len(line) < 14:
            continue
        if any(reject in line for reject in TITLE_REJECTS):
            continue
        # A case subject begins at the first top-of-page line that carries the
        # customary dash-separated descriptors.  Selecting the first such line
        # prevents later narrative paragraphs from replacing the official topic.
        if ("-" in line or "–" in line or "—" in line) and len(line) <= 420:
            segment = [line]
            # Preserve the contiguous short lines that complete a wrapped subject,
            # but stop before a numbered legal authority or narrative section.
            for following in lines[index + 1:index + 7]:
                if (PAGE_NUMBER.fullmatch(following) or any(reject in following for reject in TITLE_REJECTS)
                        or following.startswith(("1.", "2.", "3.", "ادعى", "الحمد"))):
                    break
                if len(following) < 14:
                    break
                segment.append(following)
                if following.endswith((".", "۔")):
                    break
            joined = normalise(" ".join(segment))[:700]
            return joined if len(joined) >= 14 else None
    return None


def field_line(text: str, keyword: str, limit: int = 180) -> str | None:
    court_markers = (
        "المحكمة العامة", "احملكمة العامة", "المحكمة الجزائية", "احملكمة الجزائية",
        "المحكمة التجارية", "احملكمة التجارية", "المحكمة العمالية", "احملكمة العمالية",
        "محكمة الاستئناف", "محكمة االستئناف", "المحكمة الإدارية", "احملكمة اإلدارية",
        "محكمة التنفيذ", "احملكمة التنفيذ",
    )
    for line in line_list(text):
        if keyword in line and len(line) >= len(keyword) + 3:
            raw_line = line
            if "رقم قرار التصديق" in raw_line or "مصادقة محكمة الاستئناف" in raw_line:
                continue
            if keyword == "محكمة" and not any(marker in raw_line for marker in court_markers):
                continue
            # Do not merge a case subject or a citation into the court/circuit field.
            line = re.split(r"(?:تاريخه|بتاريخ|المتضمن|الصادر|رقم قرار)", line, maxsplit=1)[0].strip(" :-،؛")
            if (len(line) >= len(keyword) + 3
                    and keyword in line
                    and "رقم قرار التصديق" not in line
                    and "مصادقة محكمة الاستئناف" not in line):
                return line[:limit]
    return None


def metadata_for_first_page(text: str) -> dict[str, str | None]:
    cleaned = normalise(text)
    return {
        "deedNumber": first_match(DEED_PATTERNS, cleaned),
        "judgmentNumber": first_match(JUDGMENT_PATTERNS, cleaned),
        "lawsuitNumber": first_match(LAWSUIT_PATTERNS, cleaned),
        "decisionDate": first_match(DATE_PATTERNS, cleaned),
        "court": field_line(text, "محكمة"),
        "circuit": field_line(text, "الدائرة"),
        "subject": title_from_first_page(text),
    }


def candidate_pages(page_texts: list[str]) -> list[tuple[int, dict[str, str | None]]]:
    candidates: list[tuple[int, dict[str, str | None]]] = []
    previous_key: tuple[str | None, str | None, str | None] | None = None
    for page_number, raw_text in enumerate(page_texts, start=1):
        if len(normalise(raw_text)) < 120:
            continue
        metadata = metadata_for_first_page(raw_text)
        identity = (metadata["deedNumber"], metadata["judgmentNumber"], metadata["lawsuitNumber"])
        if not any(identity):
            continue
        # A reference in the body is not a boundary.  A genuine source header must
        # supply either a date or a subject on the same page.
        if not (metadata["decisionDate"] or metadata["subject"]):
            continue
        if identity == previous_key:
            continue
        candidates.append((page_number, metadata))
        previous_key = identity
    return candidates


def is_bibliographic_index_volume(page_texts: list[str]) -> bool:
    """Identify a volume whose front matter identifies it as a reference index.

    An index may reproduce case/deed numbers as page references, but it is never a
    standalone judgment.  The title-page/contents combination below occurs in the
    Ministry's 1435 volume 14; treating it as an early gate protects against a
    spurious record where an index happens to resemble a judgment header.
    """
    front_matter = normalise("\n".join(page_texts[:15]))
    return "الفهارس" in front_matter and (
        "فهرس الاسانيد" in front_matter or "فهرس الكلمات" in front_matter
    )


def source_year_and_volume(path: Path) -> tuple[str | None, int | None]:
    name = path.name
    year_match = re.search(r"(14\d{2})", name)
    volume_match = re.search(r"volume-(\d+)", name)
    return (year_match.group(1) if year_match else None, int(volume_match.group(1)) if volume_match else None)


def record_id(year: str | None, volume: int | None, page: int, metadata: dict[str, str | None]) -> str:
    stable = metadata["deedNumber"] or metadata["judgmentNumber"] or metadata["lawsuitNumber"] or f"p{page}"
    raw = f"collector-{year or 'na'}-v{volume or 'na'}-p{page}-{stable}"
    return re.sub(r"[^A-Za-z0-9_-]", "-", raw)


def make_case_pdf(source: Path, start: int, end: int, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="case-", suffix=".pdf", dir=destination.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        command = ["qpdf", "--empty", "--pages", str(source), f"{start}-{end}", "--", str(temp)]
        result = subprocess.run(command, capture_output=True, text=True, errors="ignore", check=False)
        if result.returncode != 0 or not temp.exists() or temp.stat().st_size < 100:
            raise RuntimeError((result.stderr or result.stdout or "qpdf_failed").strip()[:500])
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def actual_source_pdfs(only: set[str]) -> list[Path]:
    pdfs: list[Path] = []
    for path in sorted(SOURCE_ROOT.rglob("*.pdf")):
        if only and path.name not in only:
            continue
        if path.stat().st_size < 1024 or path.read_bytes()[:4] != b"%PDF":
            continue
        pdfs.append(path)
    return pdfs


def build(only: set[str], replace: bool) -> dict[str, object]:
    if shutil.which("qpdf") is None:
        raise SystemExit("qpdf is required; install it before extraction")
    if replace:
        shutil.rmtree(OUT_DIR, ignore_errors=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, object]] = []
    pending_records: list[dict[str, object]] = []
    file_rows: list[list[object]] = []
    processing_rows: list[list[object]] = []
    skipped_rows: list[list[object]] = []
    duplicate_rows: list[list[object]] = []
    reference_collisions: list[list[object]] = []
    source_counts: Counter[str] = Counter()
    seen_ids: set[str] = set()
    seen_text_hashes: dict[str, str] = {}

    for source in actual_source_pdfs(only):
        pages = pdf_pages(source)
        if pages <= 0:
            processing_rows.append([source.name, 0, 0, 0, "failed", "invalid_pdf"])
            continue
        source_sha = sha256_file(source)
        page_texts = source_page_texts(source, pages)
        if source.name in REFERENCE_ONLY_SOURCE_FILENAMES or is_bibliographic_index_volume(page_texts):
            processing_rows.append([source.name, pages, 0, 0, "reference_only", "bibliographic_index_not_a_judgment_source"])
            continue
        candidates = candidate_pages(page_texts)
        if not candidates:
            processing_rows.append([source.name, pages, 0, 0, "needs_review", "no_verified_case_boundaries_detected"])
            continue
        year, volume = source_year_and_volume(source)
        indexed = 0
        incomplete = 0
        for position, (start, metadata) in enumerate(candidates):
            end = candidates[position + 1][0] - 1 if position + 1 < len(candidates) else pages
            rid = record_id(year, volume, start, metadata)
            if rid in seen_ids:
                skipped_rows.append([rid, source.name, start, end, "duplicate_record_id"])
                continue
            # Every case must identify a subject, an official source and a reference.
            if not metadata["subject"]:
                skipped_rows.append([rid, source.name, start, end, "missing_source_subject"])
                continue
            if not any((metadata["deedNumber"], metadata["judgmentNumber"], metadata["lawsuitNumber"])):
                skipped_rows.append([rid, source.name, start, end, "missing_case_or_judgment_reference"])
                continue
            # Court and circuit can occur after the first page in the published
            # judgment.  Read the complete verified page span before recording
            # those fields, while retaining the first-page subject and references.
            extracted_text = "\f".join(page_texts[start - 1:end])
            span_metadata = metadata_for_first_page(extracted_text)
            for key in ("court", "circuit"):
                if span_metadata.get(key):
                    metadata[key] = span_metadata[key]
            destination = OUT_DIR / f"{rid}.pdf"
            if not destination.exists():
                make_case_pdf(source, start, end, destination)
            text_hash = hashlib.sha256(normalise(extracted_text).encode("utf-8")).hexdigest()
            if text_hash in seen_text_hashes:
                duplicate_rows.append([rid, source.name, start, end, text_hash, "exact_normalized_text", seen_text_hashes[text_hash]])
                destination.unlink(missing_ok=True)
                continue
            seen_ids.add(rid)
            seen_text_hashes[text_hash] = rid
            file_sha = sha256_file(destination)
            file_bytes = destination.stat().st_size
            missing_required = [key for key in ("deedNumber", "subject", "decisionDate", "court") if not metadata.get(key)]
            review_status = "metadata_complete_auto_extracted" if not missing_required else "metadata_incomplete_pending_review"
            if missing_required:
                incomplete += 1
            record: dict[str, object] = {
                "id": rid,
                "documentType": "حكم قضائي",
                "title": metadata["subject"],
                "subject": metadata["subject"],
                "deedNumber": metadata["deedNumber"],
                "judgmentNumber": metadata["judgmentNumber"],
                "lawsuitNumber": metadata["lawsuitNumber"],
                "court": metadata["court"],
                "circuit": metadata["circuit"],
                "decisionDate": metadata["decisionDate"],
                "hijriDate": metadata["decisionDate"],
                "year": year,
                "volume": volume,
                "sourceFile": source.name,
                "sourceChecksum": source_sha,
                "sourceBytes": source.stat().st_size,
                "file": output_relpath(destination),
                "fileChecksum": file_sha,
                "fileBytes": file_bytes,
                "textChecksum": text_hash,
                "pages": end - start + 1,
                "reviewStatus": review_status,
                "archive": {
                    "granularity": "case",
                    "originalSourceFile": source.name,
                    "originalSourceChecksum": source_sha,
                    "originalStartPage": start,
                    "originalEndPage": end,
                    "preservedOriginalPages": True,
                    "derivedPdfContainsOnlyOriginalPages": True,
                },
            }
            if missing_required:
                record["missingRequiredMetadata"] = missing_required
                pending_records.append(record)
            else:
                records.append(record)
            file_rows.append([
                rid, record["file"], source.name, source_sha, start, end, end - start + 1,
                file_sha, file_bytes, metadata["subject"], metadata["deedNumber"], metadata["judgmentNumber"],
                metadata["lawsuitNumber"], metadata["decisionDate"], metadata["court"], metadata["circuit"],
                text_hash, review_status,
            ])
            if not missing_required:
                indexed += 1
        source_counts[source.name] += indexed
        notes = "case_pdfs_created" if incomplete == 0 else "case_pdfs_created_with_metadata_review_required"
        processing_rows.append([source.name, pages, len(candidates), indexed, "indexed", notes])

    # A shared case/deed/judgment reference is not automatically a duplicate: it may
    # represent distinct proceedings.  It must therefore leave the searchable set and
    # enter the pending-review register unless the content checksum already proved an
    # exact duplicate above.
    all_records = records + pending_records
    by_reference: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for record in all_records:
        for field in ("deedNumber", "judgmentNumber", "lawsuitNumber"):
            value = record.get(field)
            if value:
                by_reference[(field, str(value))].append(record)
    collision_ids: set[str] = set()
    for (field, value), grouped in sorted(by_reference.items()):
        unique = {str(record["id"]): record for record in grouped}
        if len(unique) < 2:
            continue
        canonical_ids = sorted(unique)
        for record in unique.values():
            record["reviewStatus"] = "reference_collision_pending_review"
            record["missingRequiredMetadata"] = sorted(set(record.get("missingRequiredMetadata", [])) | {f"reference_collision:{field}"})
            collision_ids.add(str(record["id"]))
            reference_collisions.append([
                record["id"], record["sourceFile"], record["archive"]["originalStartPage"],
                record["archive"]["originalEndPage"], field, value,
                record["textChecksum"], "shared_reference_distinct_text_pending_review", ";".join(canonical_ids),
            ])
    if collision_ids:
        pending_records = [record for record in all_records if str(record["id"]) in collision_ids or record["reviewStatus"] != "metadata_complete_auto_extracted"]
        records = [record for record in all_records if record["reviewStatus"] == "metadata_complete_auto_extracted"]
        file_status = {str(record["id"]): str(record["reviewStatus"]) for record in all_records}
        for row in file_rows:
            if str(row[0]) in file_status:
                row[-1] = file_status[str(row[0])]
    source_counts = Counter(str(record["sourceFile"]) for record in records)
    for row in processing_rows:
        if row[4] == "indexed":
            row[3] = source_counts[row[0]]

    INDEX.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records), encoding="utf-8")
    PENDING_INDEX.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in pending_records), encoding="utf-8")
    with FILE_REGISTER.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([
            "id", "file", "source_file", "source_sha256", "start_page", "end_page", "pages", "file_sha256",
            "bytes", "subject", "deed_number", "judgment_number", "lawsuit_number", "decision_date", "court",
            "circuit", "text_sha256", "review_status",
        ])
        writer.writerows(file_rows)
    with PROCESSING.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_file", "pages", "detected_boundaries", "indexed_case_pdfs", "status", "notes"])
        writer.writerows(processing_rows)
    with DUPLICATES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["candidate_id", "source_file", "start_page", "end_page", "text_sha256", "match_method", "canonical_id"])
        writer.writerows(duplicate_rows)
    with PENDING_CASE_DUPLICATES.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["candidate_id", "source_file", "start_page", "end_page", "reference_field", "reference_value", "text_sha256", "reason", "related_record_ids"])
        writer.writerows(reference_collisions)
    with SOURCE_COUNTS.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_file", "indexed_case_pdfs"])
        writer.writerows(sorted(source_counts.items()))
    with SKIPPED.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["id", "source_file", "start_page", "end_page", "reason"])
        writer.writerows(skipped_rows)

    summary = {
        "source_pdfs_examined": len(processing_rows),
        "judgment_case_pdfs": len(records) + len(pending_records),
        "verified_case_records_ready_for_review": len(records),
        "exact_duplicate_cases_excluded": len(duplicate_rows),
        "reference_collision_records_pending_review": len(collision_ids),
        "records_pending_metadata_review": len(pending_records),
        "sources_needing_boundary_review": sum(1 for row in processing_rows if row[4] == "needs_review"),
        "failed_sources": sum(1 for row in processing_rows if row[4] == "failed"),
        "index_path": output_relpath(INDEX),
        "pending_review_path": output_relpath(PENDING_INDEX),
        "pdf_directory": output_relpath(OUT_DIR),
        "platform_import_modified": False,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", default=[], help="source filename to process; repeatable")
    parser.add_argument("--replace", action="store_true", help="rebuild derived case PDFs and all collector manifests")
    args = parser.parse_args()
    result = build(set(args.only), args.replace)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
