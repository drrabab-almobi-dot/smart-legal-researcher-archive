#!/usr/bin/env python3
"""Collect and deduplicate the 804 external sources in Nafa Judicial Library."""

from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import tempfile
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
MAX_BYTES = 60 * 1024 * 1024
WORKERS = int(os.environ.get("NAFA_WORKERS", "10"))
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
    try:
        with requests.get(url, headers={"User-Agent": UA}, timeout=(15, 90), stream=True, allow_redirects=True) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_content(1024 * 256):
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError("source_exceeds_60_mb")
            result.update(
                status="downloaded",
                final_url=response.url,
                content_type=(response.headers.get("content-type") or "").split(";")[0].lower(),
                data=bytes(data),
                bytes=len(data),
                raw_sha256=sha256(bytes(data)),
            )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"[:500]
    return result


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
        return "", "needs_ocr"


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
    if data.startswith(b"%PDF") or ctype == "application/pdf" or final_path.endswith(".pdf"):
        return extract_pdf(data)
    if data.startswith(b"PK\x03\x04") or any(final_path.endswith(ext) for ext in (".docx", ".xlsx", ".pptx")):
        try:
            return extract_zip_xml(data)
        except Exception:
            return "", "unsupported_zip"
    if "html" in ctype or data.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
        return extract_html(data)
    if ctype.startswith("text/") or final_path.endswith((".txt", ".csv", ".md")):
        return data.decode("utf-8", errors="ignore"), "plain_text"
    return "", "unsupported_binary"


NUMBER = r"([0-9]{3,20})"
DEED_RX = re.compile(r"(?:رقم\s*(?:الصك|الحكم)\s*[:：-]?\s*)" + NUMBER)
CASE_RX = re.compile(r"(?:رقم\s*(?:الدعوى|القضية)\s*[:：-]?\s*)" + NUMBER)
CIRCULAR_RX = re.compile(r"(?:تعميم\s*(?:رقم)?\s*[:：-]?\s*)" + NUMBER)
DECISION_RX = re.compile(r"(?:قرار\s*(?:رقم)?\s*[:：-]?\s*)" + NUMBER)


def classify(text: str) -> str:
    sample = normalize(text[:20000])
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
    if doc_type == "حكم قضائي":
        marker = re.compile(r"(?=(?:رقم\s*(?:الصك|الحكم|الدعوى|القضية)\s*[:：-]?\s*[0-9]{3,20}))")
    elif doc_type == "تعميم":
        marker = re.compile(r"(?=(?:تعميم\s*(?:رقم)?\s*[:：-]?\s*[0-9]{3,20}))")
    else:
        return [clean] if clean else []
    starts = sorted(set(match.start() for match in marker.finditer(clean)))
    if len(starts) <= 1:
        return [clean] if clean else []
    chunks = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(clean)
        chunk = clean[start:end].strip()
        if len(chunk) >= 200:
            chunks.append(chunk)
    return chunks or ([clean] if clean else [])


def load_existing_keys() -> tuple[set[str], set[str], set[str]]:
    deeds, cases, text_hashes = set(), set(), set()
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
            case_number = record.get("caseNumber") or record.get("lawsuitNumber")
            if case_number:
                cases.add(str(case_number))
            if record.get("textChecksum"):
                text_hashes.add(record["textChecksum"])
    return deeds, cases, text_hashes


def safe_slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "-", value)[:180]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    sources = load_sources()
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        jobs = {executor.submit(fetch_source, record): record for record in sources}
        for future in as_completed(jobs):
            results.append(future.result())

    existing_deeds, existing_cases, existing_hashes = load_existing_keys()
    raw_hash_owner = {}
    text_hash_owner = {value: "existing_archive" for value in existing_hashes}
    legal_key_owner = {}
    records, duplicates, source_rows = [], [], []

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
            elif case and case in existing_cases:
                duplicate_of, method_name = f"existing_case:{case}", "case_number"
            elif legal_key != f"{doc_type}||||" and legal_key in legal_key_owner:
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
    counts = {
        "source_urls": len(sources),
        "downloaded_unique_binaries": len(raw_hash_owner),
        "documents_unique": len(records),
        "duplicates_excluded": len(duplicates),
        "download_failures": sum(1 for row in source_rows if row[5] == "failed"),
        "by_type": {},
    }
    for record in records:
        counts["by_type"][record["documentType"]] = counts["by_type"].get(record["documentType"], 0) + 1
    (MANIFESTS / "verified-counts.json").write_text(json.dumps(counts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
