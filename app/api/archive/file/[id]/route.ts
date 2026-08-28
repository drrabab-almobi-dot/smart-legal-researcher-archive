import {
  authenticatedEmail,
  getArchiveBindings,
  getArchiveFile,
} from "@/lib/archive-storage";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  if (!authenticatedEmail(request)) {
    return Response.json({ error: "يلزم تسجيل الدخول لتنزيل الملف." }, { status: 401 });
  }

  const { id } = await context.params;
  const record = await getArchiveFile(id);
  const bucket = getArchiveBindings().BUCKET;
  if (!record || !bucket) {
    return Response.json({ error: "الملف غير موجود." }, { status: 404 });
  }

  const object = await bucket.get(record.objectKey);
  if (!object) {
    return Response.json({ error: "تعذر العثور على أصل الملف في التخزين." }, { status: 404 });
  }

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("Content-Type", record.mimeType || "application/octet-stream");
  headers.set("Content-Length", String(record.sizeBytes));
  headers.set(
    "Content-Disposition",
    `attachment; filename*=UTF-8''${encodeURIComponent(record.fileName)}`,
  );
  headers.set("Cache-Control", "private, no-store");
  return new Response(object.body, { headers });
}
