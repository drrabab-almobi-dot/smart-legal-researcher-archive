import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { basename, resolve } from "node:path";

const inputPath = resolve(process.argv[2] || "");
const outputPath = process.argv[3] ? resolve(process.argv[3]) : null;
if (!inputPath) throw new Error("مسار ملف PDF مطلوب.");

const formatChars = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;
const marks = /[\u064b-\u065f\u0670]/g;

function clean(value) {
  return value.normalize("NFKC").replace(formatChars, "").replace(marks, "").replace(/ـ/g, " ").replace(/\s+/g, " ").trim();
}

function digits(value) {
  return value.replace(/[٠-٩]/g, (digit) => String("٠١٢٣٤٥٦٧٨٩".indexOf(digit)));
}

function specialty(value) {
  const text = clean(value);
  if (/علامة تجارية|ملكية فكرية|براءة|مصنف/.test(text)) return "ملكية فكرية";
  if (/قتل|مخدر|سرقة|حد|قصاص|سجن|جزائي|جنائي/.test(text)) return "جزائي";
  if (/زواج|طلاق|نفقة|حضانة|ارث|تركة|وصية|احوال شخصية/.test(text)) return "أحوال شخصية";
  if (/عامل|عمالي|اجور|فصل|عقد عمل/.test(text)) return "عمالي";
  if (/عقار|ارض|استحكام|ملكية|ايجار|مقاول/.test(text)) return "عقاري";
  if (/اداري|ديوان المظالم|قرار اداري|جهة حكومية/.test(text)) return "إداري";
  if (/شركة|تجاري|بيع|توريد|افلاس|تحكيم|اوراق تجارية/.test(text)) return "تجاري";
  return "أخرى";
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
  let headerEnd = Math.max(headerStart, 0);
  for (let index = headerEnd + 1; index < Math.min(lines.length, 18); index += 1) {
    if (!lines[index]) { headerEnd = index; break; }
    headerEnd = index;
  }
  const titleLines = [];
  let started = false;
  for (const line of lines.slice(headerEnd + 1, headerEnd + 15)) {
    if (!line || /^\d+$/.test(line)) { if (started) break; continue; }
    started = true;
    titleLines.push(line);
  }
  const title = titleLines.join(" ").replace(/\s*[-–]\s*/g, " - ").slice(0, 520);
  if (title.length < 18) return null;
  return { deed, lawsuit, title };
}

const bytes = readFileSync(inputPath);
const checksum = createHash("sha256").update(bytes).digest("hex");
const rawText = execFileSync("pdftotext", ["-layout", inputPath, "-"], { encoding: "utf8", maxBuffer: 96 * 1024 * 1024 });
const pages = rawText.split("\f");
const starts = [];
pages.forEach((page, index) => {
  const header = caseHeader(page);
  if (header) starts.push({ pageIndex: index, header });
});

const seen = new Set();
const cases = [];
starts.forEach((start, index) => {
  const endPage = starts[index + 1]?.pageIndex ?? pages.length;
  const caseText = clean(pages.slice(start.pageIndex, endPage).join("\n"));
  const identity = start.header.deed || start.header.lawsuit || `${start.pageIndex + 1}-${start.header.title.slice(0, 50)}`;
  if (seen.has(identity)) return;
  seen.add(identity);
  cases.push({
    id: `case-${checksum.slice(0, 12)}-${identity}`,
    granularity: "case",
    title: start.header.title,
    documentType: start.header.deed ? "صك قضائي" : "حكم قضائي",
    specialty: specialty(caseText),
    deedNumber: start.header.deed,
    lawsuitNumber: start.header.lawsuit,
    sourceFile: basename(inputPath),
    sourceChecksum: checksum,
    sourcePage: start.pageIndex + 1,
    sourceReference: `${basename(inputPath)}#page=${start.pageIndex + 1}`,
    extractedText: caseText.slice(0, 12000),
  });
});

const result = { sourceFile: basename(inputPath), sourcePages: pages.length, checksum, extractedCases: cases.length, cases };
if (outputPath) writeFileSync(outputPath, `${JSON.stringify(result, null, 2)}\n`);
console.log(JSON.stringify(result));
