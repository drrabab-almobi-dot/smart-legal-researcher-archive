import { authenticatedEmail, requireArchiveBindings } from "@/lib/archive-storage";
import { normalizeArabic } from "@/lib/arabic-search";

export const dynamic = "force-dynamic";

const PORTAL = "https://portaleservices.moj.gov.sa/TameemPortal/TameemList.aspx";
const SEED_IDS = ["27063", "36618"];

function decodeHtml(value: string) {
  return value
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCodePoint(Number(code)))
    .replace(/\s+/g, " ")
    .trim();
}

function discoverIds(html: string) {
  return Array.from(html.matchAll(/TameemList\.aspx\?id=(\d+)/gi), (match) => match[1]);
}

async function fetchPortal(url: string) {
  const response = await fetch(url, {
    headers: { "user-agent": "Mozilla/5.0 (compatible; LegalArchive/1.0)" },
  });
  if (!response.ok) throw new Error(`تعذر قراءة بوابة التعاميم (${response.status}).`);
  return await response.text();
}

function circularMetadata(text: string, portalId: string) {
  const number = text.match(/رقم\s*(?:التعميم)?\s*[:：]?\s*([0-9٠-٩/-]{3,})/)?.[1] ?? null;
  const date = text.match(/(?:تاريخ|بتاريخ)\s*[:：]?\s*([0-9٠-٩/-]{6,})/)?.[1] ?? null;
  const subject = text.match(/(?:الموضوع|بشأن)\s*[:：]?\s*(.{12,220}?)(?=رقم|تاريخ|$)/)?.[1]?.trim() ?? null;
  return {
    reference: number ? `تعميم رقم ${number}` : `سجل البوابة ${portalId}`,
    title: subject ? `تعميم بشأن ${subject}` : `تعميم عدلي - ${number || portalId}`,
    subject,
    date,
  };
}

export async function POST(request: Request) {
  const uploadedBy = authenticatedEmail(request);
  if (!uploadedBy) return Response.json({ error: "يلزم تسجيل الدخول لتشغيل جامع التعاميم." }, { status: 401 });

  try {
    const discovered = new Set(SEED_IDS);
    for (const id of SEED_IDS) {
      try {
        const html = await fetchPortal(`${PORTAL}?id=${id}`);
        discoverIds(html).forEach((value) => discovered.add(value));
      } catch { /* Preserve the other reachable seeds. */ }
    }

    const { DB } = requireArchiveBindings();
    let indexed = 0;
    let updated = 0;
    const errors: string[] = [];
    for (const id of Array.from(discovered).slice(0, 100)) {
      const sourceUrl = `${PORTAL}?id=${id}`;
      try {
        const text = decodeHtml(await fetchPortal(sourceUrl)).slice(0, 1_500_000);
        if (text.length < 40) throw new Error("صفحة التعميم بلا نص قابل للفهرسة.");
        const metadata = circularMetadata(text, id);
        const recordId = `moj-circular-${id}`;
        const existing = await DB.prepare("SELECT id FROM legal_documents WHERE id = ? LIMIT 1").bind(recordId).first();
        await DB.prepare(`
          INSERT INTO legal_documents (
            id, title, document_type, issuer, publishing_authority,
            originating_authority, reference_no, subject, summary,
            extracted_text, source_kind, source_url, source_label,
            verified, created_at, updated_at
          ) VALUES (?, ?, 'تعميم وزاري', 'وزارة العدل', 'وزارة العدل',
            'وزارة العدل', ?, ?, ?, ?, 'official_moj', ?,
            'بوابة التعاميم العدلية الرسمية', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
          ON CONFLICT(id) DO UPDATE SET
            title = excluded.title,
            reference_no = excluded.reference_no,
            subject = excluded.subject,
            summary = excluded.summary,
            extracted_text = excluded.extracted_text,
            source_url = excluded.source_url,
            verified = 1,
            updated_at = CURRENT_TIMESTAMP
        `).bind(
          recordId,
          metadata.title,
          metadata.reference,
          metadata.subject,
          [metadata.subject, metadata.date ? `التاريخ: ${metadata.date}` : null].filter(Boolean).join(" — ") || "تعميم منشور في البوابة الرسمية لوزارة العدل.",
          normalizeArabic(text),
          sourceUrl,
        ).run();
        if (existing) updated += 1;
        else indexed += 1;
      } catch (error) {
        errors.push(`${id}: ${error instanceof Error ? error.message : "تعذر فهرسة التعميم."}`);
      }
    }

    return Response.json({ summary: { discovered: discovered.size, indexed, updated, errors: errors.length }, errors: errors.slice(0, 8) });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر تشغيل جامع التعاميم." }, { status: 502 });
  }
}
