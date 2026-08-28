import {
  archiveBytes,
  authenticatedEmail,
  getCollectorState,
  setCollectorState,
} from "@/lib/archive-storage";

export const dynamic = "force-dynamic";

const STATE_KEY = "official_judgments_cursor_v1";
const MAX_FILES_PER_RUN = 10;
const MAX_FILE_BYTES = 30 * 1024 * 1024;

type Source = {
  kind: "official_moj" | "official_bog";
  authority: string;
  pages: string[];
};

const SOURCES: Source[] = [
  {
    kind: "official_bog",
    authority: "ديوان المظالم",
    pages: Array.from({ length: 12 }, (_, index) =>
      `https://www.bog.gov.sa/knowledge-center/JudicialBlogs/Pages/JudgmentsDefault.aspx?PageIndex=${index + 1}`,
    ),
  },
  {
    kind: "official_moj",
    authority: "وزارة العدل",
    pages: [
      "https://www.moj.gov.sa/ar-sa/ministry/versions/Pages/default.aspx",
      "https://moj.gov.sa/ar-sa/ministry/versions/Pages/default.aspx",
    ],
  },
];

function decode(value: string) {
  return value.replace(/&amp;/gi, "&").replace(/&#x2f;|&#47;/gi, "/").replace(/&quot;|&#34;/gi, '"');
}

function allowedOfficialUrl(value: string) {
  try {
    const url = new URL(value);
    return /(^|\.)bog\.gov\.sa$/i.test(url.hostname) || /(^|\.)moj\.gov\.sa$/i.test(url.hostname);
  } catch {
    return false;
  }
}

function pdfLinks(html: string, pageUrl: string) {
  const links: string[] = [];
  for (const match of html.matchAll(/(?:href|src)\s*=\s*["']([^"']+\.pdf(?:\?[^"']*)?)["']/gi)) {
    try {
      const absolute = new URL(decode(match[1]), pageUrl).toString();
      if (allowedOfficialUrl(absolute)) links.push(absolute);
    } catch { /* Ignore malformed links. */ }
  }
  for (const match of html.matchAll(/https?:\/\/[^\s<>"')\]]+\.pdf(?:\?[^\s<>"')\]]*)?/gi)) {
    const absolute = decode(match[0]);
    if (allowedOfficialUrl(absolute)) links.push(absolute);
  }
  return Array.from(new Set(links));
}

async function readListing(url: string) {
  try {
    const response = await fetch(url, { headers: { "user-agent": "Mozilla/5.0 (compatible; LegalArchive/1.0)" } });
    if (response.ok) return await response.text();
  } catch { /* Try the public text reader for link discovery. */ }
  const reader = await fetch(`https://r.jina.ai/http://${url.replace(/^https?:\/\//, "")}`, {
    headers: { accept: "text/plain" },
  });
  if (!reader.ok) return "";
  return await reader.text();
}

async function discover() {
  const found: Array<{ url: string; source: Source }> = [];
  for (const source of SOURCES) {
    for (const page of source.pages) {
      const html = await readListing(page);
      for (const url of pdfLinks(html, page)) found.push({ url, source });
    }
  }
  return Array.from(new Map(found.map((item) => [item.url, item])).values());
}

function fileNameFromUrl(value: string, authority: string, index: number) {
  const raw = decodeURIComponent(new URL(value).pathname.split("/").pop() || "").trim();
  return raw && raw.toLowerCase().endsWith(".pdf")
    ? `${authority}-${raw}`
    : `${authority}-مجموعة-أحكام-${index + 1}.pdf`;
}

export async function GET(request: Request) {
  if (!authenticatedEmail(request)) return Response.json({ error: "يلزم تسجيل الدخول." }, { status: 401 });
  const cursor = Number(await getCollectorState(STATE_KEY).catch(() => "0"));
  return Response.json({ configured: true, cursor: Number.isFinite(cursor) ? cursor : 0, sources: SOURCES.map((s) => s.authority) });
}

export async function POST(request: Request) {
  const uploadedBy = authenticatedEmail(request);
  if (!uploadedBy) return Response.json({ error: "يلزم تسجيل الدخول لتشغيل الجامع الرسمي." }, { status: 401 });

  try {
    const documents = await discover();
    const saved = Number(await getCollectorState(STATE_KEY));
    const cursor = Number.isFinite(saved) && saved >= 0 ? saved : 0;
    const batch = documents.slice(cursor, cursor + MAX_FILES_PER_RUN);
    let archived = 0;
    let duplicates = 0;
    let rejected = 0;
    const errors: string[] = [];

    for (const [index, item] of batch.entries()) {
      try {
        const response = await fetch(item.url, { headers: { "user-agent": "Mozilla/5.0 (compatible; LegalArchive/1.0)" } });
        if (!response.ok) throw new Error(`تعذر تنزيل الملف (${response.status}).`);
        const contentType = response.headers.get("content-type") || "application/pdf";
        const length = Number(response.headers.get("content-length") || 0);
        if (length > MAX_FILE_BYTES) { rejected += 1; continue; }
        const bytes = await response.arrayBuffer();
        if (!bytes.byteLength || bytes.byteLength > MAX_FILE_BYTES) { rejected += 1; continue; }
        const fileName = fileNameFromUrl(item.url, item.source.authority, cursor + index);
        const result = await archiveBytes({
          bytes,
          fileName,
          relativePath: item.url,
          mimeType: contentType.includes("pdf") ? contentType : "application/pdf",
          sourceKind: item.source.kind,
          sourceLabel: `مصدر رسمي موثّق: ${item.source.authority}`,
          uploadedBy,
        });
        if (result.duplicate) duplicates += 1;
        else archived += 1;
      } catch (error) {
        errors.push(error instanceof Error ? error.message : "فشل حفظ ملف رسمي.");
      }
    }

    const nextCursor = cursor + batch.length;
    await setCollectorState(STATE_KEY, String(nextCursor >= documents.length ? 0 : nextCursor));
    return Response.json({
      summary: {
        discovered: documents.length,
        archived,
        duplicates,
        rejected,
        errors: errors.length,
        processed: batch.length,
        complete: documents.length === 0 || nextCursor >= documents.length,
      },
      errors: errors.slice(0, 5),
    });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر تشغيل الجامع الرسمي." }, { status: 502 });
  }
}
