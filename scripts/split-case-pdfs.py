#!/usr/bin/env python3
import json
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: split-case-pdfs.py SOURCE.pdf CASES.json OUTPUT_DIR")

    source_path = Path(sys.argv[1]).resolve()
    index_path = Path(sys.argv[2]).resolve()
    output_dir = Path(sys.argv[3]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads(index_path.read_text(encoding="utf-8"))
    cases = index["cases"]
    reader = PdfReader(str(source_path))
    manifest = []

    for position, case in enumerate(cases):
        start_page = int(case["sourcePage"]) - 1
        next_page = int(cases[position + 1]["sourcePage"]) - 1 if position + 1 < len(cases) else len(reader.pages)
        end_page = max(start_page + 1, next_page)
        deed = case.get("deedNumber") or "no-deed"
        lawsuit = case.get("lawsuitNumber") or "no-lawsuit"
        filename = f"case-{position + 1:03d}-sak-{deed}- دعوى-{lawsuit}.pdf"
        target = output_dir / filename

        writer = PdfWriter()
        for page_number in range(start_page, min(end_page, len(reader.pages))):
            writer.add_page(reader.pages[page_number])
        writer.add_metadata({
            "/Title": case["title"],
            "/Subject": "قضية مستقلة مستخرجة دون تغيير من مدونة وزارة العدل",
            "/SourceFile": source_path.name,
            "/SourcePage": str(start_page + 1),
        })
        with target.open("wb") as stream:
            writer.write(stream)

        manifest.append({
            "file": filename,
            "title": case["title"],
            "deedNumber": case.get("deedNumber"),
            "lawsuitNumber": case.get("lawsuitNumber"),
            "sourceFile": source_path.name,
            "sourceStartPage": start_page + 1,
            "sourceEndPage": min(end_page, len(reader.pages)),
            "pages": min(end_page, len(reader.pages)) - start_page,
        })

    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"source": source_path.name, "cases": len(manifest), "output": str(output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
