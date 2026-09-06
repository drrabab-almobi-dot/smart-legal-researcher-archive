#!/usr/bin/env python3
"""Generate bounded, idempotent SQL chunks for circular metadata review."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "indices" / "target-schema" / "moj-circulars-review"
OUTPUT_DIR = ROOT / "imports" / "moj-circular-metadata-review-001"
NAMESPACE = uuid.UUID("417bfc7f-99a6-4d57-8c42-f70d74024d08")
CHUNK_SIZE = 50


def records(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (INDEX / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def payload(rows: list[dict[str, object]]) -> str:
    text = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    if "$archive_payload$" in text:
        raise ValueError("Unexpected dollar quote marker")
    return f"$archive_payload${text}$archive_payload$::jsonb"


def main() -> None:
    sources = records("sources.ndjson")
    source_files = records("source-files.ndjson")
    documents = records("legal-documents.ndjson")
    duplicates = records("duplicate-candidates.ndjson")
    if not (len(sources) == 1 and len(source_files) == 1 and len(documents) == 339 and len(duplicates) == 51):
        raise SystemExit("Unexpected circular batch cardinality")
    duplicate_by_document: dict[str, list[dict[str, object]]] = {}
    for row in duplicates:
        duplicate_by_document.setdefault(str(row["document_id"]), []).append(row)
    source_id = str(sources[0]["id"])
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    for offset in range(0, len(documents), CHUNK_SIZE):
        chunk_docs = documents[offset:offset + CHUNK_SIZE]
        chunk_duplicates = [candidate for row in chunk_docs for candidate in duplicate_by_document.get(str(row["id"]), [])]
        number = offset // CHUNK_SIZE + 1
        batch_name = f"moj-circular-metadata-review-001-chunk-{number:02d}"
        batch_id = str(uuid.uuid5(NAMESPACE, f"archive-batch:{batch_name}"))
        count = len(chunk_docs)
        duplicate_count = sum(1 for row in chunk_docs if row["status"] == "duplicate")
        candidate_count = len(chunk_duplicates)
        sql = f"""-- Review-only circular metadata chunk {number:02d}; no original PDF is claimed.
BEGIN;
SET LOCAL statement_timeout='120s';
SET LOCAL lock_timeout='10s';

WITH payload AS (SELECT {payload(sources)} AS data)
INSERT INTO public.sources (id,name,source_type,organization,url,channel_url,description,is_official,review_status)
SELECT (x->>'id')::uuid,x->>'name',x->>'source_type',x->>'organization',x->>'url',x->>'channel_url',x->>'description',(x->>'is_official')::boolean,x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x LIMIT 10
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(source_files)} AS data)
INSERT INTO public.source_files (id,source_id,original_filename,storage_path,original_url,mime_type,file_size,sha256,page_count,acquisition_source,acquired_at,processing_status)
SELECT (x->>'id')::uuid,(x->>'source_id')::uuid,x->>'original_filename',x->>'storage_path',x->>'original_url',x->>'mime_type',(x->>'file_size')::bigint,x->>'sha256',(x->>'page_count')::integer,x->>'acquisition_source',(x->>'acquired_at')::timestamptz,x->>'processing_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x LIMIT 10
ON CONFLICT DO NOTHING;

INSERT INTO public.archive_batches (id,source_id,batch_name,started_at,completed_at,files_count,documents_detected,documents_imported,duplicates_count,review_count,rejected_count,failed_count,status,commit_sha,notes)
SELECT '{batch_id}'::uuid,'{source_id}'::uuid,'{batch_name}',now(),now(),1,{count},{count},{duplicate_count},{count},0,0,'review',NULL,'Legacy portal metadata only; signed originals missing; no document file or public eligibility.'
LIMIT 1 ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(chunk_docs)} AS data)
INSERT INTO public.legal_documents (id,document_type,category,subcategory,title,document_number,case_number,judgment_number,decision_number,circular_number,court,circuit,issuing_authority,document_date,hijri_date,year,subject,summary,facts,claims,reasoning,ruling,principle_text,full_text,legal_articles,source_id,source_file_id,source_page_start,source_page_end,original_source,acquisition_source,source_url,content_hash,normalized_text_hash,status,review_status)
SELECT (x->>'id')::uuid,x->>'document_type',x->>'category',x->>'subcategory',x->>'title',x->>'document_number',x->>'case_number',x->>'judgment_number',x->>'decision_number',x->>'circular_number',x->>'court',x->>'circuit',x->>'issuing_authority',(x->>'document_date')::date,x->>'hijri_date',x->>'year',x->>'subject',x->>'summary',x->>'facts',x->>'claims',x->>'reasoning',x->>'ruling',x->>'principle_text',x->>'full_text',COALESCE(x->'legal_articles','[]'::jsonb),(x->>'source_id')::uuid,(x->>'source_file_id')::uuid,(x->>'source_page_start')::integer,(x->>'source_page_end')::integer,x->>'original_source',x->>'acquisition_source',x->>'source_url',x->>'content_hash',x->>'normalized_text_hash',x->>'status',x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x LIMIT 60
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(chunk_duplicates)} AS data)
INSERT INTO public.duplicate_candidates (id,document_id,matched_document_id,matched_external_id,match_type,similarity_score,decision,reason)
SELECT (x->>'id')::uuid,(x->>'document_id')::uuid,(x->>'matched_document_id')::uuid,x->>'matched_external_id',x->>'match_type',(x->>'similarity_score')::numeric,x->>'decision',x->>'reason'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x LIMIT 60
ON CONFLICT (id) DO NOTHING;

COMMIT;
SELECT '{batch_name}' AS batch_name,{count}::integer AS expected_documents,{candidate_count}::integer AS expected_candidates LIMIT 1;
"""
        output = OUTPUT_DIR / f"chunk-{number:02d}.sql"
        output.write_text(sql, encoding="utf-8")
        manifest.append({"chunk":number,"file":str(output.relative_to(ROOT)),"bytes":output.stat().st_size,"documents":count,"exact_duplicates":duplicate_count,"duplicate_candidates":candidate_count})
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps({"batch":"moj-circular-metadata-review-001","chunks":manifest},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"chunks":len(manifest),"documents":sum(int(x["documents"]) for x in manifest),"exact_duplicates":sum(int(x["exact_duplicates"]) for x in manifest),"duplicate_candidates":sum(int(x["duplicate_candidates"]) for x in manifest),"max_bytes":max(int(x["bytes"]) for x in manifest)},ensure_ascii=False))


if __name__ == "__main__":
    main()
