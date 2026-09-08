#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_DIR = ROOT / "manifests" / "discovery"
INDEX_FILES = [
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
    ROOT / "indices" / "collector" / "recovered-case-review.ndjson",
]
IMPORT_LOG = ROOT / "manifests" / "collector" / "import-log.csv"
QUEUE = ROOT / "manifests" / "incoming" / "collector-official-urls.txt"
OUT = ROOT / "manifests" / "discovery" / "official-resolution.csv"


def norm(v: str | None) -> str:
    return re.sub(r"\D+", "", v or "")


def load_source_urls() -> dict[str, str]:
    m = {}
    if IMPORT_LOG.exists():
        with IMPORT_LOG.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("source_file") and row.get("url"):
                    m[row["source_file"]] = row["url"]
    return m


def load_index():
    by_judgment = {}
    by_case = {}
    for path in INDEX_FILES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                j = norm(r.get("judgmentNumber"))
                c = norm(r.get("lawsuitNumber"))
                if j:
                    by_judgment.setdefault(j, []).append(r)
                if c:
                    by_case.setdefault(c, []).append(r)
    return by_judgment, by_case


def main():
    source_urls = load_source_urls()
    by_judgment, by_case = load_index()
    rows = []
    queued = []
    existing_queue = set()
    if QUEUE.exists():
        existing_queue = {x.strip() for x in QUEUE.read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")}

    for csv_path in sorted(DISCOVERY_DIR.glob("albaheth-discovery-*.csv")):
        with csv_path.open(encoding="utf-8", newline="") as f:
            for d in csv.DictReader(f):
                j = norm(d.get("judgment_number"))
                c = norm(d.get("case_number"))
                matches = by_judgment.get(j, []) if j else []
                method = "judgment_number" if matches else ""
                if not matches and c:
                    # Albaheth case numbers may contain year suffix; compare full digits first,
                    # then the leading case digits when a slash was used.
                    matches = by_case.get(c, [])
                    if not matches and "/" in (d.get("case_number") or ""):
                        lead = norm((d.get("case_number") or "").split("/", 1)[0])
                        matches = by_case.get(lead, [])
                    method = "case_number" if matches else ""

                if len(matches) == 1:
                    r = matches[0]
                    sf = r.get("sourceFile") or ""
                    url = source_urls.get(sf, "")
                    status = "matched_official_archive" if url else "matched_missing_source_url"
                    if url and url not in existing_queue:
                        queued.append(url)
                        existing_queue.add(url)
                    rows.append([d.get("source_page"), d.get("case_number"), d.get("judgment_number"), status, method, r.get("id"), sf, url])
                elif len(matches) > 1:
                    rows.append([d.get("source_page"), d.get("case_number"), d.get("judgment_number"), "ambiguous_match", method, "", "", ""])
                else:
                    rows.append([d.get("source_page"), d.get("case_number"), d.get("judgment_number"), "not_found_in_current_official_archive", "", "", "", ""])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_page","case_number","judgment_number","resolution_status","match_method","archive_record_id","source_file","official_url"])
        w.writerows(rows)

    if queued:
        with QUEUE.open("a", encoding="utf-8") as f:
            for u in queued:
                f.write(u + "\n")

    print(json.dumps({"checked": len(rows), "queued_official_urls": len(queued)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
