#!/usr/bin/env python3
"""Reconcile declared legal source files with physically preserved originals.

This audit is read-only with respect to originals.  It creates evidence files for
pre-migration decisions and treats a same-name/different-SHA file as a collision,
not as a replacement.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIMARY = ROOT / "manifests" / "source-register.csv"
PENDING = ROOT / "manifests" / "collector" / "pending-source-register.csv"
AUDIT_DIR = ROOT / "manifests" / "audit"
JSON_OUT = AUDIT_DIR / "source-file-reconciliation.json"
CSV_OUT = AUDIT_DIR / "source-file-reconciliation.csv"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def declared_rows(path: Path, registry: str) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["registry"] = registry
    return rows


def source_names_from_ndjson() -> set[str]:
    names: set[str] = set()
    for path in (
        ROOT / "indices" / "case-register.ndjson",
        ROOT / "indices" / "specialized-case-register.ndjson",
        ROOT / "indices" / "principle-precedent-register.ndjson",
        ROOT / "indices" / "collector" / "case-register.ndjson",
        ROOT / "indices" / "collector" / "pending-case-review.ndjson",
    ):
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                source_name = json.loads(line).get("sourceFile")
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid NDJSON at {path}:{number}") from exc
            if source_name:
                names.add(str(source_name))
    return names


def main() -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    declared = declared_rows(PRIMARY, "source-register") + declared_rows(PENDING, "collector/pending-source-register")
    physical_by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    for root in (ROOT / "archive-sources", ROOT / "originals", ROOT / "sources"):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                physical_by_name[path.name].append({
                    "path": str(path.relative_to(ROOT)),
                    "bytes": path.stat().st_size,
                    "sha256": file_hash(path),
                })

    out_rows: list[dict[str, object]] = []
    for row in declared:
        filename = row.get("source_file", "")
        expected_sha = row.get("sha256", "")
        candidates = physical_by_name.get(filename, [])
        match = next((candidate for candidate in candidates if candidate["sha256"] == expected_sha), None)
        if match:
            state = "stored_checksum_match"
        elif candidates:
            state = "same_name_checksum_mismatch"
        else:
            state = "declared_original_not_physically_present"
        out_rows.append({
            "registry": row["registry"],
            "source_file": filename,
            "declared_sha256": expected_sha,
            "declared_bytes": int(row.get("bytes") or 0),
            "document_type": row.get("document_type", ""),
            "declared_status": row.get("status", ""),
            "reconciliation_status": state,
            "physical_candidates": candidates,
        })

    declared_names = {str(row["source_file"]) for row in out_rows}
    referenced = source_names_from_ndjson()
    index_only_names = sorted(referenced - declared_names)
    physical_names = set(physical_by_name)
    report = {
        "schema_version": "1.0",
        "scope": "private_archive_pre_migration_audit",
        "declared_source_rows": len(out_rows),
        "declared_source_names": len(declared_names),
        "reconciliation_counts": dict(sorted(Counter(str(row["reconciliation_status"]) for row in out_rows).items())),
        "index_referenced_source_names": len(referenced),
        "index_referenced_not_declared": index_only_names,
        "physical_source_file_names": len(physical_names),
        "physical_not_declared": sorted(physical_names - declared_names),
        "rows": out_rows,
    }
    JSON_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with CSV_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow([
            "registry", "source_file", "declared_sha256", "declared_bytes", "document_type",
            "declared_status", "reconciliation_status", "physical_paths", "physical_sha256",
        ])
        for row in out_rows:
            candidates = row["physical_candidates"]
            writer.writerow([
                row["registry"], row["source_file"], row["declared_sha256"], row["declared_bytes"],
                row["document_type"], row["declared_status"], row["reconciliation_status"],
                ";".join(str(candidate["path"]) for candidate in candidates),
                ";".join(str(candidate["sha256"]) for candidate in candidates),
            ])
    print(json.dumps({key: report[key] for key in report if key != "rows"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
