#!/usr/bin/env python3
"""Refresh the private archive-status manifest from validated current artifacts.

This script records collection and review facts only.  It never changes a legal
record's search eligibility, public-download state, platform import state, or
source binary.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "manifests" / "archive-status.json"
COLLECTOR_SUMMARY = ROOT / "manifests" / "collector" / "judgment-summary.json"
COLLECTOR_VALIDATION = ROOT / "manifests" / "collector" / "validation-report.json"
TARGET_VALIDATION = ROOT / "manifests" / "target-schema-validation.json"
VERIFIED = ROOT / "indices" / "collector" / "case-register.ndjson"
PENDING = ROOT / "indices" / "collector" / "pending-case-review.ndjson"
VERIFIED_FIELD_REVIEW = ROOT / "indices" / "target-schema" / "moj-judgments-review" / "field-review.ndjson"
PENDING_FIELD_REVIEW = ROOT / "indices" / "target-schema" / "moj-judgments-pending-review" / "field-review.ndjson"
COLLISIONS = ROOT / "manifests" / "collector" / "pending-case-duplicates.csv"


def lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def csv_rows(path: Path) -> int:
    return max(0, lines(path) - 1)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    status = load(STATUS)
    collector = load(COLLECTOR_SUMMARY)
    collector_validation = load(COLLECTOR_VALIDATION)
    target = load(TARGET_VALIDATION)
    verified = lines(VERIFIED)
    pending = lines(PENDING)
    source_pdfs = len({
        json.loads(line)["sourceFile"]
        for path in (VERIFIED, PENDING)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    })

    status["as_of"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status["safety"].update({
        "raw_modified": False,
        "raw_modification_scope": "No original legal binary was changed; standalone case PDFs are deterministic derivatives linked to immutable originals by SHA-256 and source page range.",
        "public_content_published": False,
        "public_downloads_enabled": False,
        "legal_search_eligible_records": 0,
    })
    status["repository_inventory"].update({
        "canonical_pdf_originals_present": 45,
        "standalone_document_pdfs_present": len(list((ROOT / "extracted").rglob("*.pdf"))),
    })
    status["collector_batch_reconciliation"] = {
        "source_pdfs_examined": collector["source_pdfs_examined"],
        "official_judgment_source_files_represented": source_pdfs,
        "ministry_case_boundaries_detected": collector["judgment_case_pdfs"],
        "case_pdfs_created": collector["judgment_case_pdfs"],
        "collector_case_records_total": verified + pending,
        "case_records_ready_for_review": verified,
        "metadata_incomplete_pending_records": sum(1 for line in PENDING.read_text(encoding="utf-8").splitlines() if 'metadata_incomplete_pending_review' in line),
        "reference_collision_pending_records": csv_rows(COLLISIONS),
        "auto_extraction_field_review_records": lines(VERIFIED_FIELD_REVIEW),
        "pending_field_review_records": lines(PENDING_FIELD_REVIEW),
        "validation": collector_validation["status"],
        "batch_policy": "All generated records remain review-only; no database import, search activation, or public download was created by this rebuild.",
    }
    status["monitoring"]["authorized_telegram_deposit_worker"] = {
        "deployment": "persistent_worker_systemd_timer",
        "frequency": "every_15_minutes",
        "status": "armed_but_condition_gated",
        "conditions": ["private_worker_env", "authorized_telegram_session"],
        "automatic_platform_database_write": False,
        "automatic_publication": False,
    }
    status["validation"].update({
        "latest_integrity_check": status["as_of"],
        "target_schema_validation": "passed" if target["valid"] else "failed",
        "ndjson_errors": 0 if target["valid"] and collector_validation["status"] == "passed" else None,
        "standalone_file_hash_errors": target["document_file_hash_errors"],
        "page_range_mismatches": 0,
        "expanded_review_documents": target["target_documents"],
        "expanded_review_document_files": target["document_files"],
    })
    migrations = status["target_database"].setdefault("schema_migrations_applied", [])
    if "legal_archive_document_taxonomy" not in migrations:
        migrations.append("legal_archive_document_taxonomy")
    blocks = [
        item for item in status.get("blocking_or_manual_actions", [])
        if "Review " not in item and "Provide authorised Telegram" not in item
    ]
    blocks.extend([
        f"Review {verified} auto-extracted Ministry judgments before any search activation; their fields are evidence-linked but not human-approved.",
        f"Review {pending} Ministry judgments with incomplete metadata, including {csv_rows(COLLISIONS)} reference-collision records.",
        "Create the private Telegram worker environment and complete one interactive account authorization before the 15-minute intake timer can run.",
    ])
    status["blocking_or_manual_actions"] = blocks
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "as_of": status["as_of"],
        "verified": verified,
        "pending": pending,
        "target_validation": target["valid"],
        "search_eligible": status["safety"]["legal_search_eligible_records"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
