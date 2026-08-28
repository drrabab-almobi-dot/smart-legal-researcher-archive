import { authenticatedEmail, getArchiveBindings } from "@/lib/archive-storage";
import { importNafaBatch } from "@/lib/nafa-import";

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
  if (!(await authorized(request))) return Response.json({ error: "غير مصرح باستيراد نفع." }, { status: 401 });
  try {
    const body = request.headers.get("content-encoding")?.toLowerCase() === "gzip"
      ? await new Response(request.body?.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()
      : await request.arrayBuffer();
    if (!body.byteLength || body.byteLength > 15 * 1024 * 1024) {
      return Response.json({ error: "حجم دفعة نفع غير صالح." }, { status: 413 });
    }
    const parsed = JSON.parse(new TextDecoder().decode(body));
    return Response.json({ summary: await importNafaBatch(parsed) });
  } catch (error) {
    return Response.json({ error: error instanceof Error ? error.message : "تعذر استيراد دفعة نفع." }, { status: 400 });
  }
}
