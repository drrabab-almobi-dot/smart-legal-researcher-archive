export type ArchiveSourceKind = "computer" | "telegram" | "official_moj" | "official_bog" | "nafa_library";

export type ArchiveRecord = {
  id: string;
  fileName: string;
  relativePath: string | null;
  objectKey: string;
  mimeType: string;
  sizeBytes: number;
  checksum: string;
  searchText: string;
  sourceKind: ArchiveSourceKind;
  sourceLabel: string;
  telegramChatId: string | null;
  telegramMessageId: string | null;
  status: "pending_indexing" | "indexed" | "duplicate" | "failed";
  documentType: string;
  issuer: string | null;
  publishingAuthority: string | null;
  originatingAuthority: string | null;
  hijriYear: string | null;
  referenceNo: string | null;
  subject: string | null;
  uploadedBy: string;
  createdAt: string;
  indexedAt: string | null;
  relevance?: number;
  matchContext?: string | null;
  matchedTerms?: string[];
};

export type LegalDocumentRecord = {
  id: string;
  title: string;
  documentType: string;
  issuer: string | null;
  publishingAuthority: string | null;
  originatingAuthority: string | null;
  hijriYear: string | null;
  referenceNo: string | null;
  subject: string | null;
  summary: string;
  sourceKind: ArchiveSourceKind;
  sourceUrl: string | null;
  sourceLabel: string;
  granularity: "case" | "document";
  specialty: string;
  verified: boolean;
  caseNumber?: string | null;
  judgmentNumber?: string | null;
  court?: string | null;
  circuit?: string | null;
  relevance?: number;
  matchContext?: string | null;
  matchedTerms?: string[];
};

export type LegalDocumentDetail = LegalDocumentRecord & { extractedText: string };

import { legalSearchTerms, normalizeArabic, relevanceScore, textExcerpt } from "./arabic-search";

export type ArchiveBindings = {
  DB?: D1Database;
  BUCKET?: R2Bucket;
  TELEGRAM_BOT_TOKEN?: string;
  TELEGRAM_CHANNEL_ID?: string;
  ARCHIVE_IMPORT_TOKEN?: string;
};

const ARCHIVE_SELECT = `
  SELECT
    id,
    file_name AS fileName,
    relative_path AS relativePath,
    object_key AS objectKey,
    mime_type AS mimeType,
    size_bytes AS sizeBytes,
    checksum,
    search_text AS searchText,
    source_kind AS sourceKind,
    source_label AS sourceLabel,
    telegram_chat_id AS telegramChatId,
    telegram_message_id AS telegramMessageId,
    status,
    document_type AS documentType,
    issuer,
    publishing_authority AS publishingAuthority,
    originating_authority AS originatingAuthority,
    hijri_year AS hijriYear,
    reference_no AS referenceNo,
    subject,
    uploaded_by AS uploadedBy,
    created_at AS createdAt,
    indexed_at AS indexedAt
  FROM archive_files
`;

export const ACCEPTED_EXTENSIONS = new Set([
  "pdf",
  "doc",
  "docx",
  "txt",
  "rtf",
  "odt",
  "xls",
  "xlsx",
  "csv",
  "jpg",
  "jpeg",
  "png",
  "tif",
  "tiff",
  "html",
  "htm",
  "md",
  "json",
  "xml",
  "gz",
]);

export function getArchiveBindings() {
  return (
    globalThis as typeof globalThis & {
      __LEGAL_ARCHIVE_ENV__?: ArchiveBindings;
    }
  ).__LEGAL_ARCHIVE_ENV__ ?? {};
}

export function requireArchiveBindings() {
  const bindings = getArchiveBindings();
  if (!bindings.DB || !bindings.BUCKET) {
    throw new Error("خدمة الأرشيف غير مهيأة في بيئة التشغيل.");
  }
  return { DB: bindings.DB, BUCKET: bindings.BUCKET };
}

export function authenticatedEmail(request: Request) {
  const email = request.headers.get("oai-authenticated-user-email")?.trim();
  return email || null;
}

export function fileExtension(fileName: string) {
  return fileName.split(".").pop()?.toLocaleLowerCase("en") ?? "";
}

export function isAcceptedFile(fileName: string) {
  return ACCEPTED_EXTENSIONS.has(fileExtension(fileName));
}

export function safeFileName(fileName: string) {
  const cleaned = fileName
    .normalize("NFKC")
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, "-")
    .replace(/\s+/g, " ")
    .trim();
  return (cleaned || "document").slice(0, 180);
}

