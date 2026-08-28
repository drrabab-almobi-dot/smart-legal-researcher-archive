#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";

const projectRoot = process.cwd();
const splitDir = "/tmp/moj-case-split-test";
const manifestPath = path.join(splitDir, "manifest.json");
const indexPath = path.join(projectRoot, "app", "case-index.generated.json");
const destinationDir = path.join(projectRoot, "public", "library", "cases", "1434", "volume-3");

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const index = JSON.parse(fs.readFileSync(indexPath, "utf8"));
const volumeCases = index.filter((item) => item.volume === 3);

if (manifest.length !== 47 || volumeCases.length !== 47) {
  throw new Error(`Expected 47 cases; found manifest=${manifest.length}, index=${volumeCases.length}`);
}

fs.mkdirSync(destinationDir, { recursive: true });

const byKey = new Map(
  manifest.map((item, position) => [
    `${item.deedNumber || ""}|${item.lawsuitNumber || ""}`,
    { ...item, position: position + 1 },
  ]),
);

for (const item of volumeCases) {
  const key = `${item.deedNumber || ""}|${item.lawsuitNumber || ""}`;
  const match = byKey.get(key);
  if (!match) throw new Error(`No split PDF for ${item.id}`);

  const deed = item.deedNumber || "no-deed";
  const lawsuit = item.lawsuitNumber || "no-lawsuit";
  const filename = `case-${String(match.position).padStart(3, "0")}-sak-${deed}-lawsuit-${lawsuit}.pdf`;
  fs.copyFileSync(path.join(splitDir, match.file), path.join(destinationDir, filename));

  item.sourceFile = `cases/1434/volume-3/${filename}`;
  item.pdfPage = 1;
  item.archive = {
    granularity: "case",
    originalSourceFile: "moj-judgments-1434-volume-3.pdf",
    originalStartPage: match.sourceStartPage,
    originalEndPage: match.sourceEndPage,
    preservedOriginalPages: true,
  };
}

fs.writeFileSync(indexPath, `${JSON.stringify(index, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ archivedCases: volumeCases.length, destinationDir }, null, 2));
