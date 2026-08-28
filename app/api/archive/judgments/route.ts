import {
  authenticatedEmail,
  getCollectorState,
  requireArchiveBindings,
  setCollectorState,
} from "@/lib/archive-storage";
import { normalizeArabic } from "@/lib/arabic-search";

export const dynamic = "force-dynamic";

const BASE = "https://laws-gateway.moj.gov.sa/apis/legislations/v1";
const STATE_KEY = "moj_individual_judgments_cursor_v1";
const PAGE_SIZE = 50;

type CatalogItem = {
  id: string;
  courtType: number;
  judgementNumber?: string | null;
  judgementDate?: string | null;
  courtName?: string | null;
  city?: string | null;
};

type JudgmentDetail = Record<string, unknown> & {
  id?: string;
  title?: string;
  hjriiYear?: number | string;
  judgmentNumber?: string;
  judgmentHijriiDate?: string;
  judgmentFacts?: string;
  judgmentReasons?: string;
  judgmentRuling?: string;
  judgmentTextofRulling?: string;
  judgmentCourtName?: string;
  judgmentCityName?: string;
  appealNumber?: string;
  appealFacts?: string;
  appealReasons?: string;
  appealRuling?: string;
  appealTextofRulling?: string;
  appealCourtName?: string;
};

function plainText(value: unknown) {
  return String(value ?? "")
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCodePoint(Number(code)))
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function inferSpecialty(value: string) {
  const text = normalizeArabic(value);
  if (/علامه تجاريه|ملكيه فكريه|براءه|مصنف/.test(text)) return "ملكية فكرية";
  if (/قتل|مخدر|سرقه|حد|قصاص|سجن|جزائي|جنائي/.test(text)) return "جزائي";
  if (/زواج|طلاق|نفقه|حضانه|ارث|تركة|وصيه|احوال شخصيه/.test(text)) return "أحوال شخصية";
  if (/عامل|عمالي|اجور|فصل|عقد عمل/.test(text)) return "عمالي";
  if (/عقار|ارض|استحكام|ملكيه|ايجار/.test(text)) return "عقاري";
  if (/اداري|ديوان المظالم|قرار اداري|جهه حكوميه/.test(text)) return "إداري";
  if (/شركه|تجاري|بيع|توريد|افلاس|تحكيم|اوراق تجاريه|مقاول/.test(text)) return "تجاري";
  return "أخرى";
}

async function jsonFetch(url: string, init?: RequestInit) {
  const response = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      languageCode: "ar",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(`تعذر الاتصال ببوابة الأحكام (${response.status}).`);
  const payload = await response.json() as { success?: boolean; model?: unknown; message?: string };
  if (payload.success === false) throw new Error(payload.message || "رفضت البوابة طلب الأحكام.");
  return payload.model;
}

async function catalogPage(courtType: number, pageNumber: number) {
  return await jsonFetch(`${BASE}/Judgements/judgements-list`, {
    method: "POST",
    body: JSON.stringify({ courtTypes: courtType, pageNumber, pageSize: PAGE_SIZE, identityNumber: "", sortingBy: 2 }),
  }) as { judgementsCollection?: CatalogItem[]; totalCount?: number };
}

async function detail(id: string) {
  return await jsonFetch(`${BASE}/Judgements/get-details?id=${encodeURIComponent(id)}&lang=ar&IdentityNumber=`) as JudgmentDetail;
}

function cursorValue(raw: string | null) {
  try {
    const parsed = JSON.parse(raw || "") as { courtType?: number; pageNumber?: number };
    if ([1, 2, 3].includes(parsed.courtType ?? 0) && (parsed.pageNumber ?? 0) > 0) return parsed as { courtType: number; pageNumber: number };
  } catch { /* Start from the first official collection. */ }
  return { courtType: 1, pageNumber: 1 };
}

export async function GET(request: Request) {
  if (!authenticatedEmail(request)) return Response.json({ error: "يلزم تسجيل الدخول." }, { status: 401 });
  const cursor = cursorValue(await getCollectorState(STATE_KEY));
  return Response.json({ cursor, pageSize: PAGE_SIZE });
}

export async function POST(request: Request) {
  if (!authenticatedEmail(request)) return Response.json({ error: "يلزم تسجيل الدخول لتشغيل جامع الأحكام." }, { status: 401 });
  try {
    const cursor = cursorValue(await getCollectorState(STATE_KEY));
    const catalog = await catalogPage(cursor.courtType, cursor.pageNumber);
    const items = catalog.judgementsCollection ?? [];
    const details = await Promise.all(items.map(async (item) => {
      try { return { item, model: await detail(item.id), error: null }; }
      catch (error) { return { item, model: null, error: error instanceof Error ? error.message : "تعذر جلب الحكم." }; }
    }));
    const { DB } = requireArchiveBindings();
    let indexed = 0;
    let updated = 0;
    const errors: string[] = [];

    for (const entry of details) {
      if (!entry.model) { errors.push(`${entry.item.id}: ${entry.error}`); continue; }
      const model = entry.model;
      const text = plainText([
        model.judgmentFacts, model.judgmentReasons, model.judgmentRuling, model.judgmentTextofRulling,
        model.appealFacts, model.appealReasons, model.appealRuling, model.appealTextofRulling,
      ].filter(Boolean).join("\n\n"));
      if (text.length < 40) { errors.push(`${entry.item.id}: الحكم بلا نص قابل للفهرسة.`); continue; }
      const officialId = String(model.id || entry.item.id);
      const recordId = `moj-judgment-${officialId}`;
      const judgmentNumber = String(model.judgmentNumber || entry.item.judgementNumber || officialId);
      const title = plainText(model.title) || `الحكم رقم ${judgmentNumber}`;
      const courtName = plainText(model.judgmentCourtName || entry.item.courtName || model.appealCourtName) || "محاكم وزارة العدل";
      const city = plainText(model.judgmentCityName || entry.item.city) || null;
      const specialty = inferSpecialty(`${title} ${courtName} ${text.slice(0, 12000)}`);
      const sourceUrl = `https://laws.moj.gov.sa/ar/JudicialDecisionsList/${entry.item.courtType}/${entry.item.id}`;
      const existing = await DB.prepare("SELECT id FROM legal_documents WHERE id = ? LIMIT 1").bind(recordId).first();
      await DB.prepare(`
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
        recordId, title, courtName, courtName, String(model.hjriiYear || "") || null,
        judgmentNumber, [courtName, city, specialty].filter(Boolean).join(" — "),
        `حكم مستقل صادر من ${courtName}${city ? ` في ${city}` : ""}.`, normalizeArabic(text), sourceUrl, specialty,
      ).run();
      if (existing) updated += 1; else indexed += 1;
    }

    const totalCount = Number(catalog.totalCount ?? 0);
    const lastPage = !items.length || cursor.pageNumber * PAGE_SIZE >= totalCount;
    const complete = lastPage && cursor.courtType === 3;
    const next = complete
      ? { courtType: 1, pageNumber: 1 }
      : lastPage ? { courtType: cursor.courtType + 1, pageNumber: 1 }
      : { courtType: cursor.courtType, pageNumber: cursor.pageNumber + 1 };
    await setCollectorState(STATE_KEY, JSON.stringify(next));
    return Response.json({
      summary: { courtType: cursor.courtType, pageNumber: cursor.pageNumber, totalCount, received: items.length, indexed, updated, errors: errors.length, complete },
      errors: errors.slice(0, 8),
    });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر تشغيل جامع الأحكام الفردية." }, { status: 502 });
  }
}
