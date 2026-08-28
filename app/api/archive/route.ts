import {
  archiveBytes,
  authenticatedEmail,
  isAcceptedFile,
  listArchiveFiles,
  listLegalDocuments,
  getArchiveStats,
  type ArchiveRecord,
} from "@/lib/archive-storage";
import { importJudgmentBatch } from "@/lib/judgment-import";

export const dynamic = "force-dynamic";

const MAX_FILES = 50;
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const MAX_REQUEST_BYTES = 100 * 1024 * 1024;

function publicRecord(record: ArchiveRecord) {
  return {
    id: record.id,
    fileName: record.fileName,
    relativePath: record.relativePath,
    mimeType: record.mimeType,
    sizeBytes: record.sizeBytes,
    sourceKind: record.sourceKind,
    sourceLabel: record.sourceLabel,
    status: record.status,
    documentType: record.documentType,
    issuer: record.issuer,
    publishingAuthority: record.publishingAuthority,
    originatingAuthority: record.originatingAuthority,
    hijriYear: record.hijriYear,
    referenceNo: record.referenceNo,
    subject: record.subject,
    createdAt: record.createdAt,
    indexedAt: record.indexedAt,
    relevance: record.relevance,
    matchContext: record.matchContext,
    matchedTerms: record.matchedTerms,
  };
}

function errorMessage(error: unknown) {
  const message = error instanceof Error ? error.message : "حدث خطأ غير متوقع.";
  if (message.includes("no such table")) {
    return "قاعدة بيانات الأرشيف قيد التهيئة. أعد المحاولة بعد قليل.";
  }
  return message;
}

export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const query = url.searchParams.get("query") ?? "";
    const viewerEmail = authenticatedEmail(request);

    // Aggregate counts are already displayed on the landing page and contain no
    // document content. Keep every record and raw archive field authenticated,
    // while allowing only the counter to load when identity is not forwarded on
    // a client-side request.
    if (!viewerEmail) {
      if (query.trim()) {
        return Response.json({ error: "يلزم تسجيل الدخول للوصول إلى الأرشيف." }, { status: 401 });
      }
      const stats = await getArchiveStats();
      return Response.json({ files: [], documents: [], stats });
    }

    const [records, documents, stats] = await Promise.all([
      listArchiveFiles(query, 40),
      listLegalDocuments(query, 40),
      getArchiveStats(),
    ]);
    return Response.json({ files: records.map(publicRecord), documents, stats });
  } catch (error) {
    return Response.json({ error: errorMessage(error) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  const uploadedBy = authenticatedEmail(request);
  if (!uploadedBy) {
    return Response.json({ error: "يلزم تسجيل الدخول لإضافة ملفات إلى الأرشيف." }, { status: 401 });
  }

  try {
    const formData = await request.formData();
    const files = formData
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File && entry.size > 0);
    const paths = formData.getAll("paths").map((entry) => String(entry));

    if (!files.length) {
      return Response.json({ error: "اختر ملفًا واحدًا على الأقل." }, { status: 400 });
    }
    if (files.length > MAX_FILES) {
      return Response.json({ error: `الحد الأعلى ${MAX_FILES} ملفًا في الدفعة الواحدة.` }, { status: 400 });
    }

    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    if (totalBytes > MAX_REQUEST_BYTES) {
      return Response.json({ error: "حجم الدفعة يتجاوز 100 ميجابايت." }, { status: 413 });
    }

    const archived: ReturnType<typeof publicRecord>[] = [];
    const duplicates: ReturnType<typeof publicRecord>[] = [];
    const rejected: { fileName: string; reason: string }[] = [];
    let indexedJudgments = 0;
    let rejectedJudgments = 0;

    for (const [index, file] of files.entries()) {
      if (!isAcceptedFile(file.name)) {
        rejected.push({ fileName: file.name, reason: "صيغة الملف غير مدعومة." });
        continue;
      }
      if (file.size > MAX_FILE_BYTES) {
        rejected.push({ fileName: file.name, reason: "حجم الملف يتجاوز 50 ميجابايت." });
        continue;
      }

      try {
        const bytes = await file.arrayBuffer();
        const result = await archiveBytes({
          bytes,
          fileName: file.name,
          relativePath: paths[index] || file.name,
          mimeType: file.type,
          sourceKind: "computer",
          sourceLabel: paths[index] ? `مجلد الكمبيوتر: ${paths[index]}` : "رفع مباشر من الكمبيوتر",
          uploadedBy,
        });
        (result.duplicate ? duplicates : archived).push(publicRecord(result.record));
        if (/^moj-judgment-batch-.*\.json(?:\.gz)?$/i.test(file.name)) {
          const decodedBytes = file.name.toLowerCase().endsWith(".gz")
            ? await new Response(
                new Response(bytes).body?.pipeThrough(new DecompressionStream("gzip")),
              ).arrayBuffer()
            : bytes;
          const parsed = JSON.parse(new TextDecoder().decode(decodedBytes));
          const imported = await importJudgmentBatch(parsed);
          indexedJudgments += imported.processed;
          rejectedJudgments += imported.rejected;
        }
      } catch (error) {
        rejected.push({ fileName: file.name, reason: errorMessage(error) });
      }
    }

    return Response.json(
      {
        archived,
        duplicates,
        rejected,
        summary: {
          archived: archived.length,
          duplicates: duplicates.length,
          rejected: rejected.length,
          indexedJudgments,
          rejectedJudgments,
        },
      },
      { status: archived.length ? 201 : 200 },
    );
  } catch (error) {
    return Response.json({ error: errorMessage(error) }, { status: 500 });
  }
}
