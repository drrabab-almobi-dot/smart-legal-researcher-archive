#!/usr/bin/env python3
"""Generate bounded, idempotent SQL chunks for the MOJ review batch."""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "indices" / "target-schema" / "moj-judgments-review"
OUTPUT_DIR = ROOT / "imports" / "moj-1434-five-volumes-review-001"
NAMESPACE = uuid.UUID("d702a836-69be-486b-8c7f-cf6ee3a3b7f2")
CHUNK_SIZE = 6


def records(name: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in (INDEX / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def payload(data: list[dict[str, object]]) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if "$archive_payload$" in text:
        raise ValueError("Unexpected dollar quote marker")
    return f"$archive_payload${text}$archive_payload$::jsonb"


def render_chunk(
    number: int,
    sources: list[dict[str, object]],
    source_files: list[dict[str, object]],
    documents: list[dict[str, object]],
    document_files: list[dict[str, object]],
) -> str:
    source_id = str(sources[0]["id"])
    batch_name = f"moj-1434-five-volumes-review-001-chunk-{number:02d}"
    batch_id = str(uuid.uuid5(NAMESPACE, f"archive-batch:{batch_name}"))
    count = len(documents)
    return f"""-- Bounded review-only Ministry judgment import chunk {number:02d}.
BEGIN;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

WITH payload AS (SELECT {payload(sources)} AS data)
INSERT INTO public.sources (id,name,source_type,organization,url,channel_url,description,is_official,review_status)
SELECT (x->>'id')::uuid,x->>'name',x->>'source_type',x->>'organization',x->>'url',x->>'channel_url',
       x->>'description',(x->>'is_official')::boolean,x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 10
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(source_files)} AS data)
INSERT INTO public.source_files (id,source_id,original_filename,storage_path,original_url,mime_type,file_size,sha256,page_count,acquisition_source,acquired_at,processing_status)
SELECT (x->>'id')::uuid,(x->>'source_id')::uuid,x->>'original_filename',x->>'storage_path',x->>'original_url',
       x->>'mime_type',(x->>'file_size')::bigint,x->>'sha256',(x->>'page_count')::integer,
       x->>'acquisition_source',(x->>'acquired_at')::timestamptz,x->>'processing_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 10
ON CONFLICT DO NOTHING;

INSERT INTO public.archive_batches (
  id,source_id,batch_name,started_at,completed_at,files_count,documents_detected,documents_imported,
  duplicates_count,review_count,rejected_count,failed_count,status,commit_sha,notes
)
SELECT '{batch_id}'::uuid,'{source_id}'::uuid,'{batch_name}',now(),now(),5,{count},{count},0,{count},0,0,
       'review',NULL,'Official originals and standalone PDFs verified; manual field review pending.'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(documents)} AS data)
INSERT INTO public.legal_documents (
  id,document_type,category,subcategory,title,document_number,case_number,judgment_number,decision_number,
  circular_number,court,circuit,issuing_authority,document_date,hijri_date,year,subject,summary,facts,claims,
  reasoning,ruling,principle_text,full_text,legal_articles,source_id,source_file_id,source_page_start,
  source_page_end,original_source,acquisition_source,source_url,content_hash,normalized_text_hash,status,review_status
)
SELECT (x->>'id')::uuid,x->>'document_type',x->>'category',x->>'subcategory',x->>'title',x->>'document_number',
       x->>'case_number',x->>'judgment_number',x->>'decision_number',x->>'circular_number',x->>'court',x->>'circuit',
       x->>'issuing_authority',(x->>'document_date')::date,x->>'hijri_date',x->>'year',x->>'subject',x->>'summary',
       x->>'facts',x->>'claims',x->>'reasoning',x->>'ruling',x->>'principle_text',x->>'full_text',
       COALESCE(x->'legal_articles','[]'::jsonb),(x->>'source_id')::uuid,(x->>'source_file_id')::uuid,
       (x->>'source_page_start')::integer,(x->>'source_page_end')::integer,x->>'original_source',
       x->>'acquisition_source',x->>'source_url',x->>'content_hash',x->>'normalized_text_hash',x->>'status',x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 25
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(document_files)} AS data)
INSERT INTO public.document_files (
  id,document_id,file_type,storage_path,download_filename,mime_type,file_size,sha256,page_count,is_downloadable,download_block_reason
)
SELECT (x->>'id')::uuid,(x->>'document_id')::uuid,x->>'file_type',x->>'storage_path',x->>'download_filename',
       x->>'mime_type',(x->>'file_size')::bigint,x->>'sha256',(x->>'page_count')::integer,
       (x->>'is_downloadable')::boolean,x->>'download_block_reason'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 25
ON CONFLICT DO NOTHING;

COMMIT;

SELECT '{batch_name}' AS batch_name,
       (SELECT count(*) FROM public.legal_documents WHERE id IN (
          SELECT (x->>'id')::uuid FROM jsonb_array_elements({payload(documents)}) AS x LIMIT 25
       )) AS legal_documents,
       (SELECT count(*) FROM public.document_files WHERE document_id IN (
          SELECT (x->>'id')::uuid FROM jsonb_array_elements({payload(documents)}) AS x LIMIT 25
       )) AS document_files
LIMIT 1;
"""


def main() -> None:
    sources = records("sources.ndjson")
    source_files = records("source-files.ndjson")
    documents = records("legal-documents.ndjson")
    all_files = records("document-files.ndjson")
    files_by_document = {str(item["document_id"]): item for item in all_files}
    if not (len(sources) == 1 and len(source_files) == 5 and len(documents) == 191 and len(all_files) == 191):
        raise SystemExit("Unexpected input cardinality")
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for offset in range(0, len(documents), CHUNK_SIZE):
        chunk_docs = documents[offset:offset + CHUNK_SIZE]
        chunk_files = [files_by_document[str(item["id"])] for item in chunk_docs]
        number = offset // CHUNK_SIZE + 1
        output = OUTPUT_DIR / f"chunk-{number:02d}.sql"
        output.write_text(render_chunk(number, sources, source_files, chunk_docs, chunk_files), encoding="utf-8")
        manifest.append({
            "chunk": number,
            "file": str(output.relative_to(ROOT)),
            "bytes": output.stat().st_size,
            "documents": len(chunk_docs),
            "first_document_id": chunk_docs[0]["id"],
            "last_document_id": chunk_docs[-1]["id"],
        })
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps({"batch": "moj-1434-five-volumes-review-001", "chunks": manifest}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"chunks": len(manifest), "documents": sum(int(x["documents"]) for x in manifest), "max_bytes": max(int(x["bytes"]) for x in manifest)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
