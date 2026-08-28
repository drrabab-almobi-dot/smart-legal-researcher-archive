#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd "$(dirname "$0")/.." && pwd)"
gzip -dc "$project_root/generated-archives/snippet-index.generated.json.gz" > "$project_root/app/snippet-index.generated.json"
gzip -dc "$project_root/generated-archives/specialized-text.generated.json.gz" > "$project_root/app/specialized-text.generated.json"
gzip -dc "$project_root/generated-archives/case-index.generated.json.gz" > "$project_root/app/case-index.generated.json"
echo "Restored generated indexes."
