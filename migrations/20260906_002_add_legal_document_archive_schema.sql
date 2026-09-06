-- Additive target schema for independent legal documents.
-- No existing table or row is dropped, renamed, or rewritten.
-- All new tables have RLS enabled and no public client policy.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION public.set_legal_archive_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END
$$;

CREATE TABLE IF NOT EXISTS public.sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  source_type text NOT NULL,
  organization text,
  url text,
  channel_url text,
  description text,
  is_official boolean,
  review_status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sources_review_status_check CHECK (review_status IN ('pending','verified','review','rejected','archived'))
);

CREATE TABLE IF NOT EXISTS public.source_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES public.sources(id) ON DELETE RESTRICT,
  original_filename text NOT NULL,
  storage_path text NOT NULL,
  original_url text,
  mime_type text NOT NULL,
  file_size bigint NOT NULL CHECK (file_size >= 0),
  sha256 text NOT NULL,
  page_count integer CHECK (page_count IS NULL OR page_count >= 0),
  acquisition_source text NOT NULL,
  acquired_at timestamptz,
  processing_status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT source_files_sha256_format CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT source_files_processing_status_check CHECK (processing_status IN ('pending','processing','processed','review','failed','archived')),
  CONSTRAINT source_files_sha256_unique UNIQUE (sha256)
);

CREATE TABLE IF NOT EXISTS public.legal_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_type text NOT NULL,
  category text NOT NULL,
  subcategory text,
  title text NOT NULL,
  document_number text,
  case_number text,
  judgment_number text,
  decision_number text,
  circular_number text,
  court text,
  circuit text,
  issuing_authority text,
  document_date date,
  hijri_date text,
  year text,
  subject text,
  summary text,
  facts text,
  claims text,
  reasoning text,
  ruling text,
  principle_text text,
  full_text text,
  legal_articles jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_id uuid NOT NULL REFERENCES public.sources(id) ON DELETE RESTRICT,
  source_file_id uuid NOT NULL REFERENCES public.source_files(id) ON DELETE RESTRICT,
  source_page_start integer,
  source_page_end integer,
  original_source text,
  acquisition_source text NOT NULL,
  source_url text,
  content_hash text NOT NULL,
  normalized_text_hash text,
  status text NOT NULL DEFAULT 'draft',
  review_status text NOT NULL DEFAULT 'pending',
  published_at timestamptz,
  archived_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector(
      'simple'::regconfig,
      coalesce(title, '') || ' ' || coalesce(document_number, '') || ' ' ||
      coalesce(case_number, '') || ' ' || coalesce(judgment_number, '') || ' ' ||
      coalesce(decision_number, '') || ' ' || coalesce(circular_number, '') || ' ' ||
      coalesce(court, '') || ' ' || coalesce(circuit, '') || ' ' ||
      coalesce(issuing_authority, '') || ' ' || coalesce(subject, '') || ' ' ||
      coalesce(summary, '') || ' ' || coalesce(facts, '') || ' ' ||
      coalesce(claims, '') || ' ' || coalesce(reasoning, '') || ' ' ||
      coalesce(ruling, '') || ' ' || coalesce(principle_text, '') || ' ' ||
      coalesce(full_text, '')
    )
  ) STORED,
  CONSTRAINT legal_documents_type_check CHECK (document_type IN ('judgment','circular','decision','principle','precedent')),
  CONSTRAINT legal_documents_status_check CHECK (status IN ('active','draft','review','duplicate','archived','rejected')),
  CONSTRAINT legal_documents_content_hash_format CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT legal_documents_normalized_hash_format CHECK (normalized_text_hash IS NULL OR normalized_text_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT legal_documents_page_range_check CHECK (
    (source_page_start IS NULL AND source_page_end IS NULL)
    OR (source_page_start >= 1 AND source_page_end >= source_page_start)
  )
);

CREATE TABLE IF NOT EXISTS public.document_files (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  file_type text NOT NULL,
  storage_path text NOT NULL,
  download_filename text NOT NULL,
  mime_type text NOT NULL,
  file_size bigint NOT NULL CHECK (file_size >= 0),
  sha256 text NOT NULL,
  page_count integer CHECK (page_count IS NULL OR page_count >= 1),
  is_downloadable boolean NOT NULL DEFAULT false,
  download_block_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT document_files_sha256_format CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT document_files_download_check CHECK (NOT is_downloadable OR download_block_reason IS NULL),
  CONSTRAINT document_files_document_sha_unique UNIQUE (document_id, sha256)
);

CREATE TABLE IF NOT EXISTS public.document_relations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  from_document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  to_document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  relation_type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT document_relations_type_check CHECK (relation_type IN ('based_on','related_to','appeal_of','precedent_for','principle_from','supersedes','references')),
  CONSTRAINT document_relations_distinct_check CHECK (from_document_id <> to_document_id),
  CONSTRAINT document_relations_unique UNIQUE (from_document_id, to_document_id, relation_type)
);

