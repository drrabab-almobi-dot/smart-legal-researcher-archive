#!/usr/bin/env python3
"""Collect and deduplicate the 804 external sources in Nafa Judicial Library."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests


ROOT = Path.cwd()
SOURCE_DIR = ROOT / "sources" / "nafa-judicial-library-1445"
OUT = ROOT / "extracted" / "nafa"
INDEX = ROOT / "indices" / "nafa" / "documents.ndjson"
MANIFESTS = ROOT / "manifests" / "nafa"
PLATFORM_DIR = ROOT / "platform-import" / "nafa"
MAX_BYTES = 60 * 1024 * 1024
WORKERS = int(os.environ.get("NAFA_WORKERS", "10"))
OCR_MAX_PAGES = int(os.environ.get("NAFA_OCR_MAX_PAGES", "0"))
UA = "SmartLegalResearcherArchive/1.0 (public legal-source preservation)"

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
BIDI = re.compile(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069\uFEFF]")
TAG = re.compile(r"<[^>]+>")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = MARKS.sub("", text)
    text = BIDI.sub("", text).replace("ـ", "")
    text = text.translate(ARABIC_DIGITS)
    return re.sub(r"\s+", " ", text).strip()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_download_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host == "drive.google.com":
        match = re.search(r"/file/d/([^/]+)", parsed.path)
        file_id = match.group(1) if match else parse_qs(parsed.query).get("id", [None])[0]
        if file_id:
            return f"https://drive.google.com/uc?export=download&id={file_id}"
    if host == "docs.google.com":
        match = re.search(r"/(document|spreadsheets|presentation)/d/([^/]+)", parsed.path)
        if match:
            kind, file_id = match.groups()
            export = {"document": "docx", "spreadsheets": "xlsx", "presentation": "pptx"}[kind]
            return f"https://docs.google.com/{kind}/d/{file_id}/export?format={export}"
    return url


def load_sources() -> list[dict]:
    records = []
    for path in sorted(SOURCE_DIR.glob("unique-links-part-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
    seen = set()
    unique = []
    for record in records:
        url = record["url"].strip()
        if url in seen:
            continue
        seen.add(url)
        record["url"] = url
        unique.append(record)
    return unique


def fetch_source(record: dict) -> dict:
    url = canonical_download_url(record["url"])
    result = {**record, "download_url": url, "status": "failed", "error": ""}
    for attempt in range(1, 4):
        try:
            with requests.get(url, headers={"User-Agent": UA}, timeout=(20, 120), stream=True, allow_redirects=True) as response:
                response.raise_for_status()
                data = bytearray()
                for chunk in response.iter_content(1024 * 256):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("source_exceeds_60_mb")
                if not data:
                    raise ValueError("empty_response")
                result.update(
                    status="downloaded",
                    final_url=response.url,
                    content_type=(response.headers.get("content-type") or "").split(";")[0].lower(),
                    data=bytes(data),
                    bytes=len(data),
                    raw_sha256=sha256(bytes(data)),
                    attempts=attempt,
                )
                return result
        except Exception as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"[:500]
            result["attempts"] = attempt
            if attempt < 3:
                time.sleep(attempt * 2)
    return result


def run_tesseract(image: Path) -> str:
    run = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", "ara+eng", "--psm", "6"],
        capture_output=True,
        timeout=300,
    )
    if run.returncode != 0:
        return ""
    return run.stdout.decode("utf-8", errors="ignore")


def extract_pdf(data: bytes) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as directory:
        pdf = Path(directory) / "source.pdf"
        txt = Path(directory) / "source.txt"
        pdf.write_bytes(data)
        run = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], capture_output=True)
        if run.returncode == 0 and txt.exists():
            text = txt.read_text(encoding="utf-8", errors="ignore")
            if len(normalize(text)) >= 250:
                return text, "pdftotext"
        images = Path(directory) / "page"
        command = ["pdftoppm", "-jpeg", "-r", "220"]
        if OCR_MAX_PAGES > 0:
            command.extend(["-f", "1", "-l", str(OCR_MAX_PAGES)])
        command.extend([str(pdf), str(images)])
        rendered = subprocess.run(command, capture_output=True, timeout=900)
        if rendered.returncode != 0:
            return "", "ocr_render_failed"
        pages = []
        for image in sorted(Path(directory).glob("page-*.jpg")):
            page = run_tesseract(image)
            if page.strip():
                pages.append(page)
        ocr_text = "\n\n".join(pages)
        return (ocr_text, "tesseract_ara_eng") if normalize(ocr_text) else ("", "ocr_empty")


def extract_image(data: bytes, suffix: str) -> tuple[str, str]:
    with tempfile.NamedTemporaryFile(suffix=suffix) as image:
        image.write(data)
        image.flush()
        text = run_tesseract(Path(image.name))
    return (text, "tesseract_ara_eng_image") if normalize(text) else ("", "ocr_empty")


def extract_zip_xml(data: bytes) -> tuple[str, str]:
    chunks = []
    with tempfile.NamedTemporaryFile(suffix=".zip") as handle:
        handle.write(data)
        handle.flush()
        with zipfile.ZipFile(handle.name) as archive:
            for name in archive.namelist():
                if name.endswith(".xml") and any(part in name for part in ("word/", "ppt/", "xl/")):
                    raw = archive.read(name).decode("utf-8", errors="ignore")
                    chunks.append(unescape(TAG.sub(" ", raw)))
    return "\n".join(chunks), "office_xml"


def extract_html(data: bytes) -> tuple[str, str]:
    text = data.decode("utf-8", errors="ignore")
    text = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\1>", " ", text)
    return unescape(TAG.sub(" ", text)), "html"


def extract_text(item: dict) -> tuple[str, str]:
    data = item["data"]
    ctype = item.get("content_type", "")
    final_path = urlparse(item.get("final_url", item["url"])).path.lower()
    pdf_at = data.find(b"%PDF", 0, 2048)
    if pdf_at >= 0 or ctype == "application/pdf" or final_path.endswith(".pdf"):
        if pdf_at > 0:
            data = data[pdf_at:]
        return extract_pdf(data)
    image_signatures = (
        (b"\xff\xd8\xff", ".jpg"),
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"II*\x00", ".tif"),
        (b"MM\x00*", ".tif"),
    )
    for signature, suffix in image_signatures:
        if data.startswith(signature):
            return extract_image(data, suffix)
    if data.startswith(b"PK\x03\x04") or any(final_path.endswith(ext) for ext in (".docx", ".xlsx", ".pptx")):
        try:
            return extract_zip_xml(data)
        except Exception:
            return "", "unsupported_zip"
    if "html" in ctype or data.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
        return extract_html(data)
    if ctype.startswith("text/") or final_path.endswith((".txt", ".csv", ".md")):
        return data.decode("utf-8", errors="ignore"), "plain_text"
    # Some hosts send textual files as application/octet-stream.
    decoded = data.decode("utf-8", errors="ignore")
    if len(normalize(decoded)) >= 250 and re.search(r"[\u0600-\u06FF]", decoded):
        return decoded, "utf8_binary_text"
    return "", "unsupported_binary"


NUMBER = r"([0-9]{3,20})"
DEED_RX = re.compile(r"(?:رقم\s*(?:الصك|الحكم)\s*[:：-]?\s*)" + NUMBER)
CASE_RX = re.compile(r"(?:رقم\s*(?:الدعوى|القضية)\s*[:：-]?\s*)" + NUMBER)
CIRCULAR_RX = re.compile(r"(?:تعميم\s*(?:رقم)?\s*[:：-]?\s*)" + NUMBER)
DECISION_RX = re.compile(r"(?:قرار\s*(?:رقم)?\s*[:：-]?\s*)" + NUMBER)


def classify(text: str) -> str:
    sample = normalize(text)
    if "تعميم" in sample and (CIRCULAR_RX.search(sample) or "تعميم قضائي" in sample):
        return "تعميم"
    if DEED_RX.search(sample) or CASE_RX.search(sample):
        return "حكم قضائي"
    if "مبدأ قضائي" in sample or "المبادئ القضائية" in sample:
        return "مبدأ قضائي"
    if "سابقة قضائية" in sample or "السوابق القضائية" in sample:
        return "سابقة قضائية"
    if "قرار" in sample and DECISION_RX.search(sample):
        return "قرار"
    if "نظام" in sample or "اللائحة" in sample:
        return "نظام أو لائحة"
    if "بحث" in sample or "دراسة" in sample:
        return "بحث قانوني"
    return "مرجع قانوني"


def first(rx: re.Pattern, text: str) -> str | None:
    match = rx.search(normalize(text))
    return match.group(1) if match else None


def split_documents(text: str, doc_type: str) -> list[str]:
    clean = normalize(text)

    def starts_for(rx: re.Pattern) -> list[int]:
        seen_numbers = set()
        starts = []
        for match in rx.finditer(clean):
            number = match.group(1)
            if number in seen_numbers:
                continue
            seen_numbers.add(number)
            starts.append(match.start())
        return starts

    if doc_type == "حكم قضائي":
        # A single judgment commonly repeats both its case and deed numbers.
        # Split on the strongest repeated boundary only, never on every number.
        starts = []
        for candidate in (DEED_RX, CASE_RX):
            candidate_starts = starts_for(candidate)
            if len(candidate_starts) > 1:
                starts = candidate_starts
                break
    elif doc_type == "تعميم":
        starts = starts_for(CIRCULAR_RX)
    else:
        return [clean] if clean else []
    if len(starts) <= 1:
        return [clean] if clean else []
    starts[0] = 0
    chunks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(clean)
        chunk = clean[start:end].strip()
        if len(chunk) >= 200:
            chunks.append(chunk)
    return chunks or ([clean] if clean else [])


def load_existing_keys() -> tuple[set[str], set[str]]:
    deeds, text_hashes = set(), set()
    for path in list((ROOT / "indices").glob("*.ndjson")) + list((ROOT / "indices").glob("**/*.ndjson")):
        if path == INDEX or not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                record = json.loads(line)
            except Exception:
                continue
            if record.get("deedNumber"):
                deeds.add(str(record["deedNumber"]))
            if record.get("textChecksum"):
                text_hashes.add(record["textChecksum"])
    return deeds, text_hashes


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", value)[:180]


def main() -> None:
    # This directory is generated output only. Rebuild it atomically in spirit
    # so stale fragments from an earlier splitting method cannot remain indexed.
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        jobs = {executor.submit(fetch_source, record): record for record in sources}
        for future in as_completed(jobs):
            results.append(future.result())

    existing_deeds, existing_hashes = load_existing_keys()
    raw_hash_owner = {}
    text_hash_owner = {value: "existing_archive" for value in existing_hashes}
    legal_key_owner = {}
    records, platform_records, duplicates, duplicate_candidates, source_rows = [], [], [], [], []

    for item in sorted(results, key=lambda value: value["id"]):
        if item["status"] != "downloaded":
            source_rows.append([item["id"], item["url"], "", "", "", "failed", item["error"]])
            continue
        raw_hash = item["raw_sha256"]
        if raw_hash in raw_hash_owner:
            duplicates.append([item["id"], "source", raw_hash, raw_hash_owner[raw_hash], "exact_binary"])
            source_rows.append([item["id"], item["url"], item.get("final_url", ""), raw_hash, item["bytes"], "duplicate_binary", raw_hash_owner[raw_hash]])
            continue
        raw_hash_owner[raw_hash] = item["id"]
        text, method = extract_text(item)
        doc_type = classify(text)
        chunks = split_documents(text, doc_type)
        accepted = 0
        for part, chunk in enumerate(chunks, start=1):
            text_hash = sha256(normalize(chunk).encode("utf-8"))
            deed = first(DEED_RX, chunk)
            case = first(CASE_RX, chunk)
            circular = first(CIRCULAR_RX, chunk)
            decision = first(DECISION_RX, chunk)
            legal_key = f"{doc_type}|{deed or ''}|{case or ''}|{circular or ''}|{decision or ''}"
            duplicate_of = None
            method_name = None
            if text_hash in text_hash_owner:
                duplicate_of, method_name = text_hash_owner[text_hash], "exact_normalized_text"
            elif deed and deed in existing_deeds:
                duplicate_of, method_name = f"existing_deed:{deed}", "deed_number"
            elif (deed or circular or decision) and legal_key in legal_key_owner:
                duplicate_of, method_name = legal_key_owner[legal_key], "same_legal_identity"
            if duplicate_of:
                duplicates.append([item["id"], "document", text_hash, duplicate_of, method_name])
                continue
            record_id = safe_slug(f"nafa-{item['id']}-{part}-{deed or case or circular or decision or text_hash[:12]}")
            out_dir = OUT / safe_slug(doc_type)
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{record_id}.txt"
            out_file.write_text(chunk + "\n", encoding="utf-8")
            text_hash_owner[text_hash] = record_id
            if legal_key != f"{doc_type}||||":
                legal_key_owner[legal_key] = record_id
            record = {
                "id": record_id,
                "documentType": doc_type,
                "title": normalize(item.get("label") or "")[:500],
                "deedNumber": deed,
                "caseNumber": case,
                "lawsuitNumber": case,
                "circularNumber": circular,
                "decisionNumber": decision,
                "sourceUrl": item["url"],
                "finalUrl": item.get("final_url"),
                "sourcePage": item.get("page"),
                "sourceChecksum": raw_hash,
                "textChecksum": text_hash,
                "file": str(out_file.relative_to(ROOT)),
                "extractionMethod": method,
                "reviewStatus": "auto_extracted_needs_review",
                "archive": {"granularity": "document", "sourceIndex": "Nafa Judicial Library 1445"},
            }
            records.append(record)
            platform_records.append({
                "id": record_id,
                "title": record["title"] or f"{doc_type} من مكتبة نفع",
                "documentType": doc_type,
                "referenceNo": deed or circular or decision or case,
                "issuer": "مكتبة نفع القضائية",
                "publishingAuthority": "مكتبة نفع القضائية",
                "originatingAuthority": None,
                "hijriYear": None,
                "specialty": "أخرى",
                "summary": f"{doc_type} مستخرج كوثيقة مستقلة من مكتبة نفع القضائية 1445هـ.",
                "extractedText": chunk,
                "sourceUrl": item["url"],
                "sourceChecksum": raw_hash,
                "textChecksum": text_hash,
            })
            if case and not deed:
                duplicate_candidates.append([record_id, "case_number_only", case, "kept_pending_review"])
            accepted += 1
        source_rows.append([item["id"], item["url"], item.get("final_url", ""), raw_hash, item["bytes"], method, accepted])

    INDEX.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records), encoding="utf-8")
    with (MANIFESTS / "source-status.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_id", "url", "final_url", "sha256", "bytes", "status", "documents_added_or_note"])
        writer.writerows(source_rows)
    with (MANIFESTS / "duplicates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_id", "level", "sha_or_key", "canonical_record", "match_method"])
        writer.writerows(duplicates)
    with (MANIFESTS / "duplicate-candidates.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "reason", "value", "disposition"])
        writer.writerows(duplicate_candidates)
    platform_index = ROOT / "indices" / "platform-import.ndjson"
    platform_index.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in platform_records), encoding="utf-8")
    if PLATFORM_DIR.exists():
        shutil.rmtree(PLATFORM_DIR)
    PLATFORM_DIR.mkdir(parents=True, exist_ok=True)
    batch_size = 100
    for offset in range(0, len(platform_records), batch_size):
        batch = platform_records[offset:offset + batch_size]
        path = PLATFORM_DIR / f"nafa-batch-{offset // batch_size + 1:03d}.json.gz"
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as handle:
            json.dump(batch, handle, ensure_ascii=False, separators=(",", ":"))
    counts = {
        "source_urls": len(sources),
        "downloaded_unique_binaries": len(raw_hash_owner),
        "documents_unique": len(records),
        "duplicates_excluded": len(duplicates),
        "duplicate_candidates_kept_for_review": len(duplicate_candidates),
        "download_failures": sum(1 for row in source_rows if row[5] == "failed"),
        "extraction_failures": sum(1 for row in source_rows if row[5] in {"ocr_render_failed", "ocr_empty", "unsupported_binary", "unsupported_zip"}),
        "platform_batches": (len(platform_records) + batch_size - 1) // batch_size,
        "by_type": {},
    }
    for record in records:
        counts["by_type"][record["documentType"]] = counts["by_type"].get(record["documentType"], 0) + 1
    (MANIFESTS / "verified-counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
