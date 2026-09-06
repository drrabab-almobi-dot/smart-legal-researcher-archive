#!/usr/bin/env python3
"""Record non-conclusive normalized-title collisions for manual review."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = [
    ROOT / "indices" / "collector" / "case-register.ndjson",
    ROOT / "indices" / "collector" / "pending-case-review.ndjson",
    ROOT / "indices" / "collector" / "recovered-case-review.ndjson",
]
OUTPUT = ROOT / "manifests" / "collector" / "pending-title-collisions.ndjson"


def normalized(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def main() -> None:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for path in INPUTS:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            title = normalized(row.get("title"))
            if title:
                groups[title].append(row)
    review: list[dict[str, object]] = []
    for title, rows in sorted(groups.items()):
        if len(rows) < 2:
            continue
        row_text_hashes = [str(row.get("textChecksum") or "") for row in rows]
        text_hashes = sorted(set(row_text_hashes))
        if "" in text_hashes:
            text_hashes.remove("")
        review.append({
            "review_id": "title-collision-" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:20],
            "match_method": "normalized_title_only",
            "normalized_title_sha256": hashlib.sha256(title.encode("utf-8")).hexdigest(),
            "title_as_first_seen": rows[0].get("title"),
            "candidate_ids": sorted(str(row["id"]) for row in rows),
            "candidate_count": len(rows),
            "distinct_text_checksums": len(text_hashes),
            "exact_text_duplicate": all(row_text_hashes) and len(set(row_text_hashes)) == 1,
            "decision": "review",
            "reason": "A shared title is not sufficient to merge or delete legal records.",
        })
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        for row in review:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({
        "review_groups": len(review),
        "duplicate_title_records_beyond_first": sum(int(row["candidate_count"]) - 1 for row in review),
        "exact_text_duplicate_groups": sum(1 for row in review if row["exact_text_duplicate"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
