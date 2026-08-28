#!/usr/bin/env python3
import json
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "app" / "case-index.generated.json"
LIBRARY = ROOT / "public" / "library"
ARCHIVE_ROOT = LIBRARY / "cases" / "1434"


def safe_value(value, fallback):
    value = str(value or "").strip()
    return "".join(ch for ch in value if ch.isascii() and (ch.isalnum() or ch in "-_")) or fallback


def split_volume(volume, cases):
    source_name = f"moj-judgments-1434-volume-{volume}.pdf"
    source_path = LIBRARY / source_name
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    reader = PdfReader(str(source_path))
    ordered = sorted(cases, key=lambda item: int(item["pdfPage"]))
    destination = ARCHIVE_ROOT / f"volume-{volume}"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []

    for position, item in enumerate(ordered):
        start = int(item["pdfPage"])
        next_start = int(ordered[position + 1]["pdfPage"]) if position + 1 < len(ordered) else len(reader.pages) + 1
        end = max(start, next_start - 1)
        deed = safe_value(item.get("deedNumber"), "no-deed")
        lawsuit = safe_value(item.get("lawsuitNumber"), "no-lawsuit")
        filename = f"case-{position + 1:03d}-sak-{deed}-lawsuit-{lawsuit}.pdf"
        target = destination / filename

        writer = PdfWriter()
        for page_number in range(start - 1, min(end, len(reader.pages))):
            writer.add_page(reader.pages[page_number])
        writer.add_metadata({
            "/Title": f"صك {item.get('deedNumber') or ''} - دعوى {item.get('lawsuitNumber') or ''}".strip(" -"),
            "/Subject": "حكم مستقل من مجموعة الأحكام القضائية - وزارة العدل",
            "/SourceFile": source_name,
            "/SourcePages": f"{start}-{min(end, len(reader.pages))}",
        })
        with target.open("wb") as stream:
            writer.write(stream)

        item["sourceFile"] = f"cases/1434/volume-{volume}/{filename}"
        item["pdfPage"] = 1
        item["archive"] = {
            "granularity": "case",
            "originalSourceFile": source_name,
            "originalStartPage": start,
            "originalEndPage": min(end, len(reader.pages)),
            "preservedOriginalPages": True,
        }
        manifest.append({
            "id": item["id"],
            "file": filename,
            "deedNumber": item.get("deedNumber"),
            "lawsuitNumber": item.get("lawsuitNumber"),
            "sourceStartPage": start,
            "sourceEndPage": min(end, len(reader.pages)),
            "pages": min(end, len(reader.pages)) - start + 1,
        })

    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(manifest)


def main():
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    pending = defaultdict(list)
    for item in index:
        if item.get("archive", {}).get("preservedOriginalPages"):
            continue
        pending[int(item["volume"])].append(item)

    processed = 0
    for volume in sorted(pending):
        count = split_volume(volume, pending[volume])
        processed += count
        print(f"volume {volume}: {count} cases")

    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(1 for item in index if item.get("archive", {}).get("preservedOriginalPages"))
    print(json.dumps({"processed": processed, "archived": total}, ensure_ascii=False))


if __name__ == "__main__":
    main()
