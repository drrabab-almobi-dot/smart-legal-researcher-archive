#!/usr/bin/env python3
"""Generate an idempotent, review-only SQL import for the SAIP small batch."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "indices" / "target-schema" / "saip-copyright-2019"
OUTPUT = ROOT / "imports" / "20260906_saip_copyright_review_batch.sql"
NAMESPACE = uuid.UUID("c5c9874e-2552-4a21-b3d4-d675b13d6bc2")


def records(name: str) -> list[dict[str, object]]:
    path = INDEX / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def payload(data: list[dict[str, object]]) -> str:
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if "$archive_payload$" in text:
        raise ValueError("Unexpected SQL dollar-quote marker in payload")
    return f"$archive_payload${text}$archive_payload$::jsonb"


def main() -> None:
    sources = records("sources.ndjson")
    source_files = records("source-files.ndjson")
    documents = records("legal-documents.ndjson")
    document_files = records("document-files.ndjson")
    duplicates = records("duplicate-candidates.ndjson")
    if not (len(sources) == 1 and len(source_files) == 1 and len(documents) == 53 and len(document_files) == 53 and len(duplicates) == 53):
        raise SystemExit("Unexpected batch cardinality")
    if any(item.get("status") != "review" or item.get("legal_search_eligibility") is not False for item in documents):
        raise SystemExit("All documents must remain review-only and not search eligible")
    if any(item.get("is_downloadable") is not False for item in document_files):
        raise SystemExit("All document files must remain non-downloadable")

    batch_id = str(uuid.uuid5(NAMESPACE, "archive-batch:saip-copyright-2019-review-001"))
    source_id = str(sources[0]["id"])
    sql = f"""-- Generated review-only data batch.  Not public and not search eligible.
BEGIN;
SET LOCAL statement_timeout = '120s';
SET LOCAL lock_timeout = '10s';

WITH payload AS (SELECT {payload(sources)} AS data)
INSERT INTO public.sources (id,name,source_type,organization,url,channel_url,description,is_official,review_status)
SELECT (x->>'id')::uuid,x->>'name',x->>'source_type',x->>'organization',x->>'url',
       x->>'channel_url',x->>'description',(x->>'is_official')::boolean,x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 10
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(source_files)} AS data)
INSERT INTO public.source_files (id,source_id,original_filename,storage_path,original_url,mime_type,file_size,sha256,page_count,acquisition_source,acquired_at,processing_status)
SELECT (x->>'id')::uuid,(x->>'source_id')::uuid,x->>'original_filename',x->>'storage_path',
       x->>'original_url',x->>'mime_type',(x->>'file_size')::bigint,x->>'sha256',
       (x->>'page_count')::integer,x->>'acquisition_source',(x->>'acquired_at')::timestamptz,
       x->>'processing_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 10
ON CONFLICT DO NOTHING;

INSERT INTO public.archive_batches (
  id,source_id,batch_name,started_at,completed_at,files_count,documents_detected,
  documents_imported,duplicates_count,review_count,rejected_count,failed_count,status,commit_sha,notes
)
SELECT '{batch_id}'::uuid,'{source_id}'::uuid,'saip-copyright-2019-review-001',now(),now(),
       1,53,53,53,53,0,0,'review',NULL,
       'Review-only import. Source-checksum crosswalk pending; no public search or download.'
LIMIT 1
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(documents)} AS data)
INSERT INTO public.legal_documents (
  id,document_type,category,subcategory,title,document_number,case_number,judgment_number,
  decision_number,circular_number,court,circuit,issuing_authority,document_date,hijri_date,year,
  subject,summary,facts,claims,reasoning,ruling,principle_text,full_text,legal_articles,source_id,
  source_file_id,source_page_start,source_page_end,original_source,acquisition_source,source_url,
  content_hash,normalized_text_hash,status,review_status
)
SELECT (x->>'id')::uuid,x->>'document_type',x->>'category',x->>'subcategory',x->>'title',
       x->>'document_number',x->>'case_number',x->>'judgment_number',x->>'decision_number',
       x->>'circular_number',x->>'court',x->>'circuit',x->>'issuing_authority',
       (x->>'document_date')::date,x->>'hijri_date',x->>'year',x->>'subject',x->>'summary',
       x->>'facts',x->>'claims',x->>'reasoning',x->>'ruling',x->>'principle_text',x->>'full_text',
       COALESCE(x->'legal_articles','[]'::jsonb),(x->>'source_id')::uuid,(x->>'source_file_id')::uuid,
       (x->>'source_page_start')::integer,(x->>'source_page_end')::integer,x->>'original_source',
       x->>'acquisition_source',x->>'source_url',x->>'content_hash',x->>'normalized_text_hash',
       x->>'status',x->>'review_status'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 100
ON CONFLICT (id) DO NOTHING;

WITH payload AS (SELECT {payload(document_files)} AS data)
INSERT INTO public.document_files (
  id,document_id,file_type,storage_path,download_filename,mime_type,file_size,sha256,page_count,
  is_downloadable,download_block_reason
)
SELECT (x->>'id')::uuid,(x->>'document_id')::uuid,x->>'file_type',x->>'storage_path',
       x->>'download_filename',x->>'mime_type',(x->>'file_size')::bigint,x->>'sha256',
       (x->>'page_count')::integer,(x->>'is_downloadable')::boolean,x->>'download_block_reason'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 100
ON CONFLICT DO NOTHING;

WITH payload AS (SELECT {payload(duplicates)} AS data)
INSERT INTO public.duplicate_candidates (
  id,document_id,matched_external_id,match_type,similarity_score,decision,reason
)
SELECT (x->>'id')::uuid,(x->>'document_id')::uuid,x->>'matched_external_id',x->>'match_type',
       (x->>'similarity_score')::numeric,x->>'decision',x->>'reason'
FROM payload CROSS JOIN LATERAL jsonb_array_elements(payload.data) AS x
LIMIT 100
ON CONFLICT (id) DO NOTHING;

COMMIT;

SELECT
  (SELECT count(*) FROM public.sources WHERE id = '{source_id}'::uuid) AS sources,
  (SELECT count(*) FROM public.source_files WHERE source_id = '{source_id}'::uuid) AS source_files,
  (SELECT count(*) FROM public.legal_documents WHERE source_id = '{source_id}'::uuid) AS legal_documents,
  (SELECT count(*) FROM public.document_files f JOIN public.legal_documents d ON d.id=f.document_id WHERE d.source_id = '{source_id}'::uuid) AS document_files,
  (SELECT count(*) FROM public.duplicate_candidates c JOIN public.legal_documents d ON d.id=c.document_id WHERE d.source_id = '{source_id}'::uuid) AS duplicate_candidates
LIMIT 1;
"""
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(sql, encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT.relative_to(ROOT)), "bytes": OUTPUT.stat().st_size, "documents": len(documents)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
