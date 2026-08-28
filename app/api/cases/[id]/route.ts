import { PDFDocument } from "pdf-lib";
import caseIndex from "@/app/case-index.generated.json";
import specializedCaseIndex from "@/app/specialized-case-index.generated.json";
import snippetIndex from "@/app/snippet-index.generated.json";

type ArchiveRecord = {
  id: string;
  title?: string;
  sourceFile: string;
  startPage: number;
  endPage: number;
  startY?: number;
  endY?: number;
  excludedPages?: number[];
  reference?: string;
  documentType?: string;
};

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;
  const ministryRecord = caseIndex.find((item) => item.id === id);
  const specializedRecord = (specializedCaseIndex as ArchiveRecord[]).find((item) => item.id === id);
  const snippetRecord = (snippetIndex as ArchiveRecord[]).find((item) => item.id === id);
  const archiveRecord = specializedRecord ?? snippetRecord;
  const sourceFile = ministryRecord?.archive?.originalSourceFile ?? archiveRecord?.sourceFile;
  const startPage = ministryRecord?.archive?.originalStartPage ?? archiveRecord?.startPage;
  const endPage = ministryRecord?.archive?.originalEndPage ?? archiveRecord?.endPage;
  if (!sourceFile || !startPage || !endPage) {
    return Response.json({ error: "الحكم غير موجود في الأرشيف." }, { status: 404 });
  }

  const sourceUrl = new URL(`/library/${sourceFile}`, request.url);
  const sourceResponse = await fetch(sourceUrl);
  if (!sourceResponse.ok) {
    return Response.json({ error: "تعذر تحميل المدونة الأصلية." }, { status: 502 });
  }

  const sourcePdf = await PDFDocument.load(await sourceResponse.arrayBuffer(), { ignoreEncryption: true });
  const outputPdf = await PDFDocument.create();
  const first = Math.max(0, startPage - 1);
  const last = Math.min(sourcePdf.getPageCount() - 1, endPage - 1);
  const excludedPages = new Set(archiveRecord?.excludedPages ?? []);
  const pageIndices = Array.from({ length: last - first + 1 }, (_, index) => first + index)
    .filter((pageIndex) => !excludedPages.has(pageIndex + 1));
  const pages = await outputPdf.copyPages(sourcePdf, pageIndices);
  pages.forEach((page, index) => {
    if (snippetRecord) {
      const height = page.getHeight();
      const width = page.getWidth();
      const isFirst = index === 0;
      const isLast = index === pages.length - 1;
      const top = isFirst ? Math.max(0, snippetRecord.startY ?? 0) : 65;
      const bottom = isLast
        ? Math.min(height, snippetRecord.endY ?? height - 35)
        : Math.min(height, 620);
      if (bottom > top) page.setCropBox(0, height - bottom, width, bottom - top);
    }
    outputPdf.addPage(page);
  });
  const reference = ministryRecord?.deedNumber || ministryRecord?.lawsuitNumber || archiveRecord?.reference || id;
  outputPdf.setTitle(archiveRecord?.title || `حكم ${reference}`);
  outputPdf.setSubject(archiveRecord?.documentType || "حكم مستقل من مجموعة الأحكام القضائية - وزارة العدل");

  const bytes = await outputPdf.save({ useObjectStreams: true });
  const safeReference = String(reference).replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || id;
  const filename = `legal-document-${safeReference}.pdf`;
  return new Response(bytes as BodyInit, {
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `inline; filename="${filename}"`,
      "Cache-Control": "public, max-age=86400",
    },
  });
}