function inferMetadata(fileName: string) {
  const normalized = fileName.replace(/[_-]+/g, " ");
  const year = normalized.match(/(?:13|14)\d{2}/)?.[0] ?? null;
  const issuer = /ديوان\s*المظالم|مظالم/.test(normalized)
    ? "ديوان المظالم"
    : /وزارة\s*العدل|العدل/.test(normalized)
      ? "وزارة العدل"
      : /المجلس\s*الأعلى\s*للقضاء/.test(normalized)
        ? "المجلس الأعلى للقضاء"
      : null;
  const documentType = /صك/.test(normalized)
    ? "صك قضائي"
    : /تعميم/.test(normalized)
    ? issuer === "المجلس الأعلى للقضاء" ? "تعميم قضائي" : "تعميم وزاري"
    : /مبدأ|مبادئ/.test(normalized)
      ? "مبدأ قضائي"
      : /حكم|أحكام/.test(normalized)
        ? "مجموعة أحكام"
        : "مدونة قضائية";
  const subject = normalized.replace(/\.[^.]+$/, "").trim().slice(0, 240) || null;
  return {
    year,
    issuer,
    publishingAuthority: issuer,
    originatingAuthority: issuer,
    documentType,
    subject,
  };
}

function extractIndexableText(bytes: ArrayBuffer, fileName: string, mimeType: string) {
  const extension = fileExtension(fileName);
  const textLike = new Set(["txt", "csv", "html", "htm", "md", "json", "xml"]);
  if (!textLike.has(extension) && !mimeType.startsWith("text/")) return "";

  const capped = bytes.slice(0, Math.min(bytes.byteLength, 2 * 1024 * 1024));
  let text = new TextDecoder("utf-8", { fatal: false }).decode(capped);
  if (extension === "html" || extension === "htm") {
    text = text
      .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;|&#160;/gi, " ")
      .replace(/&amp;/gi, "&")
      .replace(/&lt;/gi, "<")
      .replace(/&gt;/gi, ">");
  }
  return text.replace(/\0/g, " ").replace(/\s+/g, " ").trim().slice(0, 1_500_000);
}

async function sha256Hex(bytes: ArrayBuffer) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function archiveBytes(input: {
  bytes: ArrayBuffer;
  fileName: string;
  relativePath?: string | null;
  mimeType?: string | null;
  sourceKind: ArchiveSourceKind;
  sourceLabel: string;
  uploadedBy: string;
  telegramChatId?: string | null;
  telegramMessageId?: string | null;
}) {
  const { DB, BUCKET } = requireArchiveBindings();
  const checksum = await sha256Hex(input.bytes);
  const duplicate = await DB.prepare(`${ARCHIVE_SELECT} WHERE checksum = ? LIMIT 1`)
    .bind(checksum)
    .first<ArchiveRecord>();

  if (duplicate) return { record: duplicate, duplicate: true };

  const id = crypto.randomUUID();
  const fileName = safeFileName(input.fileName);
  const datePath = new Date().toISOString().slice(0, 10);
  const objectKey = `judicial-blogs/${datePath}/${id}-${fileName}`;
  const metadata = inferMetadata(fileName);
  const mimeType = input.mimeType?.trim() || "application/octet-stream";
  const extractedText = extractIndexableText(input.bytes, fileName, mimeType);
  const searchText = normalizeArabic(
    [
      fileName,
      input.relativePath,
      metadata.documentType,
      metadata.issuer,
      metadata.publishingAuthority,
      metadata.originatingAuthority,
      metadata.year,
      metadata.subject,
      extractedText,
    ]
      .filter(Boolean)
      .join(" "),
  );

  await BUCKET.put(objectKey, input.bytes, {
    httpMetadata: { contentType: mimeType },
    customMetadata: {
      sourceKind: input.sourceKind,
      uploadedBy: input.uploadedBy,
    },
  });

  try {
    await DB.prepare(`
      INSERT INTO archive_files (
        id, file_name, relative_path, object_key, mime_type, size_bytes,
        checksum, search_text, source_kind, source_label, telegram_chat_id,
        telegram_message_id, status, document_type, issuer,
        publishing_authority, originating_authority, hijri_year,
        subject, uploaded_by, indexed_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `)
      .bind(
        id,
        fileName,
        input.relativePath?.slice(0, 500) || null,
        objectKey,
        mimeType,
        input.bytes.byteLength,
        checksum,
        searchText,
        input.sourceKind,
        input.sourceLabel.slice(0, 240),
        input.telegramChatId || null,
        input.telegramMessageId || null,
        extractedText ? "indexed" : "pending_indexing",
        metadata.documentType,
        metadata.issuer,
        metadata.publishingAuthority,
        metadata.originatingAuthority,
        metadata.year,
        metadata.subject,
        input.uploadedBy,
        extractedText ? new Date().toISOString() : null,
      )
      .run();
  } catch (error) {
    await BUCKET.delete(objectKey);
    throw error;
  }

  const record = await DB.prepare(`${ARCHIVE_SELECT} WHERE id = ? LIMIT 1`)
    .bind(id)
    .first<ArchiveRecord>();
  if (!record) throw new Error("تعذر قراءة سجل الملف بعد حفظه.");
  return { record, duplicate: false };
}

