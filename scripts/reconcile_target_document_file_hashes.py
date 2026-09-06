#!/usr/bin/env python3
"""Reconcile review-only target document-file hashes with collector binaries.

Only ``sha256`` is updated. Document identity, source linkage, page boundaries,
file size, and download policy must remain unchanged. No database is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = [
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
]
TARGETS = [
    ROOT / "indices" / "target-schema" / "moj-judgments-review" / "document-files.ndjson",
    ROOT / "indices" / "target-schema" / "moj-judgments-pending-review" / "document-files.ndjson",
]


def read_ndjson(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_ndjson_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-stamp", help="Filename stamp such as 20260906T1503+0300")
    args = parser.parse_args()
    stamp = args.audit_stamp or datetime.now(timezone(timedelta(hours=3))).strftime("%Y%m%dT%H%M%z")

    collector_by_path: dict[str, dict[str, object]] = {}
    for path in COLLECTOR:
        for row in read_ndjson(path):
            storage_path = str(row["file"])
            if storage_path in collector_by_path:
                raise ValueError(f"Duplicate collector storage path: {storage_path}")
            collector_by_path[storage_path] = row

    reconciliations: list[dict[str, object]] = []
    target_total = 0
    updated_targets: list[tuple[Path, list[dict[str, object]]]] = []
    for target in TARGETS:
        rows = read_ndjson(target)
        target_total += len(rows)
        for row in rows:
            storage_path = str(row["storage_path"])
            collector = collector_by_path.get(storage_path)
            if collector is None:
                raise ValueError(f"No collector record for target file: {storage_path}")
            binary = ROOT / storage_path
            if not binary.is_file():
                raise FileNotFoundError(binary)
            actual = sha256_file(binary)
            collector_hash = str(collector["fileChecksum"])
            if actual != collector_hash:
                raise ValueError(f"Collector/binary hash mismatch: {storage_path}")
            if int(row["file_size"]) != binary.stat().st_size:
                raise ValueError(f"File size changed unexpectedly: {storage_path}")
            if int(row["page_count"]) != int(collector["pages"]):
                raise ValueError(f"Page count changed unexpectedly: {storage_path}")
            old = str(row["sha256"])
            if old == actual:
                continue
            reconciliations.append({
                "document_file_id": row["id"],
                "document_id": row["document_id"],
                "storage_path": storage_path,
                "file_size": row["file_size"],
                "page_count": row["page_count"],
                "old_sha256": old,
                "new_sha256": actual,
                "collector_record_id": collector["id"],
                "reason": "target_metadata_stale_binary_and_collector_hash_agree",
                "database_modified": False,
            })
            row["sha256"] = actual
        updated_targets.append((target, rows))

    if target_total != len(collector_by_path):
        raise ValueError(f"Identity coverage mismatch: target={target_total}, collector={len(collector_by_path)}")
    if not reconciliations:
        print(json.dumps({"valid": True, "records_reconciled": 0}, ensure_ascii=False))
        return

    for target, rows in updated_targets:
        write_ndjson_atomic(target, rows)
    audit = ROOT / "manifests" / "audit" / f"moj-document-file-hash-reconciliation-{stamp}.ndjson"
    write_ndjson_atomic(audit, reconciliations)
    summary = {
        "schema_version": "1.0",
        "scope": "private_archive_target_metadata_reconciliation",
        "target_document_files": target_total,
        "records_reconciled": len(reconciliations),
        "document_identity_changed": False,
        "source_linkage_changed": False,
        "source_page_boundaries_changed": False,
        "file_size_changed": False,
        "download_policy_changed": False,
        "binary_files_changed": False,
        "database_modified": False,
        "audit_file": audit.relative_to(ROOT).as_posix(),
    }
    summary_path = ROOT / "manifests" / "audit" / f"moj-document-file-hash-reconciliation-{stamp}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
