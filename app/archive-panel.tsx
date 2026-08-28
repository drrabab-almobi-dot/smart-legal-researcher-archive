"use client";

import { useEffect, useRef, useState } from "react";

type ArchiveRecord = {
  id: string;
  fileName: string;
  relativePath: string | null;
  mimeType: string;
  sizeBytes: number;
  sourceKind: "computer" | "telegram" | "official_moj" | "official_bog";
  sourceLabel: string;
  status: "pending_indexing" | "indexed" | "duplicate" | "failed";
  documentType: string;
  issuer: string | null;
  publishingAuthority: string | null;
  originatingAuthority: string | null;
  hijriYear: string | null;
  referenceNo: string | null;
  subject: string | null;
  createdAt: string;
  indexedAt: string | null;
};

type UploadSummary = {
  archived: number;
  duplicates: number;
  rejected: number;
  indexedJudgments?: number;
  rejectedJudgments?: number;
};

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} بايت`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} كيلوبايت`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} ميجابايت`;
}

function statusLabel(status: ArchiveRecord["status"]) {
  if (status === "indexed") return "مفهرس";
  if (status === "duplicate") return "مكرر";
  if (status === "failed") return "تعذر الفهرسة";
  return "محفوظ — بانتظار الفهرسة";
}

export default function ArchivePanel() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [archiveFiles, setArchiveFiles] = useState<ArchiveRecord[]>([]);
  const [archiveStats, setArchiveStats] = useState({ total: 0, indexed: 0, official: 0, judgments: 0, circulars: 0, decisions: 0 });
  const [archiveQuery, setArchiveQuery] = useState("");
  const [uploading, setUploading] = useState(false);
  const [loadingArchive, setLoadingArchive] = useState(true);
  const [notice, setNotice] = useState("");
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null);
  const [syncingOfficial, setSyncingOfficial] = useState(false);

  useEffect(() => {
    folderInputRef.current?.setAttribute("webkitdirectory", "");
    folderInputRef.current?.setAttribute("directory", "");

    void loadArchive();
  }, []);

  async function loadArchive(query = "") {
    setLoadingArchive(true);
    try {
      const response = await fetch(`/api/archive?query=${encodeURIComponent(query)}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        setArchiveFiles([]);
        return;
      }
      const payload = (await response.json()) as { files?: ArchiveRecord[]; stats?: { total: number; indexed: number; official: number; judgments: number; circulars: number; decisions: number } };
      setArchiveFiles(payload.files ?? []);
      if (payload.stats) setArchiveStats(payload.stats);
    } finally {
      setLoadingArchive(false);
    }
  }

  function chooseFiles(files: FileList | null) {
    if (!files) return;
    setSelectedFiles(Array.from(files).slice(0, 50));
    setUploadSummary(null);
    setNotice("");
  }

  async function uploadSelected() {
    if (!selectedFiles.length) return;
    setUploading(true);
    setNotice("");
    setUploadSummary(null);

    try {
      const body = new FormData();
      for (const file of selectedFiles) {
        body.append("files", file, file.name);
        body.append("paths", file.webkitRelativePath || file.name);
      }
      const response = await fetch("/api/archive", { method: "POST", body });
      const payload = (await response.json()) as {
        error?: string;
        summary?: UploadSummary;
      };
      if (!response.ok || !payload.summary) {
        throw new Error(payload.error || "تعذر رفع الملفات.");
      }
      setUploadSummary(payload.summary);
      setNotice(
        payload.summary.archived
          ? payload.summary.indexedJudgments
            ? `تم حفظ الأصول وفهرسة ${payload.summary.indexedJudgments} حكمًا مستقلًا.`
            : "تم حفظ الأصول بنجاح وإرسالها إلى قائمة الفهرسة."
          : "لم تُضف ملفات جديدة؛ راجع التكرارات أو الصيغ غير المدعومة.",
      );
      setSelectedFiles([]);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (folderInputRef.current) folderInputRef.current.value = "";
      await loadArchive();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر رفع الملفات.");
    } finally {
      setUploading(false);
    }
  }

  async function syncOfficial(maxBatches = 12) {
    setSyncingOfficial(true);
    setNotice("");
    try {
      let archived = 0;
      let duplicates = 0;
      let discovered = 0;
      let indexedJudgments = 0;
      let updatedJudgments = 0;
      let complete = false;
      for (let batch = 1; batch <= maxBatches; batch += 1) {
        setNotice(`جارٍ فصل وفهرسة دفعة الأحكام ${batch} من بوابة وزارة العدل...`);
        const response = await fetch("/api/archive/judgments", { method: "POST" });
        const payload = (await response.json()) as { error?: string; summary?: { indexed: number; updated: number; complete: boolean } };
        if (!response.ok || !payload.summary) throw new Error(payload.error || "تعذر فهرسة الأحكام الفردية.");
        indexedJudgments += payload.summary.indexed;
        updatedJudgments += payload.summary.updated;
        await loadArchive();
        if (payload.summary.complete) break;
      }
      for (let batch = 1; batch <= maxBatches && !complete; batch += 1) {
        setNotice(`جارٍ سحب الدفعة الرسمية ${batch} من وزارة العدل وديوان المظالم...`);
        const response = await fetch("/api/archive/official", { method: "POST" });
        const payload = (await response.json()) as { error?: string; summary?: { discovered: number; archived: number; duplicates: number; complete: boolean } };
        if (!response.ok || !payload.summary) throw new Error(payload.error || "تعذر تشغيل الجامع الرسمي.");
        discovered = payload.summary.discovered;
        archived += payload.summary.archived;
        duplicates += payload.summary.duplicates;
        complete = payload.summary.complete;
        await loadArchive();
        if (!discovered) break;
      }
      const circularResponse = await fetch("/api/archive/circulars", { method: "POST" });
      const circularPayload = (await circularResponse.json()) as { summary?: { discovered: number; indexed: number; updated: number }; error?: string };
      if (!circularResponse.ok) throw new Error(circularPayload.error || "تعذر جمع التعاميم الرسمية.");
      await loadArchive();
      setNotice(`تمت الدفعة: ${indexedJudgments} حكمًا جديدًا مفصولًا، ${updatedJudgments} حكمًا محدّثًا، ${archived} ملف مصدر جديد، ${duplicates} مكررًا، و${circularPayload.summary?.indexed ?? 0} تعميم جديد.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "تعذر تشغيل الجامع الرسمي.");
    } finally {
      setSyncingOfficial(false);
    }
  }

  const totalSelectedBytes = selectedFiles.reduce((sum, file) => sum + file.size, 0);
  const totalArchivedBytes = archiveFiles.reduce((sum, file) => sum + file.sizeBytes, 0);

  return (
    <section className="archive-section" id="archive">
      <div className="shell">
        <div className="archive-heading">
          <div>
            <span className="section-kicker">الأرشيف القضائي الخاص</span>
            <h2>اجمع المدونات القضائية في مكان واحد</h2>
          </div>
          <p>
            يحفظ النظام أصل كل ملف، وبصمته الرقمية، ومصدره؛ ثم يكتشف التكرار
            ويجهزه للفهرسة والبحث.
          </p>
        </div>

        <div className="archive-pipeline" aria-label="مسار معالجة الملف">
          <div><span>01</span><strong>حفظ الأصل</strong><small>تخزين خاص وآمن</small></div>
          <i aria-hidden="true">←</i>
          <div><span>02</span><strong>بصمة رقمية</strong><small>منع النسخ المكررة</small></div>
          <i aria-hidden="true">←</i>
          <div><span>03</span><strong>استخراج الوصف</strong><small>الناشر والأصل والنوع</small></div>
          <i aria-hidden="true">←</i>
          <div><span>04</span><strong>قائمة الفهرسة</strong><small>جاهز للمراجعة والبحث</small></div>
        </div>

        <div className="collector-grid">
          <article className="collector-card official-card">
            <div className="collector-card-top">
              <span className="collector-icon">⚖</span>
              <span className="ready-pill"><i /> مصادر رسمية</span>
            </div>
            <small>المصدر الأول والأوثق</small>
            <h3>وزارة العدل وديوان المظالم</h3>
            <p>يسحب الأحكام الفردية من البوابة الرسمية، ويفصل كل قضية كسجل مستقل قابل للبحث، مع حفظ رابط الأصل.</p>
            <ol className="official-steps">
              <li>وزارة العدل — الأحكام الفردية ومجموعات الأحكام</li>
              <li>ديوان المظالم — المدونات القضائية</li>
              <li>منع التكرار بالبصمة الرقمية</li>
            </ol>
            <button className="primary-action" type="button" disabled={syncingOfficial} onClick={() => void syncOfficial(12)}>
              {syncingOfficial ? "جارٍ فصل وفهرسة الأحكام..." : "سحب وفهرسة الأحكام الرسمية الآن"}
            </button>
          </article>

          <article className="collector-card computer-card">
            <div className="collector-card-top">
              <span className="collector-icon">⌁</span>
              <span className="ready-pill"><i /> جاهز للاستخدام</span>
            </div>
            <small>مصدر إضافي</small>
            <h3>ملفات أو مجلد من الكمبيوتر</h3>
            <p>ارفع مجموعة المدونات دفعة واحدة مع الاحتفاظ بأسماء المجلدات ومساراتها.</p>

            <div
              className="drop-zone"
              onDragOver={(event) => event.preventDefault()}
              onDrop={(event) => {
                event.preventDefault();
                chooseFiles(event.dataTransfer.files);
              }}
            >
              <strong>{selectedFiles.length ? `${selectedFiles.length} ملفًا محددًا` : "اسحب الملفات هنا"}</strong>
              <span>
                {selectedFiles.length
                  ? `الحجم الإجمالي ${formatSize(totalSelectedBytes)}`
                  : "PDF وWord والصور والنصوص — حتى 50 ملفًا"}
              </span>
              <div className="picker-actions">
                <button type="button" onClick={() => fileInputRef.current?.click()}>اختيار ملفات</button>
                <button type="button" className="secondary-picker" onClick={() => folderInputRef.current?.click()}>اختيار مجلد</button>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                hidden
                multiple
                accept=".pdf,.doc,.docx,.txt,.rtf,.odt,.xls,.xlsx,.csv,.html,.htm,.md,.json,.json.gz,.xml,.jpg,.jpeg,.png,.tif,.tiff"
                onChange={(event) => chooseFiles(event.target.files)}
              />
              <input
                ref={folderInputRef}
                type="file"
                hidden
                multiple
                onChange={(event) => chooseFiles(event.target.files)}
              />
            </div>

            {selectedFiles.length > 0 && (
              <div className="selected-preview">
                {selectedFiles.slice(0, 3).map((file) => (
                  <span key={`${file.name}-${file.size}`}>{file.name}</span>
                ))}
                {selectedFiles.length > 3 && <span>+ {selectedFiles.length - 3} ملفات أخرى</span>}
              </div>
            )}

            <button
              className="primary-action"
              type="button"
              disabled={!selectedFiles.length || uploading}
              onClick={uploadSelected}
            >
              {uploading ? "جارٍ حفظ الأصول..." : "حفظ في الأرشيف"}
            </button>
          </article>

        </div>

        {(notice || uploadSummary) && (
          <div className="archive-notice" role="status">
            <strong>{notice}</strong>
            {uploadSummary && (
              <span>
                جديد: {uploadSummary.archived} · مكرر: {uploadSummary.duplicates} · أحكام مفهرسة: {uploadSummary.indexedJudgments ?? 0} · مستبعد: {uploadSummary.rejected + (uploadSummary.rejectedJudgments ?? 0)}
              </span>
            )}
          </div>
        )}

        <div className="archive-register">
          <div className="register-toolbar">
            <div>
              <span className="section-kicker">سجل الأرشيف</span>
              <h3>{archiveStats.total} ملفًا محفوظًا · {archiveStats.indexed} مفهرسًا · {archiveStats.official} رسميًا</h3>
            </div>
            <form
              className="archive-search"
              onSubmit={(event) => {
                event.preventDefault();
                void loadArchive(archiveQuery);
              }}
            >
              <label className="sr-only" htmlFor="archive-query">بحث في الأرشيف</label>
              <input
                id="archive-query"
                value={archiveQuery}
                onChange={(event) => setArchiveQuery(event.target.value)}
                placeholder="اسم الملف، السنة، أو الجهة..."
              />
              <button type="submit">بحث</button>
            </form>
          </div>

          {loadingArchive ? (
            <div className="register-empty">جارٍ قراءة سجل الأرشيف...</div>
          ) : archiveFiles.length ? (
            <div className="archive-table-wrap">
              <table className="archive-table">
                <thead>
                  <tr>
                    <th>الملف</th>
                    <th>المصدر</th>
                    <th>التصنيف الأولي</th>
                    <th>الناشر والأصل</th>
                    <th>الحالة</th>
                    <th>الأصل</th>
                  </tr>
                </thead>
                <tbody>
                  {archiveFiles.map((file) => (
                    <tr key={file.id}>
                      <td><strong>{file.fileName}</strong><small>{formatSize(file.sizeBytes)}</small></td>
                      <td>{file.sourceKind === "official_moj" || file.sourceKind === "official_bog" ? "مصدر قضائي رسمي" : "ملف محفوظ"}</td>
                      <td><span>{file.documentType}</span>{file.hijriYear && <small>{file.hijriYear}هـ</small>}</td>
                      <td>
                        <span>{file.publishingAuthority ?? file.issuer ?? "غير محدد"}</span>
                        <small>الأصل: {file.originatingAuthority ?? "يحتاج مراجعة"}</small>
                      </td>
                      <td><span className={`archive-status ${file.status}`}>{statusLabel(file.status)}</span></td>
                      <td><a href={`/api/archive/file/${file.id}`}>تنزيل ↙</a></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="register-empty">
              <strong>لم تُضف ملفات بعد</strong>
              <span>اختر ملفات المدونات أو مجلدها، وسيظهر سجل الحفظ هنا.</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
