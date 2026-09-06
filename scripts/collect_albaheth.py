#!/usr/bin/env python3
import argparse, hashlib, json, os, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

BASE = "https://albaheth.app"
UA = "RababLegalArchive/1.0 (+archival research; respectful crawler)"


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def extract_value(text, label):
    m = re.search(rf"{re.escape(label)}\s*[:：]?\s*([^\n]+)", text)
    return norm(m.group(1)) if m else None


def load_existing(path):
    ids, hashes = set(), set()
    if not path.exists():
        return ids, hashes
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
                if r.get("source_id") is not None: ids.add(int(r["source_id"]))
                if r.get("text_sha256"): hashes.add(r["text_sha256"])
            except Exception:
                pass
    return ids, hashes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, required=True)
    ap.add_argument("--end", type=int, required=True)
    ap.add_argument("--delay", type=float, default=0.45)
    args = ap.parse_args()

    out = Path("archive-sources/albaheth/albaheth-judgments.ndjson")
    manifest = Path("manifests/albaheth/source-register.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)

    rp = RobotFileParser()
    rp.set_url(urljoin(BASE, "/robots.txt"))
    try:
        rp.read()
        if not rp.can_fetch(UA, urljoin(BASE, "/judgment/1")):
            raise SystemExit("robots.txt disallows judgment crawling")
    except Exception as e:
        print(f"robots check warning: {e}")

    seen_ids, seen_hashes = load_existing(out)
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})

    new_records = []
    rows = []
    stats = {"requested":0,"found":0,"new":0,"duplicate":0,"missing":0,"errors":0}

    for i in range(args.start, args.end + 1):
        if i in seen_ids:
            continue
        stats["requested"] += 1
        u = f"{BASE}/judgment/{i}"
        try:
            r = s.get(u, timeout=25, allow_redirects=True)
            if r.status_code == 404:
                stats["missing"] += 1
                continue
            if r.status_code != 200:
                stats["errors"] += 1
                rows.append((i,r.status_code,"http_error",r.url))
                time.sleep(args.delay)
                continue
            if "/judgment/" not in r.url:
                stats["missing"] += 1
                continue

            soup = BeautifulSoup(r.text, "lxml")
            main_el = soup.find("main") or soup.body
            text = norm(main_el.get_text("\n", strip=True) if main_el else soup.get_text("\n", strip=True))
            if len(text) < 120 or "رقم الحكم" not in text:
                stats["missing"] += 1
                continue

            stats["found"] += 1
            title = norm((soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else soup.title.get_text(" ", strip=True) if soup.title else ""))
            judgment_number = extract_value(text, "رقم الحكم")
            case_number = extract_value(text, "رقم القضية")
            year = extract_value(text, "سنة الحكم")
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            duplicate = h in seen_hashes
            rec = {
                "source": "albaheth.app",
                "source_id": i,
                "source_url": r.url,
                "title": title,
                "case_number": case_number,
                "judgment_number": judgment_number,
                "year": year,
                "text": text,
                "text_sha256": h,
                "duplicate_text": duplicate,
                "collected_at": datetime.now(timezone.utc).isoformat()
            }
            if duplicate:
                stats["duplicate"] += 1
            else:
                new_records.append(rec)
                seen_hashes.add(h)
                stats["new"] += 1
            rows.append((i,200,"duplicate" if duplicate else "archived",r.url))
        except Exception as e:
            stats["errors"] += 1
            rows.append((i,"",f"error:{type(e).__name__}",u))
        finally:
            time.sleep(args.delay)

    if new_records:
        with out.open("a", encoding="utf-8") as f:
            for rec in new_records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    new_manifest = not manifest.exists()
    with manifest.open("a", encoding="utf-8") as f:
        if new_manifest:
            f.write("source_id,http_status,status,source_url\n")
        for row in rows:
            f.write(",".join('"'+str(x).replace('"','""')+'"' for x in row)+"\n")

    summary = Path("manifests/albaheth/summary.json")
    summary.write_text(json.dumps({
        "range": [args.start,args.end],
        "stats": stats,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "archive_file": str(out)
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))

if __name__ == "__main__":
    main()
