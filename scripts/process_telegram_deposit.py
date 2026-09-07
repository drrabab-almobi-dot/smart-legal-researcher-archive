#!/usr/bin/env python3
"""Classify and separate already-preserved Telegram deposit originals.

Only entries acquired by pull_telegram_deposit.py are considered. Originals are
never modified. Derived PDFs and all records stay in private review; no record is
made public, searchable, downloadable, or platform-importable by this workflow.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "manifests" / "collector" / "telegram-deposit-file-register.csv"
RECORDS = ROOT / "indices" / "collector" / "pending-telegram-deposit-documents.ndjson"
DUPLICATES = ROOT / "manifests" / "collector" / "telegram-deposit-duplicates.csv"
PROCESSING = ROOT / "manifests" / "collector" / "telegram-deposit-processing-log.csv"
SUMMARY = ROOT / "manifests" / "collector" / "telegram-deposit-summary.json"
OUT_DIR = ROOT / "extracted" / "telegram-deposit-review"

DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")
REF_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("circular", re.compile(r"(?:رقم\s*)?(?:التعميم)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{2,40})")),
    ("decision", re.compile(r"(?:رقم\s*)?(?:القرار)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{2,40})")),
    ("judgment", re.compile(r"(?:رقم\s*)?(?:الحكم)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{3,40})")),
    ("deed", re.compile(r"(?:رقم\s*)?(?:الصك)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{3,40})")),
    ("principle", re.compile(r"(?:رقم\s*)?(?:المبدأ)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{1,40})")),
    ("precedent", re.compile(r"(?:رقم\s*)?(?:السابقة)\s*(?:رقم\s*)?[:：\-]?\s*([0-9/\-]{1,40})")),
]
DATE = re.compile(r"(?:بتاريخ|تاريخه|تاريخ)\s*[:：\-]?\s*((?:1[34][0-9]{2}|20[0-9]{2})\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}|[0-9]{1,2}\s*[/\-]\s*[0-9]{1,2}\s*[/\-]\s*(?:1[34][0-9]{2}|20[0-9]{2}))")
COURT = re.compile(r"(?:المحكمة|محكمة)\s+[^\n]{3,160}")
TYPE_AR = {"judgment": "حكم قضائي", "deed": "صك قضائي", "circular": "تعميم", "decision": "قرار", "principle": "مبدأ قضائي", "precedent": "سابقة قضائية"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalise(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").translate(DIGITS)
    value = BIDI.sub("", value)
    value = DIACRITICS.sub("", value).replace("ـ", "")
    return re.sub(r"\s+", " ", value).strip()


def sha_text(value: str) -> str:
    return hashlib.sha256(normalise(value).encode("utf-8")).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError(f"Non-object NDJSON at {path}:{number}")
        rows.append(item)
    return rows


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temp.replace(path)


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    temp.replace(path)


def pdf_page_texts(path: Path) -> list[str]:
    info = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=False)
    found = re.search(r"^Pages:\s*(\d+)", info.stdout, re.MULTILINE)
    if not found:
        raise ValueError("pdfinfo_no_page_count")
    pages = int(found.group(1))
    text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, errors="ignore", check=False)
    if text.returncode != 0:
        raise ValueError("pdftotext_failed")
    texts = text.stdout.split("\f")[:pages]
    return texts + [""] * max(0, pages - len(texts))


def page_metadata(text: str) -> tuple[str | None, str | None, str | None, str | None]:
    clean = normalise(text)
    # A reference alone is not enough: a page may cite another decision or circular.
    # Require the corresponding document-type word in the opening header area.
    header = clean[:1800]
    for kind, pattern in REF_PATTERNS:
        if TYPE_AR[kind] not in header:
            continue
        match = pattern.search(clean)
        if match:
            reference = normalise(match.group(1))
            date_match = DATE.search(clean)
            court_match = COURT.search(clean)
            return kind, reference, normalise(date_match.group(1)) if date_match else None, normalise(court_match.group(0)) if court_match else None
    return None, None, None, None


def title_from_page(text: str) -> str | None:
    rejected = ("رقم الصك", "رقم الحكم", "رقم القضية", "رقم التعميم", "رقم القرار", "بسم الله", "المملكة العربية السعودية", "وزارة العدل", "الصفحة", "فهرس")
    lines = [normalise(line) for line in text.splitlines() if normalise(line)]
    for line in lines[:40]:
        if len(line) < 12 or len(line) > 420 or any(term in line for term in rejected):
            continue
        if any(token in line for token in ("-", "–", "—", "موضوع", "بشأن")):
            return line
    return None


def make_pdf(source: Path, start: int, end: int, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix="telegram-document-", suffix=".pdf", dir=destination.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        result = subprocess.run(["qpdf", "--static-id", "--empty", "--pages", str(source), f"{start}-{end}", "--", str(temp)], capture_output=True, text=True, errors="ignore", check=False)
        if result.returncode != 0 or not temp.exists() or temp.stat().st_size < 100:
            raise ValueError((result.stderr or result.stdout or "qpdf_failed")[:500])
        temp.replace(destination)
    finally:
        temp.unlink(missing_ok=True)


def image_text(path: Path) -> str:
    """Read an original image without altering it.

    The OCR result is review evidence only. OCR cannot itself make the received
    image an official legal source or make it eligible for search.
    """
    result = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", "ara+eng"],
        capture_output=True, text=True, errors="ignore", check=False,
    )
    if result.returncode != 0:
        raise ValueError((result.stderr or "tesseract_failed").strip()[:500])
    return result.stdout


def all_existing_text_hashes() -> dict[str, set[str]]:
    found: dict[str, set[str]] = defaultdict(set)
    for path in sorted((ROOT / "indices").rglob("*.ndjson")):
        if path == RECORDS:
            continue
        for row in read_ndjson(path):
            checksum = str(row.get("textChecksum") or row.get("text_checksum") or "")
            identifier = str(row.get("id") or "")
            if len(checksum) == 64 and identifier:
                found[checksum].add(identifier)
    return found


def classify_whole_pdf(filename: str, first_text: str) -> str:
    combined = normalise(filename + " " + first_text[:2000]).lower()
    if "فهرس" in combined or "مدونة" in combined:
        return "blog_or_index"
    for kind, arabic in TYPE_AR.items():
        if arabic.lower() in combined:
            return kind
    return "unclassified_review"


def make_record(row: dict[str, str], source: Path, source_sha: str, start: int, end: int, page_texts: list[str], kind: str, reference: str | None, date: str | None, court: str | None, sequence: int, duplicate_of: list[str], is_pdf: bool) -> dict[str, Any]:
    full_text = "\f".join(page_texts[start - 1:end])
    text_sha = sha_text(full_text)
    identifier = f"telegram-deposit-{row['post_id']}-p{start}-{source_sha[:12]}"
    stored_name = source.name
    derived = OUT_DIR / f"{identifier}.pdf"
    if is_pdf and kind in TYPE_AR and not derived.exists():
        make_pdf(source, start, end, derived)
    type_ar = TYPE_AR.get(kind, "غير مصنف للمراجعة")
    title = title_from_page(page_texts[start - 1])
    required_missing = []
    if kind not in TYPE_AR:
        required_missing.append("verified_legal_type")
    if not title:
        required_missing.append("verified_title")
    if not reference and kind in TYPE_AR:
        required_missing.append("verified_reference")
    if not row.get("official_url_as_posted_unverified"):
        required_missing.append("official_source_url")
    status = "exact_duplicate_review" if duplicate_of else "telegram_deposit_pending_provenance_and_metadata_review"
    record: dict[str, Any] = {
        "id": identifier,
        "documentType": type_ar,
        "documentTypeCode": kind,
        "title": title,
        "subject": title,
        "reference": reference,
        "deedNumber": reference if kind == "deed" else None,
        "judgmentNumber": reference if kind == "judgment" else None,
        "circularNumber": reference if kind == "circular" else None,
        "decisionNumber": reference if kind == "decision" else None,
        "principleNumber": reference if kind == "principle" else None,
        "precedentNumber": reference if kind == "precedent" else None,
        "decisionDate": date,
        "court": court,
        "issuingBody": None,
        "jurisdiction": "unknown_review",
        "telegram": {"channel": row["telegram_channel"], "postId": int(row["post_id"]), "postUrl": row["post_url"], "postedAt": row.get("posted_at") or None, "captionAsReceived": row.get("caption_as_received") or None},
        "sourceFile": stored_name,
        "sourcePath": row["storage_path"],
        "sourceChecksum": source_sha,
        "sourceBytes": int(row["bytes"]),
        "officialUrlAsPostedUnverified": row.get("official_url_as_posted_unverified") or None,
        "textChecksum": text_sha,
        "archive": {"granularity": "document", "originalSourceFile": stored_name, "originalSourceChecksum": source_sha, "originalStartPage": start, "originalEndPage": end, "preservedOriginalPages": is_pdf, "derivedPdfContainsOnlyOriginalPages": is_pdf and kind in TYPE_AR, "sourceRepresentation": "pdf_pages" if is_pdf else "single_original_image"},
        "reviewStatus": status,
        "officialSourceStatus": "unverified", "searchIndexEligibility": "not_eligible", "publicDownloadEligibility": "not_eligible", "platformImportEligibility": "not_eligible",
        "missingRequirements": required_missing,
        "duplicateOf": duplicate_of or None,
    }
    if is_pdf and kind in TYPE_AR:
        record["file"] = derived.relative_to(ROOT).as_posix()
        record["fileChecksum"] = sha_file(derived)
        record["fileBytes"] = derived.stat().st_size
    return record


def process(apply: bool) -> dict[str, Any]:
    register = read_rows(REGISTER)
    existing = read_ndjson(RECORDS)
    prior_duplicates = read_rows(DUPLICATES)
    prior_processing = read_rows(PROCESSING)
    existing_by_source = {(item.get("sourceChecksum"), item.get("archive", {}).get("originalStartPage")) for item in existing}
    existing_source_sha = {str(item.get("sourceChecksum") or "") for item in existing}
    already_logged_posts = {str(item.get("post_id") or "") for item in prior_processing}
    hashes = all_existing_text_hashes()
    # The current private review index is excluded from all_existing_text_hashes to
    # prevent self-collisions during one scan. Add its known values here so a later
    # Telegram post with identical content is explicitly routed to duplicate review.
    for record in existing:
        checksum = str(record.get("textChecksum") or "")
        identifier = str(record.get("id") or "")
        if len(checksum) == 64 and identifier:
            hashes[checksum].add(identifier)
    records = list(existing)
    duplicate_rows: list[list[str]] = []
    processing_rows: list[list[str]] = []
    type_counts: Counter[str] = Counter()
    processable = 0
    created = 0
    for row in register:
        source = ROOT / row["storage_path"]
        if not source.is_file():
            if row["post_id"] in already_logged_posts:
                continue
            processing_rows.append([row["post_id"], row["original_filename"], "failed", "source_path_missing", "0", "0"])
            continue
        source_sha = sha_file(source)
        if source_sha != row["sha256"]:
            if row["post_id"] in already_logged_posts:
                continue
            processing_rows.append([row["post_id"], row["original_filename"], "failed", "source_sha256_mismatch", "0", "0"])
            continue
        if source_sha in existing_source_sha:
            continue
        is_pdf = source.suffix.lower() == ".pdf" and source.read_bytes()[:4] == b"%PDF"
        is_image = source.suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}
        if is_pdf:
            processable += 1
            try:
                texts = pdf_page_texts(source)
            except Exception as exc:
                if row["post_id"] in already_logged_posts:
                    continue
                processing_rows.append([row["post_id"], row["original_filename"], "failed", str(exc), "0", "0"])
                continue
        elif is_image:
            try:
                texts = [image_text(source)]
            except Exception as exc:
                if row["post_id"] in already_logged_posts:
                    continue
                processing_rows.append([row["post_id"], row["original_filename"], "pending_ocr_runtime_or_quality_review", str(exc), "0", "0"])
                continue
        else:
            if row["post_id"] in already_logged_posts:
                continue
            processing_rows.append([row["post_id"], row["original_filename"], "pending_document_conversion_review", "original_preserved; automated page boundaries are unavailable for this format", "0", "0"])
            continue
        starts: list[tuple[int, str, str | None, str | None, str | None]] = []
        for number, text in enumerate(texts, start=1):
            kind, reference, date, court = page_metadata(text)
            # A standalone legal document boundary must evidence a legal type and reference on its page.
            if kind and reference:
                starts.append((number, kind, reference, date, court))
        if not starts:
            kind = classify_whole_pdf(row["original_filename"], texts[0] if texts else "")
            starts = [(1, kind, None, None, None)]
        created_for_file = 0
        for sequence, (start, kind, reference, date, court) in enumerate(starts, start=1):
            if (source_sha, start) in existing_by_source:
                continue
            end = starts[sequence][0] - 1 if sequence < len(starts) else len(texts)
            full_text = "\f".join(texts[start - 1:end])
            text_sha = sha_text(full_text)
            duplicate_of = sorted(hashes.get(text_sha, set()))
            record = make_record(row, source, source_sha, start, end, texts, kind, reference, date, court, sequence, duplicate_of, is_pdf)
            records.append(record)
            existing_by_source.add((source_sha, start))
            existing_source_sha.add(source_sha)
            hashes[text_sha].add(record["id"])
            type_counts[kind] += 1
            created += 1
            created_for_file += 1
            if duplicate_of:
                duplicate_rows.append([record["id"], row["post_id"], row["original_filename"], str(start), str(end), text_sha, ";".join(duplicate_of), "exact_normalized_text", "retain_original_and_review_record_not_searchable"])
        if created_for_file or row["post_id"] not in already_logged_posts:
            status = "processed_private_review" if created_for_file else "already_processed"
            processing_rows.append([row["post_id"], row["original_filename"], status, "all_outputs_private_review_only", str(len(starts)), str(created_for_file)])

    summary = {
        "schema_version": "1.0", "scope": "authorized_telegram_deposit_private_review_only", "processed_at": now(),
        "originals_registered": len(register), "pdf_originals_processed": processable, "new_review_records": created,
        "records_in_private_review": len(records), "new_processing_events": len(processing_rows),
        "records_by_type": dict(sorted(type_counts.items())), "exact_duplicate_records": len(duplicate_rows),
        "search_eligible_records": 0, "public_downloads_enabled": False, "platform_database_modified": False,
        "next_step": "Verify official source, issuer, legal type, title, reference, and page boundaries before any search activation.",
    }
    if apply and (created or processing_rows or duplicate_rows):
        write_ndjson(RECORDS, records)
        write_csv(DUPLICATES, ["record_id", "post_id", "original_filename", "start_page", "end_page", "text_sha256", "related_record_ids", "match_method", "disposition"], [
            [item.get(key, "") for key in ("record_id", "post_id", "original_filename", "start_page", "end_page", "text_sha256", "related_record_ids", "match_method", "disposition")]
            for item in prior_duplicates
        ] + duplicate_rows)
        write_csv(PROCESSING, ["post_id", "original_filename", "status", "notes", "detected_document_boundaries", "new_review_records"], [
            [item.get(key, "") for key in ("post_id", "original_filename", "status", "notes", "detected_document_boundaries", "new_review_records")]
            for item in prior_processing
        ] + processing_rows)
        SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write private review outputs; without it, only reports a dry run")
    args = parser.parse_args()
    print(json.dumps(process(args.apply), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
