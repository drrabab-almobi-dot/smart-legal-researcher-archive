import { authenticatedEmail, getLegalDocument } from "@/lib/archive-storage";

export const dynamic = "force-dynamic";

function escapeHtml(value: string | null | undefined) {
  return (value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export async function GET(request: Request, context: { params: Promise<{ id: string }> }) {
  if (!authenticatedEmail(request)) {
    return Response.json({ error: "يلزم تسجيل الدخول لعرض المستند." }, { status: 401 });
  }
  const { id } = await context.params;
  const document = await getLegalDocument(id);
  if (!document) return Response.json({ error: "المستند غير موجود." }, { status: 404 });

  const url = new URL(request.url);
  const download = url.searchParams.get("download") === "1";
  const safeName = (document.judgmentNumber || document.caseNumber || document.id)
    .replace(/[^A-Za-z0-9٠-٩_-]+/g, "-")
    .replace(/^-+|-+$/g, "") || "legal-document";
  const rows = [
    ["نوع المستند", document.documentType],
    ["رقم القضية", document.caseNumber || "غير مدون في المصدر"],
    ["رقم الحكم/الصك", document.judgmentNumber || "غير مدون في المصدر"],
    ["المحكمة", document.court || "غير مدونة في المصدر"],
    ["الدائرة", document.circuit || "غير مدونة في المصدر"],
    ["السنة", document.hijriYear ? `${document.hijriYear}هـ` : "غير مدونة في المصدر"],
    ["الاختصاص", document.specialty],
  ];
  const html = `<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(document.title)}</title><style>body{font-family:Tahoma,Arial,sans-serif;background:#fbf8f3;color:#29202f;margin:0;line-height:1.9}.page{max-width:940px;margin:32px auto;background:white;border:1px solid #eaddec;border-radius:18px;padding:36px;box-sizing:border-box}h1{color:#512169;margin:0 0 10px;font-size:30px}.badge{color:#08756b;font-weight:700}.meta{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:24px 0}.meta div{background:#f8f2fa;border-radius:10px;padding:10px 14px}.meta b{display:block;color:#6a3b77;font-size:13px}.text{white-space:pre-wrap;border-top:1px solid #eee;padding-top:24px}.actions{display:flex;gap:12px;flex-wrap:wrap;margin-top:28px}.actions a{padding:10px 16px;border-radius:9px;text-decoration:none;font-weight:700;background:#512169;color:#fff}.actions a.secondary{background:#fff;color:#512169;border:1px solid #512169}@media(max-width:650px){.page{margin:0;border-radius:0;padding:22px}.meta{grid-template-columns:1fr}}@media print{body{background:#fff}.page{border:0;margin:0;max-width:none}.actions{display:none}}</style></head><body><main class="page"><span class="badge">✓ مستند قانوني مستقل</span><h1>${escapeHtml(document.title)}</h1><p>${escapeHtml(document.summary)}</p><section class="meta">${rows.map(([label,value]) => `<div><b>${escapeHtml(label)}</b>${escapeHtml(value)}</div>`).join("")}</section><article class="text">${escapeHtml(document.extractedText)}</article><footer class="actions"><a href="/api/documents/${encodeURIComponent(document.id)}?download=1">تنزيل المستند المستقل</a>${document.sourceUrl ? `<a class="secondary" href="${escapeHtml(document.sourceUrl)}" target="_blank" rel="noreferrer">فتح المصدر الرسمي</a>` : ""}<a class="secondary" href="javascript:window.print()">طباعة / حفظ PDF</a></footer></main></body></html>`;
  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Disposition": `${download ? "attachment" : "inline"}; filename="legal-document-${safeName}.html"`,
      "Cache-Control": "private, no-store",
    },
  });
}
