import { normalizeArabic } from "./arabic-search";
import { requireArchiveBindings } from "./archive-storage";

export type ImportedJudgment = {
  id: string;
  title: string;
  referenceNo?: string | null;
  courtName?: string | null;
  city?: string | null;
  hijriYear?: string | number | null;
  specialty?: string | null;
  summary?: string | null;
  extractedText: string;
  sourceUrl: string;
};

function clean(value: unknown, max = 1_500_000) {
  return String(value ?? "").replace(/\0/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

function validSourceUrl(value: string) {
  try {
    const url = new URL(value);
    return /(^|\.)laws\.moj\.gov\.sa$/i.test(url.hostname) ? url.toString() : null;
  } catch { return null; }
}

export async function importJudgmentBatch(input: unknown) {
  const rows = Array.isArray(input) ? input as ImportedJudgment[] : [];
  if (!rows.length || rows.length > 1_000) throw new Error("دفعة الأحكام يجب أن تحتوي بين 1 و1000 سجل.");
  const { DB } = requireArchiveBindings();
  let processed = 0;
  let rejected = 0;

  for (let offset = 0; offset < rows.length; offset += 75) {
    const statements: D1PreparedStatement[] = [];
    for (const row of rows.slice(offset, offset + 75)) {
      const officialId = clean(row.id, 180);
      const title = clean(row.title, 500);
      const extractedText = normalizeArabic(clean(row.extractedText));
      const sourceUrl = validSourceUrl(clean(row.sourceUrl, 1_000));
      if (!officialId || !title || extractedText.length < 40 || !sourceUrl) { rejected += 1; continue; }
      const courtName = clean(row.courtName, 300) || "محاكم وزارة العدل";
      const city = clean(row.city, 120) || null;
      const specialty = clean(row.specialty, 80) || "أخرى";
      statements.push(DB.prepare(`
        INSERT INTO legal_documents (
          id, title, document_type, issuer, publishing_authority, originating_authority,
          hijri_year, reference_no, subject, summary, extracted_text, source_kind,
          source_url, source_label, granularity, specialty, verified, created_at, updated_at
        ) VALUES (?, ?, 'حكم قضائي', ?, 'وزارة العدل', ?, ?, ?, ?, ?, ?, 'official_moj', ?,
          'بوابة الأحكام القضائية الرسمية بوزارة العدل', 'case', ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
          title = excluded.title, issuer = excluded.issuer, publishing_authority = excluded.publishing_authority,
          originating_authority = excluded.originating_authority, hijri_year = excluded.hijri_year,
          reference_no = excluded.reference_no, subject = excluded.subject, summary = excluded.summary,
          extracted_text = excluded.extracted_text, source_url = excluded.source_url,
          granularity = 'case', specialty = excluded.specialty, verified = 1, updated_at = CURRENT_TIMESTAMP
      `).bind(
        `moj-judgment-${officialId}`, title, courtName, courtName,
        clean(row.hijriYear, 20) || null, clean(row.referenceNo, 180) || officialId,
        [courtName, city, specialty].filter(Boolean).join(" — "),
        clean(row.summary, 1_000) || `حكم مستقل صادر من ${courtName}${city ? ` في ${city}` : ""}.`,
        extractedText, sourceUrl, specialty,
      ));
    }
    if (statements.length) {
      await DB.batch(statements);
      processed += statements.length;
    }
  }
  return { processed, rejected };
}
