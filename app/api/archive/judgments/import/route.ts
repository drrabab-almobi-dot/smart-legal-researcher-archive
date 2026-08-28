import { authenticatedEmail, getArchiveBindings } from "@/lib/archive-storage";
import { importJudgmentBatch } from "@/lib/judgment-import";

export const dynamic = "force-dynamic";

async function authorized(request: Request) {
  if (authenticatedEmail(request)) return true;
  const expected = getArchiveBindings().ARCHIVE_IMPORT_TOKEN?.trim();
  const supplied = request.headers.get("x-archive-import-token")?.trim();
  if (!expected || !supplied) return false;
  const encoder = new TextEncoder();
  const [expectedHash, suppliedHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
    crypto.subtle.digest("SHA-256", encoder.encode(supplied)),
  ]);
  const left = new Uint8Array(expectedHash);
  const right = new Uint8Array(suppliedHash);
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

export async function POST(request: Request) {
  if (!(await authorized(request))) return Response.json({ error: "غير مصرح بالاستيراد." }, { status: 401 });
  try {
    const body = request.headers.get("content-encoding")?.toLowerCase() === "gzip"
      ? await new Response(request.body?.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()
      : await request.arrayBuffer();
    if (!body.byteLength || body.byteLength > 15 * 1024 * 1024) {
      return Response.json({ error: "حجم الدفعة غير صالح." }, { status: 413 });
    }
    const parsed = JSON.parse(new TextDecoder().decode(body));
    const summary = await importJudgmentBatch(parsed);
    return Response.json({ summary });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر استيراد دفعة الأحكام." }, { status: 400 });
  }
}