export async function listArchiveFiles(query = "", limit = 30) {
  const { DB } = requireArchiveBindings();
  const safeLimit = Math.min(Math.max(limit, 1), 100);
  const normalizedQuery = query.trim().slice(0, 120);
  if (!normalizedQuery) {
    const result = await DB.prepare(
      `${ARCHIVE_SELECT} WHERE source_kind <> 'telegram' ORDER BY created_at DESC LIMIT ?`,
    )
      .bind(safeLimit)
      .all<ArchiveRecord>();
    return result.results;
  }

  const { expanded } = legalSearchTerms(normalizedQuery);
  const terms = expanded.length ? expanded : [normalizeArabic(normalizedQuery)];
  const clauses = terms.map(() => "search_text LIKE ?").join(" OR ");
  const patterns = terms.map((term) => `%${term}%`);
  const result = await DB.prepare(`
    ${ARCHIVE_SELECT}
    WHERE source_kind <> 'telegram' AND (${clauses})
    ORDER BY created_at DESC
    LIMIT 250
  `)
    .bind(...patterns)
    .all<ArchiveRecord>();

  return result.results
    .map((record) => {
      const ranked = relevanceScore({
        title: record.fileName,
        reference: record.referenceNo,
        subject: record.subject,
        summary: `${record.documentType} ${record.publishingAuthority ?? record.issuer ?? ""} ${record.originatingAuthority ?? ""} ${record.hijriYear ?? ""}`,
        fullText: record.searchText,
      }, normalizedQuery);
      return {
        ...record,
        relevance: ranked.score,
        matchedTerms: ranked.matchedTerms,
        matchContext: textExcerpt(record.searchText, normalizedQuery),
      };
    })
    .filter((record) => (record.relevance ?? 0) > 0)
    .sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0))
    .slice(0, safeLimit);
}

export async function listLegalDocuments(query = "", limit = 40) {
  const { DB } = requireArchiveBindings();
  const normalizedQuery = query.trim().slice(0, 120);
  if (!normalizedQuery) return [] as LegalDocumentRecord[];
  const { expanded } = legalSearchTerms(normalizedQuery);
  const terms = expanded.length ? expanded : [normalizeArabic(normalizedQuery)];
  const clauses = terms.map(() => "(title LIKE ? OR reference_no LIKE ? OR subject LIKE ? OR extracted_text LIKE ?)").join(" OR ");
  const bindings = terms.flatMap((term) => Array(4).fill(`%${term}%`));
  const result = await DB.prepare(`
    SELECT id, title, document_type AS documentType, issuer,
      publishing_authority AS publishingAuthority,
      originating_authority AS originatingAuthority,
      hijri_year AS hijriYear, reference_no AS referenceNo, subject,
      summary, source_kind AS sourceKind, source_url AS sourceUrl,
      source_label AS sourceLabel, granularity, specialty, verified,
      extracted_text AS extractedText
    FROM legal_documents
    WHERE source_kind <> 'telegram'
      AND granularity = 'case'
      AND (${clauses})
    ORDER BY updated_at DESC
    LIMIT 250
  `).bind(...bindings).all<LegalDocumentRecord & { extractedText: string }>();

  return result.results.map((record) => {
    const ranked = relevanceScore({
      title: record.title,
      reference: record.referenceNo,
      subject: record.subject,
      summary: record.summary,
      fullText: record.extractedText,
    }, normalizedQuery);
    const { extractedText, ...publicRecord } = record;
    const metadata = extractLegalDocumentMetadata(record);
    return {
      ...publicRecord,
      ...metadata,
      verified: Boolean(record.verified),
      relevance: ranked.score,
      matchedTerms: ranked.matchedTerms,
      matchContext: textExcerpt(extractedText, normalizedQuery),
    };
  }).filter((record) => (record.relevance ?? 0) > 0)
    .sort((a, b) => (b.relevance ?? 0) - (a.relevance ?? 0))
    .slice(0, Math.min(Math.max(limit, 1), 100));
}

