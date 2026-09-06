#!/usr/bin/env python3
"""Generate bounded, guarded database hash-reconciliation queries from an audit.

The generated mutations update only document_files.sha256 and file_size. Every
row requires its immutable document-file UUID and the expected prior SHA-256.
Run all preflight queries, inspect their results, then run the apply queries and
finally the verification queries. No query grants access or changes documents.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

PROJECT_ID = "psumrktqizfepbpddktb"


def rows_from(path: Path) -> list[dict[str, object]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    required = {"document_file_id", "document_id", "storage_path", "file_size", "page_count", "old_sha256", "new_sha256"}
    if not rows or any(not required.issubset(row) for row in rows):
        raise ValueError("The reconciliation audit is empty or missing a required field")
    if len({str(row["document_file_id"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate document file IDs in reconciliation audit")
    if len({str(row["new_sha256"]) for row in rows}) != len(rows):
        raise ValueError("Duplicate target hashes in reconciliation audit")
    if any(row["old_sha256"] == row["new_sha256"] for row in rows):
        raise ValueError("An audit row has no SHA-256 change")
    return rows


def write_payload(path: Path, query: str) -> None:
    path.write_text(json.dumps({"project_id": PROJECT_ID, "query": query}, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--chunk-size", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.chunk_size <= 100:
        raise SystemExit("chunk-size must be between 1 and 100")

    rows = rows_from(args.audit)
    shutil.rmtree(args.output_dir, ignore_errors=True)
    args.output_dir.mkdir(parents=True)
    chunks: list[dict[str, object]] = []
    for offset in range(0, len(rows), args.chunk_size):
        chunk = rows[offset:offset + args.chunk_size]
        number = offset // args.chunk_size + 1
        payload = json.dumps(chunk, ensure_ascii=False, separators=(",", ":"))
        preflight = f"""WITH payload AS (
  SELECT x FROM jsonb_array_elements($payload${payload}$payload$::jsonb) AS x LIMIT {args.chunk_size + 1}
), classified AS (
  SELECT p.x, f.id, f.sha256, f.file_size
  FROM payload p
  LEFT JOIN public.document_files f ON f.id=(p.x->>'document_file_id')::uuid
)
SELECT
  count(*) AS payload_records,
  count(id) AS existing_document_files,
  count(*) FILTER (WHERE sha256=x->>'old_sha256') AS old_hash_matches,
  count(*) FILTER (WHERE sha256=x->>'new_sha256') AS new_hash_matches,
  count(*) FILTER (WHERE id IS NOT NULL AND sha256<>x->>'old_sha256' AND sha256<>x->>'new_sha256') AS unexpected_hashes
FROM classified
LIMIT 1;"""
        apply = f"""BEGIN;
SET LOCAL statement_timeout='120s';
SET LOCAL lock_timeout='10s';
WITH payload AS (
  SELECT x FROM jsonb_array_elements($payload${payload}$payload$::jsonb) AS x LIMIT {args.chunk_size + 1}
), updated AS (
  UPDATE public.document_files f
  SET sha256=p.x->>'new_sha256', file_size=(p.x->>'file_size')::bigint
  FROM payload p
  WHERE f.id=(p.x->>'document_file_id')::uuid
    AND f.sha256=p.x->>'old_sha256'
  RETURNING f.id
)
SELECT count(*) AS updated_records FROM updated LIMIT 1;
COMMIT;"""
        verify = f"""WITH payload AS (
  SELECT x FROM jsonb_array_elements($payload${payload}$payload$::jsonb) AS x LIMIT {args.chunk_size + 1}
), classified AS (
  SELECT p.x, f.id, f.sha256, f.file_size
  FROM payload p
  LEFT JOIN public.document_files f ON f.id=(p.x->>'document_file_id')::uuid
)
SELECT
  count(*) AS payload_records,
  count(id) AS existing_document_files,
  count(*) FILTER (WHERE sha256=x->>'new_sha256' AND file_size=(x->>'file_size')::bigint) AS reconciled_records,
  count(*) FILTER (WHERE id IS NOT NULL AND (sha256<>x->>'new_sha256' OR file_size<>(x->>'file_size')::bigint)) AS mismatched_records
FROM classified
LIMIT 1;"""
        for kind, query in (("preflight", preflight), ("apply", apply), ("verify", verify)):
            write_payload(args.output_dir / f"{number:02d}-{kind}.json", query)
        chunks.append({"chunk": number, "records": len(chunk)})
    (args.output_dir / "summary.json").write_text(
        json.dumps({"records": len(rows), "chunk_size": args.chunk_size, "chunks": chunks}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"records": len(rows), "chunks": len(chunks), "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
