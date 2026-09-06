-- Cover the two foreign keys identified by the Supabase performance advisor.
CREATE INDEX IF NOT EXISTS document_keywords_keyword_id_idx
  ON public.document_keywords(keyword_id);
CREATE INDEX IF NOT EXISTS document_relations_to_document_id_idx
  ON public.document_relations(to_document_id);
