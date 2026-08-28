import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { basename, join, resolve } from "node:path";

const sourceDir = resolve(process.argv[2] || ".");
const outputPath = resolve(process.argv[3] || "app/case-index.generated.json");

const volumes = [
  [3, "3-1(2).pdf"],
  [4, "4-1(2).pdf"],
  [6, "6(2).pdf"],
  [7, "7(2).pdf"],
  [8, "8(2).pdf"],
  [9, "9(2).pdf"],
  [10, "10(2).pdf"],
  [12, "12(2).pdf"],
  [14, "14(2).pdf"],
  [15, "15(2).pdf"],
  [16, "16(2).pdf"],
  [17, "_سوابق مخدرات (2).pdf"],
  [18, "18.pdf"],
  [19, "19.pdf"],
  [20, "20.pdf"],
  [21, "21.pdf"],
  [22, "22.pdf"],
  [23, "23.pdf"],
  [24, "24.pdf"],
  [25, "25.pdf"],
  [26, "26_2 مجموعة الاحكام القضائسة.pdf"],
  [27, "27.pdf"],
  [28, "28.pdf"],
  [29, "29-1.pdf"],
  [30, "30.pdf"],
];

const formatChars = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;
const marks = /[\u064b-\u065f\u0670]/g;

function clean(value) {
  return value
    .normalize("NFKC")
    .replace(formatChars, "")
    .replace(marks, "")
    .replace(/ـ/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function digits(value) {
  return value.replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
}

function caseHeader(page) {
  const lines = page.split(/\r?\n/).map(clean);
  const firstLines = lines.slice(0, 18);
  const compact = digits(firstLines.join(" ")).replace(/\s+/g, "");
  if (!compact.includes("الصك") || !compact.includes("الدعوى")) return null;

  const deed = compact.match(/الصك[:：]?([0-9]{4,})/)?.[1] ?? null;
  const lawsuit = compact.match(/الدعوى[:：]?([0-9]{4,})/)?.[1] ?? null;
  if (!deed && !lawsuit) return null;

  const headerStart = firstLines.findIndex((line) => line.replace(/\s+/g, "").includes("الصك"));
  let headerEnd = headerStart;
  for (let index = headerStart + 1; index < Math.min(lines.length, 18); index += 1) {
    if (!lines[index]) {
      headerEnd = index;
      break;
    }
    headerEnd = index;
  }

  const titleLines = [];
  let started = false;
  for (const line of lines.slice(headerEnd + 1, headerEnd + 15)) {
    if (!line || /^\d+$/.test(line)) {
      if (started) break;
      continue;
    }
    started = true;
    titleLines.push(line);
  }

  const title = titleLines.join(" ").replace(/\s*[-–]\s*/g, " - ").slice(0, 520);
  if (title.length < 18) return null;
  return { deed, lawsuit, title };
}

const records = [];
const referenceTexts = {};
for (const [volume, fileName] of volumes) {
  const inputPath = join(sourceDir, fileName);
  const bytes = readFileSync(inputPath);
  const checksum = createHash("sha256").update(bytes).digest("hex");
  const text = execFileSync("pdftotext", ["-layout", inputPath, "-"], {
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (volume >= 29) referenceTexts[volume] = clean(text).slice(0, 120_000);

  const seen = new Set();
  text.split("\f").forEach((page, index) => {
    const header = caseHeader(page);
    if (!header) return;
    const identity = header.deed || header.lawsuit || `${index + 1}-${header.title.slice(0, 40)}`;
    if (seen.has(identity)) return;
    seen.add(identity);
    records.push({
      id: `moj-1434-v${volume}-p${index + 1}-${identity}`,
      volume,
      pdfPage: index + 1,
      deedNumber: header.deed,
      lawsuitNumber: header.lawsuit,
      title: header.title,
      searchText: clean(page).slice(0, 1600),
      sourceFile: `moj-judgments-1434-volume-${volume}.pdf`,
      sourceChecksum: checksum,
    });
  });
}

writeFileSync(outputPath, `${JSON.stringify(records, null, 2)}\n`);
writeFileSync(
  outputPath.replace("case-index.generated.json", "reference-text.generated.json"),
  `${JSON.stringify(referenceTexts, null, 2)}\n`,
);
console.log(`Generated ${records.length} case records from ${volumes.length} unique volumes at ${basename(outputPath)}.`);
