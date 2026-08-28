#!/usr/bin/env python3
import json
import re
import unicodedata
from pathlib import Path

import fitz


ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ROOT / "public" / "library"
OUTPUT = ROOT / "app" / "snippet-index.generated.json"
SPECIALIZED_OUTPUT = ROOT / "app" / "specialized-case-index.generated.json"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def clean(text):
    value = unicodedata.normalize("NFKC", " ".join(text.split())).strip()
    if len(value) % 2 == 0 and value[: len(value) // 2] == value[len(value) // 2 :]:
        value = value[: len(value) // 2]
    return value


def principle_number(text, expected):
    raw = clean(text).translate(ARABIC_DIGITS)
    raw = re.sub(r"\s+", "", raw)
    if not raw.isdigit():
        return None
    value = str(expected)
    reversed_value = value[::-1]
    encodings = {
        value,
        reversed_value,
        value * 2,
        reversed_value * 2,
        "".join(character * 2 for character in value),
        "".join(character * 2 for character in reversed_value),
    }
    return expected if raw in encodings else None


def next_text(blocks, start_index):
    values = []
    for block in blocks[start_index + 1 :]:
        value = clean(block[4])
        if value:
            values.append(value)
        if len(" ".join(values)) >= 180:
            break
    return " ".join(values)[:260]


def build_principles():
    source_filename = "higher-judiciary-principles-1391-1437.pdf"
    runtime_filename = "higher-judiciary-principles-1391-1437-runtime.pdf"
    # Keep the archival master in source control without shipping a duplicate
    # copy in every production bundle. The runtime-optimized copy remains public.
    doc = fitz.open(ROOT / "source-archives" / source_filename)
    anchors = []
    expected = 1
    for page_index in range(32, 571):
        blocks = sorted(doc[page_index].get_text("blocks"), key=lambda block: (block[1], block[0]))
        for block_index, block in enumerate(blocks):
            if block[1] > 620:
                continue
            number = principle_number(block[4], expected)
            if number == expected:
                anchors.append({
                    "number": number,
                    "page": page_index + 1,
                    "y": round(max(0, block[1] - 5), 2),
                    "title": next_text(blocks, block_index),
                    "pageHeight": round(doc[page_index].rect.height, 2),
                })
                expected += 1
    if expected != 2324:
        raise RuntimeError(f"Expected principles 1-2323, stopped at {expected}")

    records = []
    for index, anchor in enumerate(anchors):
        following = anchors[index + 1] if index + 1 < len(anchors) else None
        records.append({
            "id": f"supreme-principle-{anchor['number']}",
            "documentType": "مبدأ قضائي",
            "title": f"المبدأ القضائي رقم {anchor['number']}",
            "searchText": anchor["title"],
            "sourceFile": runtime_filename,
            "startPage": anchor["page"],
            "endPage": following["page"] if following else 571,
            "startY": anchor["y"],
            "endY": round(max(0, following["y"] - 3), 2) if following else 620,
            "reference": str(anchor["number"]),
        })
    return records


def build_admin_precedents():
    filename = "bog-administrative-precedents-1402-1436.pdf"
    doc = fitz.open(LIBRARY / filename)
    anchors = []
    pattern = re.compile(r"-\s*(\d+)")
    for page_index in range(12, 358):
        blocks = sorted(doc[page_index].get_text("blocks"), key=lambda block: (block[1], block[0]))
        for block in blocks:
            value = clean(block[4])
            match = pattern.search(value)
            if not match or block[1] > 610:
                continue
            # A chapter taxonomy line on page 296 contains OCR'd list separators
            # that resemble a record number; it is not a precedent boundary.
            if page_index + 1 == 296 and block[1] < 100:
                continue
            title = pattern.sub("", value, count=1).strip(" .-؛")
            if len(title) < 12:
                continue
            anchors.append({
                "localNumber": match.group(1),
                "page": page_index + 1,
                "y": round(max(0, block[1] - 5), 2),
                "title": title[:300],
            })
    if len(anchors) != 1317:
        raise RuntimeError(f"Expected 1317 trusted administrative anchors, found {len(anchors)}")

    records = []
    for index, anchor in enumerate(anchors):
        following = anchors[index + 1] if index + 1 < len(anchors) else None
        records.append({
            "id": f"bog-precedent-{index + 1}",
            "documentType": "سابقة قضائية",
            "title": f"سابقة قضائية إدارية - السجل {index + 1}",
            "searchText": anchor["title"],
            "sourceFile": filename,
            "startPage": anchor["page"],
            "endPage": following["page"] if following else 358,
            "startY": anchor["y"],
            "endY": round(max(0, following["y"] - 3), 2) if following else 610,
            "reference": f"السابقة {anchor['localNumber']} - سجل {index + 1}",
        })
    return records


def build_commercial_precedents():
    filename = "commercial-contract-precedents.pdf"
    end_pages = [
        61, 79, 82, 85, 96, 116, 123, 126, 133, 136, 146, 154, 161, 177,
        185, 195, 217, 236, 248, 263, 271, 284, 309, 319, 327, 336, 363,
        381, 394, 408, 422, 429, 442, 451, 458, 480, 481, 492, 501, 517,
        531, 541, 549, 558, 572, 580, 593,
    ]
    divider_pages = {117, 138, 139, 178, 237, 272, 299, 320, 430, 532, 550, 559, 560}
    records = []
    start_page = 35
    for index, end_page in enumerate(end_pages, start=1):
        while start_page in divider_pages:
            start_page += 1
        excluded = sorted(page for page in divider_pages if start_page <= page <= end_page)
        records.append({
            "id": f"commercial-precedent-{index}",
            "documentType": "سابقة قضائية",
            "title": f"سابقة قضائية في عقود المعاوضات التجارية - السجل {index}",
            "sourceFile": filename,
            "startPage": start_page,
            "endPage": end_page,
            "excludedPages": excluded,
            "reference": str(index),
        })
        start_page = end_page + 1
    return records


records = build_principles() + build_admin_precedents()
OUTPUT.write_text(json.dumps(records, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
existing_specialized = json.loads(SPECIALIZED_OUTPUT.read_text(encoding="utf-8"))
specialized = [item for item in existing_specialized if not item["id"].startswith("commercial-precedent-")]
specialized.extend(build_commercial_precedents())
SPECIALIZED_OUTPUT.write_text(json.dumps(specialized, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(json.dumps({
    "principles": sum(item["documentType"] == "مبدأ قضائي" for item in records),
    "precedents": sum(item["documentType"] == "سابقة قضائية" for item in records),
    "commercialPrecedents": 47,
    "total": len(records),
}, ensure_ascii=False))