function firstCaptured(text: string, patterns: RegExp[]) {
  for (const pattern of patterns) {
    const value = text.match(pattern)?.[1]?.trim();
    if (value) return value.slice(0, 120);
  }
  return null;
}

export function extractLegalDocumentMetadata(record: {
  title: string;
  referenceNo?: string | null;
  issuer?: string | null;
  originatingAuthority?: string | null;
  subject?: string | null;
  summary?: string | null;
  extractedText?: string | null;
}) {
  const text = [record.title, record.subject, record.summary, record.extractedText]
    .filter(Boolean)
    .join(" \n ");
  const number = "([0-9٠-٩]+(?:\\s*[/\\-]\\s*[0-9٠-٩]+)*)";
  const caseNumber = firstCaptured(text, [
    new RegExp(`(?:رقم\\s*(?:القضية|الدعوى)|(?:القضية|الدعوى)\\s*رقم)\\s*[:：]?\\s*${number}`, "i"),
  ]);
  const judgmentNumber = firstCaptured(text, [
    new RegExp(`(?:رقم\\s*(?:الحكم|الصك)|(?:الحكم|الصك)\\s*رقم)\\s*[:：]?\\s*${number}`, "i"),
  ]) ?? record.referenceNo?.trim() ?? null;
  const circuit = firstCaptured(text, [
    /(?:الدائرة)\s*[:：]?\s*([^،.\n]{2,80})/i,
  ]);
  const court = record.issuer?.trim()
    || record.originatingAuthority?.trim()
    || firstCaptured(text, [/(المحكمة\s+(?:التجارية|العامة|الجزائية|الإدارية|العمالية|العليا|الاستئناف)(?:\s+في\s+[^،.\n]{2,50})?)/i]);
  return { caseNumber, judgmentNumber, court, circuit };
}

export async function getLegalDocument(id: string) {
  const { DB } = requireArchiveBindings();
  const record = await DB.prepare(`
    SELECT id, title, document_type AS documentType, issuer,
      publishing_authority AS publishingAuthority,
      originating_authority AS originatingAuthority,
      hijri_year AS hijriYear, reference_no AS referenceNo, subject,
      summary, source_kind AS sourceKind, source_url AS sourceUrl,
      source_label AS sourceLabel, granularity, specialty, verified,
      extracted_text AS extractedText
    FROM legal_documents
    WHERE id = ? AND granularity = 'case'
    LIMIT 1
  `).bind(id).first<LegalDocumentDetail>();
  if (!record) return null;
  return { ...record, verified: Boolean(record.verified), ...extractLegalDocumentMetadata(record) };
}

