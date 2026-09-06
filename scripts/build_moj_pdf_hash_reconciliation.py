#!/usr/bin/env python3
"""Reconcile document_files after the collector workflow regenerates PDFs.

Document identity and page boundaries remain stable. Only the derived binary
fingerprint is updated, with old and new SHA-256 values preserved for audit.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "indices" / "target-schema" / "moj-judgments-review" / "document-files.ndjson",
    ROOT / "indices" / "target-schema" / "moj-judgments-pending-review" / "document-files.ndjson",
]
AUDIT = ROOT / "manifests" / "audit" / "moj-regenerated-pdf-hash-reconciliation.ndjson"
SUMMARY = ROOT / "manifests" / "batches" / "moj-regenerated-pdf-hash-reconciliation-001.json"
CHUNK_SIZE = 100


def read_rows(text: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def git_rows(path: Path) -> list[dict[str, object]]:
    relative = str(path.relative_to(ROOT))
    result = subprocess.run(
        ["git", "show", f"HEAD:{relative}"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return read_rows(result.stdout)


def current_rows(path: Path) -> list[dict[str, object]]:
    return read_rows(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    old_by_id: dict[str, dict[str, object]] = {}
    new_by_id: dict[str, dict[str, object]] = {}
    for path in TARGETS:
        old_by_id.update({str(row["id"]): row for row in git_rows(path)})
        new_by_id.update({str(row["id"]): row for row in current_rows(path)})
    if old_by_id.keys() != new_by_id.keys() or len(new_by_id) != 1366:
        raise SystemExit("Document file identity set changed unexpectedly")
    reconciliation: list[dict[str, object]] = []
    for file_id in sorted(new_by_id):
        old = old_by_id[file_id]
        new = new_by_id[file_id]
        stable_fields = ("document_id", "storage_path", "file_size", "page_count", "download_filename")
        if any(old[field] != new[field] for field in stable_fields):
            raise ValueError(f"Non-hash field changed for {file_id}")
        if old["sha256"] == new["sha256"]:
            raise ValueError(f"Expected regenerated hash change for {file_id}")
        reconciliation.append({
            "document_file_id": file_id,
            "document_id": new["document_id"],
            "storage_path": new["storage_path"],
            "file_size": new["file_size"],
            "page_count": new["page_count"],
            "old_sha256": old["sha256"],
            "new_sha256": new["sha256"],
            "reason": "collector_workflow_regenerated_same_page_span_pdf",
        })
    if len({str(row["new_sha256"]) for row in reconciliation}) != len(reconciliation):
        raise ValueError("Regenerated PDF hashes are not unique")

    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT.open("w", encoding="utf-8", newline="") as handle:
        for row in reconciliation:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    shutil.rmtree(args.output_dir, ignore_errors=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[dict[str, object]] = []
    for offset in range(0, len(reconciliation), CHUNK_SIZE):
        rows = reconciliation[offset:offset + CHUNK_SIZE]
        number = offset // CHUNK_SIZE + 1
        data = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        sql = f"""BEGIN;
SET LOCAL statement_timeout='120s';
SET LOCAL lock_timeout='10s';
WITH payload AS (
  SELECT x FROM jsonb_array_elements($payload${data}$payload$::jsonb) AS x LIMIT 110
), updated AS (
  UPDATE public.document_files f
  SET sha256=p.x->>'new_sha256', file_size=(p.x->>'file_size')::bigint
  FROM payload p
  WHERE f.id=(p.x->>'document_file_id')::uuid
    AND f.sha256=p.x->>'old_sha256'
  RETURNING f.id
)
SELECT count(*) AS updated_records FROM updated LIMIT 1;
COMMIT;
"""
        output = args.output_dir / f"chunk-{number:02d}.sql"
        output.write_text(sql, encoding="utf-8")
        chunks.append({"chunk": number, "file": str(output), "records": len(rows), "bytes": output.stat().st_size})
    summary = {
        "schema_version": "1.0",
        "batch_id": "moj-regenerated-pdf-hash-reconciliation-001",
        "reason": "concurrent_collector_workflow_regenerated_derived_pdfs",
        "document_file_records": len(reconciliation),
        "document_identity_changed": False,
        "source_page_boundaries_changed": False,
        "new_hashes_unique": True,
        "database_reconciliation_required": True,
        "chunks": len(chunks),
        "max_chunk_bytes": max(int(row["bytes"]) for row in chunks),
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
