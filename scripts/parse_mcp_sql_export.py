#!/usr/bin/env python3
"""Extract a JSON row array from a saved Supabase MCP execute_sql result."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    envelope = json.loads(args.input.read_text(encoding="utf-8"))
    result = envelope.get("result")
    if not isinstance(result, str):
        raise SystemExit("MCP result string missing")
    match = re.search(r"<untrusted-data-[^>]+>\n(.*)\n</untrusted-data-[^>]+>", result, re.DOTALL)
    if not match:
        raise SystemExit("Untrusted-data payload wrapper not found")
    rows = json.loads(match.group(1))
    if not isinstance(rows, list) or len(rows) != args.expected:
        raise SystemExit(f"Expected {args.expected} rows, found {len(rows) if isinstance(rows, list) else 'non-list'}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps({"rows": len(rows), "output": str(args.output), "bytes": args.output.stat().st_size}, ensure_ascii=False))


if __name__ == "__main__":
    main()