export async function getArchiveStats() {
  const { DB } = requireArchiveBindings();
  const [row, documentCounts] = await Promise.all([DB.prepare(`
    SELECT
      COUNT(*) AS total,
      SUM(CASE WHEN status = 'indexed' THEN 1 ELSE 0 END) AS indexed,
      SUM(CASE WHEN source_kind IN ('official_moj', 'official_bog') THEN 1 ELSE 0 END) AS official
    FROM archive_files
    WHERE source_kind <> 'telegram'
  `).first<{ total: number; indexed: number | null; official: number | null }>(),
  DB.prepare(`
    SELECT
      SUM(CASE WHEN ld.granularity = 'case'
        AND ld.document_type IN ('حكم قضائي', 'صك قضائي', 'سابقة قضائية')
        AND NOT (ld.specialty = 'ملكية فكرية' OR ld.document_type IN ('قرار ملكية فكرية', 'مبدأ قضائي دولي'))
        AND NOT (ld.document_type = 'سابقة قضائية' AND (ld.specialty = 'إداري' OR COALESCE(ld.originating_authority, '') LIKE '%ديوان المظالم%' OR COALESCE(ld.publishing_authority, '') LIKE '%ديوان المظالم%'))
        THEN 1 ELSE 0 END) AS judgments,
      SUM(CASE WHEN ld.granularity = 'case' AND ld.document_type LIKE 'تعميم%' THEN 1 ELSE 0 END) AS circulars,
      SUM(CASE WHEN ld.granularity = 'case' AND ld.document_type LIKE '%قرار%' THEN 1 ELSE 0 END) AS decisions,
      SUM(CASE WHEN ld.granularity = 'case' AND ld.document_type = 'سابقة قضائية' THEN 1 ELSE 0 END) AS precedents,
      SUM(CASE WHEN ld.granularity = 'case' AND ld.document_type = 'مبدأ قضائي' THEN 1 ELSE 0 END) AS principles,
      COUNT(DISTINCT CASE WHEN ld.granularity = 'case' AND (
        ld.document_type IN ('حكم قضائي', 'صك قضائي', 'سابقة قضائية', 'مبدأ قضائي', 'مبدأ قضائي دولي')
        OR ld.document_type LIKE '%قرار%'
        OR ld.document_type LIKE 'تعميم%'
      ) THEN ld.id END) AS contentTotal,
      SUM(CASE WHEN ld.granularity = 'case' AND ld.document_type = 'سابقة قضائية'
        AND (ld.specialty = 'إداري' OR COALESCE(ld.originating_authority, '') LIKE '%ديوان المظالم%' OR COALESCE(ld.publishing_authority, '') LIKE '%ديوان المظالم%')
        THEN 1 ELSE 0 END) AS administrativePrecedents,
      SUM(CASE WHEN ld.granularity = 'case'
        AND (ld.specialty = 'ملكية فكرية' OR COALESCE(ld.subject, '') LIKE '%ملكية فكرية%' OR COALESCE(ld.subject, '') LIKE '%حقوق المؤلف%' OR COALESCE(ld.subject, '') LIKE '%علامة تجارية%')
        AND (ld.document_type IN ('حكم قضائي', 'صك قضائي', 'سابقة قضائية', 'مبدأ قضائي دولي') OR ld.document_type LIKE '%قرار%')
        THEN 1 ELSE 0 END) AS ipPrecedentsOrDecisions,
      SUM(CASE WHEN ld.granularity = 'case'
        AND (ld.document_type = 'مبدأ قضائي' OR ld.document_type LIKE '%قرار%')
        AND NOT (ld.specialty = 'ملكية فكرية' OR ld.document_type IN ('قرار ملكية فكرية', 'مبدأ قضائي دولي') OR COALESCE(ld.subject, '') LIKE '%ملكية فكرية%' OR COALESCE(ld.subject, '') LIKE '%حقوق المؤلف%' OR COALESCE(ld.subject, '') LIKE '%علامة تجارية%')
        THEN 1 ELSE 0 END) AS judicialPrinciplesOrDecisions
    FROM legal_documents AS ld
    LEFT JOIN archive_files AS af ON af.id = ld.archive_file_id
    WHERE af.source_kind IS NULL OR af.source_kind <> 'telegram'
  `).first<{
    judgments: number | null;
    circulars: number | null;
    decisions: number | null;
    precedents: number | null;
    principles: number | null;
    contentTotal: number | null;
    administrativePrecedents: number | null;
    ipPrecedentsOrDecisions: number | null;
    judicialPrinciplesOrDecisions: number | null;
  }>(),
  ]);
  return {
    total: Number(row?.total ?? 0),
    indexed: Number(row?.indexed ?? 0),
    official: Number(row?.official ?? 0),
    judgments: Number(documentCounts?.judgments ?? 0),
    circulars: Number(documentCounts?.circulars ?? 0),
    decisions: Number(documentCounts?.decisions ?? 0),
    precedents: Number(documentCounts?.precedents ?? 0),
    principles: Number(documentCounts?.principles ?? 0),
    contentTotal: Number(documentCounts?.contentTotal ?? 0),
    administrativePrecedents: Number(documentCounts?.administrativePrecedents ?? 0),
    ipPrecedentsOrDecisions: Number(documentCounts?.ipPrecedentsOrDecisions ?? 0),
    judicialPrinciplesOrDecisions: Number(documentCounts?.judicialPrinciplesOrDecisions ?? 0),
  };
}

export async function getArchiveFile(id: string) {
  const { DB } = requireArchiveBindings();
  return DB.prepare(`${ARCHIVE_SELECT} WHERE id = ? LIMIT 1`)
    .bind(id)
    .first<ArchiveRecord>();
}

export async function getCollectorState(key: string) {
  const { DB } = requireArchiveBindings();
  const row = await DB.prepare("SELECT value FROM collector_state WHERE key = ? LIMIT 1")
    .bind(key)
    .first<{ value: string }>();
  return row?.value ?? null;
}

export async function setCollectorState(key: string, value: string) {
  const { DB } = requireArchiveBindings();
  await DB.prepare(`
    INSERT INTO collector_state (key, value, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
  `)
    .bind(key, value)
    .run();
}
