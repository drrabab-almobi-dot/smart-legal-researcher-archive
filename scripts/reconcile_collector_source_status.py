#!/usr/bin/env python3
"""Synchronize the existing pending-source register with collector processing results."""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "manifests" / "collector" / "pending-source-register.csv"
PROCESSING = ROOT / "manifests" / "collector" / "processing-log.csv"


def main() -> None:
    with PROCESSING.open(encoding="utf-8", newline="") as handle:
        process = {row["source_file"]: row for row in csv.DictReader(handle)}
    with REGISTER.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
        fields = list(rows[0]) if rows else []
    updated = 0
    for row in rows:
        result = process.get(row["source_file"])
        if not result:
            continue
        state = result["status"]
        indexed = int(result["indexed_case_pdfs"] or 0)
        if state == "reference_only":
            row["document_type"] = "فهرس مدونة"
            row["granularity"] = "document"
            row["status"] = "مرجعي فقط؛ ليس مصدراً لحكم مستقل"
        elif state == "indexed" and indexed:
            row["status"] = f"تم الفصل؛ {indexed} سجلاً استوفى حقول فهرس البحث، والبقية في مراجعة مستقلة"
        elif state == "indexed":
            row["status"] = "تم الفصل إلى PDF؛ لا سجل قابل للبحث قبل استكمال الحقول الإلزامية"
        elif state == "needs_review":
            row["status"] = "تعذّر إثبات حدود القضايا؛ في انتظار مراجعة يدوية"
        elif state == "failed":
            row["status"] = "فشل فحص الأصل؛ راجع سجل المعالجة"
        updated += 1
    with REGISTER.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"reconciled_sources={updated}")


if __name__ == "__main__":
    main()
