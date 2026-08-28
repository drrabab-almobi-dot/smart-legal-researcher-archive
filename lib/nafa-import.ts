import { normalizeArabic } from "./arabic-search";
import { requireArchiveBindings } from "./archive-storage";

type NafaDocument = {
  id?: unknown;
  title?: unknown;
  documentType?: unknown;
  referenceNo?: unknown;
  issuer?: unknown;
  publishingAuthority?: unknown;
  originatingAuthority?: unknown;
  hijriYear?: unknown;
  specialty?: unknown;
  summary?: unknown;
  extractedText?: unknown;
  sourceUrl?: unknown;
  textChecksum?: unknown;
};

const ALLOWED_TYPES = new Set([
  "حكم قضائي",
  "تعميم",
  "قرار",
  "مبدأ قضائي",
  "سابقة قضائية",
  "نظام أو لائحة",
  "بحث قانوني",
  "مرجع قانوني",
]);

function clean(value: unknown, max = 1_500_000) {
  return String(value ?? "").replace(/\0/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

function validSourceUrl(value: unknown) {
  try {
    const url = new URL(clean(value, 1_000));
    return url.protocol === "https:" || url.protocol === "http:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export async function importNafaBatch(input: unknown) {
  const rows = Array.isArray(input) ? input as NafaDocument[] : [];
  if (!rows.length || rows.length > 250) throw new Error("دفعة نفع يجب أن تحتوي بين 1 و250 سجلًا.");
  const { DB } = requireArchiveBindings();
  let added = 0;
  let updated = 0;
  let duplicates = 0;
  let rejected = 0;

  for (const row of rows) {
    const id = clean(row.id, 180);
    const title = clean(row.title, 500);
    const documentType = clean(row.documentType, 80);
    const extractedText = normalizeArabic(clean(row.extractedText));
    const sourceUrl = validSourceUrl(row.sourceUrl);
    const textChecksum = clean(row.textChecksum, 64).toLowerCase();
    if (!/^nafa-[A-Za-z0-9_-]+$/.test(id) || !title || !ALLOWED_TYPES.has(documentType)
      || extractedText.length < 40 || !sourceUrl || !/^[a-f0-9]{64}$/.test(textChecksum)) {
      rejected += 1;
      continue;
    }

    const existing = await DB.prepare(
      "SELECT id FROM legal_documents WHERE id = ? OR text_checksum = ? LIMIT 1",
    ).bind(id, textChecksum).first<{ id: string }>();
    if (existing && existing.id !== id) {
      duplicates += 1;
      continue;
    }

    const issuer = clean(row.issuer, 300) || "مكتبة نفع القضائية";
    const publishingAuthority = clean(row.publishingAuthority, 300) || issuer;
    const originatingAuthority = clean(row.originatingAuthority, 300) || null;
    const referenceNo = clean(row.referenceNo, 180) || null;
    const specialty = clean(row.specialty, 80) || "أخرى";
    const granularity = documentType === "حكم قضائي" || documentType === "سابقة قضائية"
      ? "case"
      : "document";
    await DB.prepare(`
      INSERT INTO legal_documents (
        id, title, document_type, issuer, publishing_authority, originating_authority,
        hijri_year, reference_no, subject, summary, extracted_text, text_checksum,
        source_kind, source_url, source_label, granularity, specialty, verified,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'nafa_library', ?,
        'مكتبة نفع القضائية — دليل 1445هـ', ?, ?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
      ON CONFLICT(id) DO UPDATE SET
        title = excluded.title, document_type = excluded.document_type,
        issuer = excluded.issuer, publishing_authority = excluded.publishing_authority,
        originating_authority = excluded.originating_authority,
        hijri_year = excluded.hijri_year, reference_no = excluded.reference_no,
        subject = excluded.subject, summary = excluded.summary,
        extracted_text = excluded.extracted_text, text_checksum = excluded.text_checksum,
        source_url = excluded.source_url, granularity = excluded.granularity,
        specialty = excluded.specialty, verified = 1, updated_at = CURRENT_TIMESTAMP
    `).bind(
      id, title, documentType, issuer, publishingAuthority, originatingAuthority,
      clean(row.hijriYear, 20) || null, referenceNo,
      [documentType, referenceNo, specialty].filter(Boolean).join(" — "),
      clean(row.summary, 1_000) || `${documentType} مستخرج من مكتبة نفع القضائية.`,
      extractedText, textChecksum, sourceUrl, granularity, specialty,
    ).run();
    if (existing) updated += 1;
    else added += 1;
  }

  return { processed: added + updated, added, updated, duplicates, rejected };
}
