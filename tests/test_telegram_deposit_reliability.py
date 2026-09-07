#!/usr/bin/env python3
"""Offline regression test for the private Telegram intake reliability rules."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_register(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "telegram_channel", "post_id", "post_url", "posted_at", "original_filename",
            "storage_path", "bytes", "sha256", "mime_type", "caption_as_received",
            "urls_as_posted", "official_url_as_posted_unverified", "acquired_at", "access_status",
            "binary_status", "official_source_status", "search_eligibility", "notes",
        ], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    processor = load_module("telegram_processor", "scripts/process_telegram_deposit.py")
    validator = load_module("telegram_validator", "scripts/validate_telegram_deposit.py")
    puller = load_module("telegram_puller", "scripts/pull_telegram_deposit.py")
    source_candidates = sorted((REPO / "extracted" / "collector-judgments-pdf").rglob("*.pdf"))
    if not source_candidates:
        raise SystemExit("No known standalone PDF fixture is available")

    with tempfile.TemporaryDirectory(prefix="telegram-deposit-reliability-") as tmp:
        root = Path(tmp)
        original_a = root / "originals/telegram-deposit/test/post-1/source.pdf"
        original_b = root / "originals/telegram-deposit/test/post-2/source.pdf"
        original_a.parent.mkdir(parents=True, exist_ok=True)
        original_b.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_candidates[0], original_a)
        shutil.copyfile(original_a, original_b)
        checksum = sha(original_a)
        common = {
            "telegram_channel": "test", "posted_at": "2026-09-07T00:00:00+00:00",
            "original_filename": "source.pdf", "bytes": str(original_a.stat().st_size),
            "sha256": checksum, "mime_type": "application/pdf", "caption_as_received": "",
            "urls_as_posted": "", "official_url_as_posted_unverified": "",
            "acquired_at": "2026-09-07T00:00:00+00:00",
            "access_status": "authorized_telegram_account_session", "binary_status": "preserved_unmodified",
            "official_source_status": "unverified", "search_eligibility": "not_eligible",
            "notes": "offline test",
        }
        write_register(root / "manifests/collector/telegram-deposit-file-register.csv", [
            {**common, "post_id": "1", "post_url": "https://t.me/test/1", "storage_path": str(original_a.relative_to(root))},
            {**common, "post_id": "2", "post_url": "https://t.me/test/2", "storage_path": str(original_b.relative_to(root))},
        ])
        binary = root / "manifests/collector/telegram-deposit-binary-duplicates.csv"
        binary.write_text(
            "duplicate_post_id,duplicate_storage_path,duplicate_sha256,canonical_post_id,canonical_storage_path,detection_method,disposition,recorded_at\n"
            f"2,{original_b.relative_to(root).as_posix()},{checksum},1,{original_a.relative_to(root).as_posix()},sha256_exact_binary_match,retain_each_received_original_and_route_duplicate_link_to_review,2026-09-07T00:00:00+00:00\n",
            encoding="utf-8",
        )
        for module in (processor, validator):
            module.ROOT = root
            module.REGISTER = root / "manifests/collector/telegram-deposit-file-register.csv"
            module.RECORDS = root / "indices/collector/pending-telegram-deposit-documents.ndjson"
            module.DUPLICATES = root / "manifests/collector/telegram-deposit-duplicates.csv"
            module.PROCESSING = root / "manifests/collector/telegram-deposit-processing-log.csv"
            module.SUMMARY = root / "manifests/collector/telegram-deposit-summary.json"
        processor.OUT_DIR = root / "extracted/telegram-deposit-review"
        validator.BINARY_DUPLICATES = binary
        validator.REPORT = root / "manifests/collector/telegram-deposit-validation-report.json"

        first = processor.process(True)
        if first["new_review_records"] < 1:
            raise SystemExit(f"Expected private review record, got {first}")
        before = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}
        second = processor.process(True)
        after = {path.relative_to(root).as_posix(): sha(path) for path in root.rglob("*") if path.is_file()}
        if second["new_review_records"] != 0 or before != after:
            raise SystemExit("Empty reprocessing rewrote outputs or created duplicate records")
        validation_exit = validator.main()
        report = json.loads(validator.REPORT.read_text(encoding="utf-8"))
        if validation_exit or report["status"] != "passed" or report["binary_duplicate_review_rows"] != 1:
            raise SystemExit(f"Validation failed: {report}")
        if puller.urls_from_caption("source https://www.moj.gov.sa/example")[1] != "https://www.moj.gov.sa/example":
            raise SystemExit("Official-source URL extraction failed")
        print(json.dumps({"status": "passed", "review_records": first["new_review_records"], "binary_duplicate_rows": 1}, ensure_ascii=False))


if __name__ == "__main__":
    main()