CREATE TABLE IF NOT EXISTS public.keywords (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  normalized_name text NOT NULL UNIQUE,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.document_keywords (
  document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  keyword_id uuid NOT NULL REFERENCES public.keywords(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (document_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS public.archive_batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES public.sources(id) ON DELETE RESTRICT,
  batch_name text NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  files_count integer NOT NULL DEFAULT 0 CHECK (files_count >= 0),
  documents_detected integer NOT NULL DEFAULT 0 CHECK (documents_detected >= 0),
  documents_imported integer NOT NULL DEFAULT 0 CHECK (documents_imported >= 0),
  duplicates_count integer NOT NULL DEFAULT 0 CHECK (duplicates_count >= 0),
  review_count integer NOT NULL DEFAULT 0 CHECK (review_count >= 0),
  rejected_count integer NOT NULL DEFAULT 0 CHECK (rejected_count >= 0),
  failed_count integer NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
  status text NOT NULL DEFAULT 'pending',
  commit_sha text,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT archive_batches_status_check CHECK (status IN ('pending','processing','review','completed','failed','rolled_back')),
  CONSTRAINT archive_batches_import_count_check CHECK (documents_imported <= documents_detected)
);

CREATE TABLE IF NOT EXISTS public.duplicate_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  matched_document_id uuid REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  matched_external_id text,
  match_type text NOT NULL,
  similarity_score numeric(6,5),
  decision text NOT NULL DEFAULT 'review',
  reason text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT duplicate_candidates_match_type_check CHECK (match_type IN ('exact_hash','same_case_number','same_document_number','text_similarity','metadata_similarity')),
  CONSTRAINT duplicate_candidates_decision_check CHECK (decision IN ('duplicate','not_duplicate','review')),
  CONSTRAINT duplicate_candidates_score_check CHECK (similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 1)),
  CONSTRAINT duplicate_candidates_target_check CHECK (matched_document_id IS NOT NULL OR matched_external_id IS NOT NULL),
  CONSTRAINT duplicate_candidates_distinct_check CHECK (matched_document_id IS NULL OR matched_document_id <> document_id)
);

CREATE TABLE IF NOT EXISTS public.document_chunks (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES public.legal_documents(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL CHECK (chunk_index >= 0),
  chunk_text text NOT NULL,
  page_start integer,
  page_end integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT document_chunks_page_range_check CHECK (
    (page_start IS NULL AND page_end IS NULL)
    OR (page_start >= 1 AND page_end >= page_start)
  ),
  CONSTRAINT document_chunks_unique UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS source_files_source_id_idx ON public.source_files(source_id);
CREATE INDEX IF NOT EXISTS source_files_processing_status_idx ON public.source_files(processing_status);
CREATE INDEX IF NOT EXISTS legal_documents_document_type_idx ON public.legal_documents(document_type);
CREATE INDEX IF NOT EXISTS legal_documents_category_subcategory_idx ON public.legal_documents(category, subcategory);
CREATE INDEX IF NOT EXISTS legal_documents_case_number_idx ON public.legal_documents(case_number);
CREATE INDEX IF NOT EXISTS legal_documents_judgment_number_idx ON public.legal_documents(judgment_number);
CREATE INDEX IF NOT EXISTS legal_documents_decision_number_idx ON public.legal_documents(decision_number);
CREATE INDEX IF NOT EXISTS legal_documents_circular_number_idx ON public.legal_documents(circular_number);
CREATE INDEX IF NOT EXISTS legal_documents_court_idx ON public.legal_documents(court);
CREATE INDEX IF NOT EXISTS legal_documents_issuing_authority_idx ON public.legal_documents(issuing_authority);
CREATE INDEX IF NOT EXISTS legal_documents_document_date_idx ON public.legal_documents(document_date);
CREATE INDEX IF NOT EXISTS legal_documents_source_id_idx ON public.legal_documents(source_id);
CREATE INDEX IF NOT EXISTS legal_documents_source_file_id_idx ON public.legal_documents(source_file_id);
CREATE INDEX IF NOT EXISTS legal_documents_content_hash_idx ON public.legal_documents(content_hash);
CREATE INDEX IF NOT EXISTS legal_documents_normalized_text_hash_idx ON public.legal_documents(normalized_text_hash);
CREATE INDEX IF NOT EXISTS legal_documents_status_idx ON public.legal_documents(status);
CREATE INDEX IF NOT EXISTS legal_documents_search_vector_idx ON public.legal_documents USING gin(search_vector);
CREATE INDEX IF NOT EXISTS document_files_document_id_idx ON public.document_files(document_id);
CREATE INDEX IF NOT EXISTS document_files_sha256_idx ON public.document_files(sha256);
CREATE INDEX IF NOT EXISTS duplicate_candidates_document_idx ON public.duplicate_candidates(document_id);
CREATE INDEX IF NOT EXISTS duplicate_candidates_matched_document_idx ON public.duplicate_candidates(matched_document_id);
CREATE INDEX IF NOT EXISTS archive_batches_source_idx ON public.archive_batches(source_id);
CREATE INDEX IF NOT EXISTS document_chunks_document_idx ON public.document_chunks(document_id);

DROP TRIGGER IF EXISTS sources_set_updated_at ON public.sources;
CREATE TRIGGER sources_set_updated_at BEFORE UPDATE ON public.sources
FOR EACH ROW EXECUTE FUNCTION public.set_legal_archive_updated_at();
DROP TRIGGER IF EXISTS source_files_set_updated_at ON public.source_files;
CREATE TRIGGER source_files_set_updated_at BEFORE UPDATE ON public.source_files
FOR EACH ROW EXECUTE FUNCTION public.set_legal_archive_updated_at();
DROP TRIGGER IF EXISTS legal_documents_set_updated_at ON public.legal_documents;
CREATE TRIGGER legal_documents_set_updated_at BEFORE UPDATE ON public.legal_documents
FOR EACH ROW EXECUTE FUNCTION public.set_legal_archive_updated_at();

ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.source_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.legal_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_files ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_relations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_keywords ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.archive_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.duplicate_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_chunks ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.sources, public.source_files, public.legal_documents,
  public.document_files, public.document_relations, public.keywords,
  public.document_keywords, public.archive_batches, public.duplicate_candidates,
  public.document_chunks FROM anon, authenticated;
