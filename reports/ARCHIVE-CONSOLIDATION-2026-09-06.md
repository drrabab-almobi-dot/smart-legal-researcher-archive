# Archive consolidation status — 2026-09-06

This report records the consolidation of previously archived Smart Legal Researcher assets into the central repository.

## Central repository
- Repository: drrabab-almobi-dot/smart-legal-researcher-archive
- Base branch: collector-import
- Consolidation branch: archive-consolidation-2026-09-06

## Previously archived assets confirmed in repository
- indices/platform-import.ndjson
- indices/case-register.ndjson
- indices/principle-precedent-register.ndjson
- indices/specialized-case-register.ndjson
- indices/collector/
- indices/nafa/
- indices/target-schema/
- archive-sources/
- extracted/
- manifests/
- migrations/
- legacy-artifacts/
- originals/

## Original archive state
The originals directory currently contains README.md and telegram-preview/. The repository already contains substantial extracted/indexed legal data; therefore this consolidation must preserve those files and avoid rebuilding them blindly.

## Consolidation rule
1. Preserve originals.
2. Do not delete archived indexes.
3. Add newly recovered archived records only after duplicate checks.
4. Keep all metadata, extraction outputs, indexes, schema/migrations, and reports in this repository.
5. For binary originals that cannot be written by the current connector, register them in a manifest with source, filename, file id/location, and processing status until a binary-capable upload path is available.

## Current execution
A discovery pass over ChatGPT Library found legal source documents relevant to the archive, including judicial precedents, banking/finance judicial principles, and other legal PDFs. These will be registered in the recovery manifest for deduplication and ingestion.
