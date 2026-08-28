import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const sourceDir = resolve(process.argv[2] || ".");
const outputPath = resolve(process.argv[3] || "app/specialized-text.generated.json");

const documents = [
  ["uncitral-arbitration-2024", "770924071-سوابق-قضائية-دولية-في-التحيكم-2024(1).pdf"],
  ["bog-administrative-precedents", "السوابق القضائية (1).pdf"],
  ["nafa-judicial-library", "939792676-مكتبة-نفع-القضائية(1).pdf"],
  ["ip-judgments-1446", "أحكام قضائية في الملكية الفكرية(1).pdf"],
  ["ip-precedents", "السوابق_القضائية_في_الملكية_الفكرية(1).pdf"],
  ["insurance-precedents", "السوابق القضائية التأمينية(1).pdf"],
  ["banking-finance-principles", "المبادىء القضائية في المنازعات المصرفية والتمويلية(1).pdf"],
  ["higher-judiciary-principles", "المبادئ والقرارات الصادرة من المحكمة العليا(1).pdf"],
  ["judicial-precedents-compilation", "تجميعات سوابق قضائية(1).pdf"],
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

const index = {};
for (const [id, fileName] of documents) {
  const inputPath = join(sourceDir, fileName);
  readFileSync(inputPath);
  const text = execFileSync("pdftotext", ["-layout", inputPath, "-"], {
    encoding: "utf8",
    maxBuffer: 128 * 1024 * 1024,
  });
  const pages = text.split("\f");
  const perPage = Math.max(500, Math.min(1400, Math.floor(400_000 / Math.max(pages.length, 1))));
  index[id] = pages.map((page) => clean(page).slice(0, perPage)).filter(Boolean).join(" ").slice(0, 400_000);
}

writeFileSync(outputPath, `${JSON.stringify(index, null, 2)}\n`);
console.log(`Generated searchable text for ${documents.length} specialized references.`);
