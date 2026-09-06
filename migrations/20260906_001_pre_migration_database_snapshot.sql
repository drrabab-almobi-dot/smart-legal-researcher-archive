-- Full in-database data snapshot before the additive legal archive migration.
-- The snapshot schema is outside the public API schema and is never exposed to clients.
-- It is an immediate rollback aid, not a substitute for an external provider backup.

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'backup_pre_legal_archive_20260906_0900') THEN
    RAISE EXCEPTION 'Backup schema backup_pre_legal_archive_20260906_0900 already exists';
  END IF;
END
$$;

CREATE SCHEMA backup_pre_legal_archive_20260906_0900;
COMMENT ON SCHEMA backup_pre_legal_archive_20260906_0900 IS
  'Pre-migration snapshot of every public base table taken before the additive legal archive schema migration on 2026-09-06.';

CREATE TABLE backup_pre_legal_archive_20260906_0900.snapshot_manifest (
  source_schema text NOT NULL,
  source_table text PRIMARY KEY,
  snapshot_table text NOT NULL,
  source_row_count bigint NOT NULL,
  snapshot_row_count bigint NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  verified boolean GENERATED ALWAYS AS (source_row_count = snapshot_row_count) STORED
);

DO $$
DECLARE
  item record;
  source_count bigint;
  snapshot_count bigint;
BEGIN
  FOR item IN
    SELECT tablename
    FROM pg_catalog.pg_tables
    WHERE schemaname = 'public'
    ORDER BY tablename
  LOOP
    EXECUTE format(
      'CREATE TABLE backup_pre_legal_archive_20260906_0900.%I AS TABLE public.%I WITH DATA',
      item.tablename,
      item.tablename
    );
    EXECUTE format('SELECT count(*) FROM public.%I', item.tablename) INTO source_count;
    EXECUTE format(
      'SELECT count(*) FROM backup_pre_legal_archive_20260906_0900.%I',
      item.tablename
    ) INTO snapshot_count;
    INSERT INTO backup_pre_legal_archive_20260906_0900.snapshot_manifest (
      source_schema, source_table, snapshot_table, source_row_count, snapshot_row_count
    ) VALUES (
      'public', item.tablename,
      format('backup_pre_legal_archive_20260906_0900.%I', item.tablename),
      source_count, snapshot_count
    );
    IF source_count <> snapshot_count THEN
      RAISE EXCEPTION 'Snapshot row count mismatch for public.%', item.tablename;
    END IF;
  END LOOP;
END
$$;

REVOKE ALL ON SCHEMA backup_pre_legal_archive_20260906_0900 FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA backup_pre_legal_archive_20260906_0900 FROM PUBLIC, anon, authenticated;
