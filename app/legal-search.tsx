"use client";

import { useEffect, useMemo, useState } from "react";
import {
  legalDocuments,
  sourceRegistry,
  type LegalDocument,
} from "./legal-data";
import ArchivePanel from "./archive-panel";
import { legalSearchTerms, normalizeArabic, relevanceScore, shouldShowSearchResults } from "@/lib/arabic-search";

const quickSearches = ["التعويضات", "الاستحكام", "أحكام تجارية", "مبادئ إدارية"];
const specialties = ["تجاري", "جزائي", "إداري", "عقاري", "أحوال شخصية", "عمالي", "ملكية فكرية", "إجراءات"];

function inferSpecialty(value: string) {
  const text = normalizeArabic(value);
  if (/علامه تجاريه|ملكيه فكريه|براءه|مصنف/.test(text)) return "ملكية فكرية";
  if (/قتل|مخدر|سرقه|حد|قصاص|سجن|جزائي|جنائي/.test(text)) return "جزائي";
  if (/زواج|طلاق|نفقه|حضانه|ارث|تركة|وصيه|احوال شخصيه/.test(text)) return "أحوال شخصية";
  if (/عامل|عمالي|اجور|فصل|عقد عمل/.test(text)) return "عمالي";
  if (/عقار|ارض|استحكام|ملكيه|ايجار|مقاول/.test(text)) return "عقاري";
  if (/اداري|ديوان المظالم|قرار اداري|جهة حكوميه/.test(text)) return "إداري";
  if (/شركه|تجاري|بيع|توريد|افلاس|تحكيم|اوراق تجاريه/.test(text)) return "تجاري";
  return "إجراءات";
}

const searchCorpus = legalDocuments.map((item) => {
  const title = normalizeArabic(item.title);
  const reference = normalizeArabic(item.reference);
  const subject = normalizeArabic(item.subject);
  const keywords = normalizeArabic(item.keywords.join(" "));
  const summary = normalizeArabic(item.summary);
  const fullText = normalizeArabic(
    `${item.type} ${item.publishingAuthority} ${item.originatingAuthority} ${item.hijriYear} ${item.searchText ?? ""}`,
  );
  const combined = `${title} ${subject} ${keywords} ${summary} ${fullText}`;
  return { item, title, reference, subject, keywords, summary, fullText, combined, specialty: inferSpecialty(combined) };
});

function scoreIndexedDocument(entry: (typeof searchCorpus)[number], query: string) {
  return relevanceScore({
    title: entry.item.title,
    reference: entry.item.reference,
    subject: entry.item.subject,
    keywords: entry.item.keywords,
    summary: entry.item.summary,
    fullText: entry.item.searchText,
  }, query);
}

type ArchivedSearchRecord = {
  id: string;
  fileName: string;
  sizeBytes: number;
  sourceKind: "computer" | "telegram" | "official_moj" | "official_bog";
  status: "pending_indexing" | "indexed" | "duplicate" | "failed";
  documentType: string;
  issuer: string | null;
  publishingAuthority?: string | null;
  originatingAuthority?: string | null;
  hijriYear: string | null;
  subject: string | null;
  relevance?: number;
  matchContext?: string | null;
  matchedTerms?: string[];
  recordKind?: "file" | "legal_document";
  title?: string;
  referenceNo?: string | null;
  summary?: string;
  sourceUrl?: string | null;
  specialty?: string;
  verified?: boolean;
  granularity?: "case" | "document";
  caseNumber?: string | null;
  judgmentNumber?: string | null;
  court?: string | null;
  circuit?: string | null;
};

type IndexedDatabaseRecord = Omit<ArchivedSearchRecord, "fileName" | "sizeBytes" | "status"> & {
  title: string;
  documentType: string;
  referenceNo: string | null;
  summary: string;
  sourceUrl: string | null;
};

function databaseRecord(item: IndexedDatabaseRecord): ArchivedSearchRecord {
  return {
    ...item,
    fileName: item.title,
    sizeBytes: 0,
    status: "indexed",
    recordKind: "legal_document",
  };
}

function visiblePublishingAuthority(item: ArchivedSearchRecord) {
  const publisher = item.publishingAuthority ?? item.issuer;
  if (publisher && normalizeArabic(publisher).includes("اعداد عمر صالح الشهري")) {
    return item.originatingAuthority ?? item.issuer;
  }
  return publisher;
}

type MainCollection =
  | "الكل"
  | "الأحكام القضائية"
  | "السوابق القضائية الإدارية"
  | "سوابق وقرارات الملكية الفكرية"
  | "المبادئ والقرارات القضائية"
  | "التعاميم";

const mainCollections: Exclude<MainCollection, "الكل">[] = [
  "الأحكام القضائية",
  "السوابق القضائية الإدارية",
  "سوابق وقرارات الملكية الفكرية",
  "المبادئ والقرارات القضائية",
  "التعاميم",
];

function isJudgmentType(documentType: string) {
  return documentType === "حكم قضائي"
    || documentType === "صك قضائي"
    || documentType === "سابقة قضائية";
}

function matchesMainCollection(
  collection: MainCollection,
  record: {
    id?: string;
    documentType: string;
    specialty: string;
    publishingAuthority?: string | null;
    originatingAuthority?: string | null;
    subject?: string | null;
    title?: string | null;
  },
) {
  if (collection === "الكل") return true;
  const authority = normalizeArabic([
    record.publishingAuthority,
    record.originatingAuthority,
  ].filter(Boolean).join(" "));
  const isIp = record.specialty === "ملكية فكرية"
    || record.id?.startsWith("saip-copyright-")
    || record.documentType === "قرار ملكية فكرية"
    || record.documentType === "مبدأ قضائي دولي";
  const isAdministrativePrecedent = record.documentType === "سابقة قضائية"
    && (record.id?.startsWith("bog-precedent-")
      || /ديوان المظالم|محكمه اداريه|المحاكم الاداريه/.test(authority));

  if (collection === "الأحكام القضائية") return isJudgmentType(record.documentType) && !isIp && !isAdministrativePrecedent;
  if (collection === "السوابق القضائية الإدارية") return isAdministrativePrecedent;
  if (collection === "سوابق وقرارات الملكية الفكرية") {
    return isIp;
  }
  if (collection === "المبادئ والقرارات القضائية") {
    return record.documentType === "مبدأ قضائي"
      || (record.documentType.includes("قرار") && !isIp && !isAdministrativePrecedent);
  }
  return record.documentType.startsWith("تعميم");
}

export default function LegalSearch() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [collection, setCollection] = useState<MainCollection>("الكل");
  const [issuer, setIssuer] = useState("الكل");
  const [origin, setOrigin] = useState("الكل");
  const [year, setYear] = useState("الكل");
  const [specialty, setSpecialty] = useState("الكل");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [openedDocument, setOpenedDocument] = useState<(typeof legalDocuments)[number] | null>(null);
  const [archivedResults, setArchivedResults] = useState<ArchivedSearchRecord[]>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  const [archiveStatsLoaded, setArchiveStatsLoaded] = useState(false);
  const [archiveStats, setArchiveStats] = useState({
    total: 0,
    indexed: 0,
    official: 0,
    judgments: 0,
    circulars: 0,
    decisions: 0,
    precedents: 0,
    principles: 0,
    contentTotal: 0,
    administrativePrecedents: 0,
    ipPrecedentsOrDecisions: 0,
    judicialPrinciplesOrDecisions: 0,
  });

  useEffect(() => {
    void fetch("/api/archive", { cache: "no-store" })
      .then((response) => response.ok ? response.json() : null)
      .then((payload: { stats?: typeof archiveStats } | null) => {
        if (payload?.stats) setArchiveStats(payload.stats);
      })
      .finally(() => setArchiveStatsLoaded(true));
  }, []);

  const years = useMemo(
    () => Array.from(new Set(legalDocuments.map((item) => item.hijriYear))).sort().reverse(),
    [],
  );
  const publishingAuthorities = useMemo(
    () => Array.from(new Set([
      ...legalDocuments.map((item) => item.publishingAuthority),
      ...sourceRegistry.map((item) => item.authority),
    ])),
    [],
  );
  const originatingAuthorities = useMemo(
    () => Array.from(new Set(legalDocuments.map((item) => item.originatingAuthority))),
    [],
  );

  const staticStats = useMemo(() => {
    const records = searchCorpus.filter(({ item }) => item.granularity === "case");
    const judgments = records.filter((entry) => matchesMainCollection(
      "الأحكام القضائية",
      {
        id: entry.item.id,
        documentType: entry.item.type,
        specialty: entry.specialty,
        publishingAuthority: entry.item.publishingAuthority,
        originatingAuthority: entry.item.originatingAuthority,
      },
    )).length;
    // These counters are intentionally disjoint. IP and administrative records
    // belong to their dedicated collections and must not be counted again here.
    const decisions = records.filter((entry) => matchesMainCollection(
      "المبادئ والقرارات القضائية",
      {
        id: entry.item.id,
        documentType: entry.item.type,
        specialty: entry.specialty,
        publishingAuthority: entry.item.publishingAuthority,
        originatingAuthority: entry.item.originatingAuthority,
        subject: entry.item.subject,
        title: entry.item.title,
      },
    ) && entry.item.type.includes("قرار")).length;
    const principles = records.filter(({ item }) => item.type === "مبدأ قضائي").length;
    const circulars = records.filter(({ item }) => item.type.startsWith("تعميم")).length;
    const administrativePrecedents = records.filter((entry) => matchesMainCollection(
      "السوابق القضائية الإدارية",
      {
        id: entry.item.id,
        documentType: entry.item.type,
        specialty: entry.specialty,
        publishingAuthority: entry.item.publishingAuthority,
        originatingAuthority: entry.item.originatingAuthority,
        subject: entry.item.subject,
        title: entry.item.title,
      },
    )).length;
    const ipPrecedentsOrDecisions = records.filter((entry) => matchesMainCollection(
      "سوابق وقرارات الملكية الفكرية",
      {
        id: entry.item.id,
        documentType: entry.item.type,
        specialty: entry.specialty,
        publishingAuthority: entry.item.publishingAuthority,
        originatingAuthority: entry.item.originatingAuthority,
        subject: entry.item.subject,
        title: entry.item.title,
      },
    )).length;
    const judicialPrinciplesOrDecisions = records.filter((entry) => matchesMainCollection(
      "المبادئ والقرارات القضائية",
      {
        id: entry.item.id,
        documentType: entry.item.type,
        specialty: entry.specialty,
        publishingAuthority: entry.item.publishingAuthority,
        originatingAuthority: entry.item.originatingAuthority,
        subject: entry.item.subject,
        title: entry.item.title,
      },
    )).length;
    return {
      judgments,
      decisions,
      principles,
      circulars,
      contentTotal: judgments + administrativePrecedents + ipPrecedentsOrDecisions + judicialPrinciplesOrDecisions + circulars,
      administrativePrecedents,
      ipPrecedentsOrDecisions,
      judicialPrinciplesOrDecisions,
    };
  }, []);

  const combinedStats = {
    judgments: staticStats.judgments + archiveStats.judgments,
    decisions: staticStats.decisions + archiveStats.decisions,
    principles: staticStats.principles + archiveStats.principles,
    circulars: staticStats.circulars + archiveStats.circulars,
    contentTotal: staticStats.contentTotal + archiveStats.contentTotal,
    administrativePrecedents: staticStats.administrativePrecedents + archiveStats.administrativePrecedents,
    ipPrecedentsOrDecisions: staticStats.ipPrecedentsOrDecisions + archiveStats.ipPrecedentsOrDecisions,
    judicialPrinciplesOrDecisions: staticStats.judicialPrinciplesOrDecisions + archiveStats.judicialPrinciplesOrDecisions,
  };

  const results = useMemo(() => {
    // The search page must stay empty until the beneficiary submits a query.
    // Filters refine a search; they must not expose an arbitrary first page of cases.
    if (!shouldShowSearchResults(submittedQuery)) return [];
    return searchCorpus.map((entry) => {
      const relevance = scoreIndexedDocument(entry, submittedQuery);
      return {
        ...entry.item,
        relevance: relevance.score,
        matchedTerms: relevance.matchedTerms,
        inferredSpecialty: entry.specialty,
      };
    }).filter((item) => {
      if (item.granularity !== "case") return false;
      const matchesQuery = item.relevance > 0;
      const matchesCollection = matchesMainCollection(collection, {
        id: item.id,
        documentType: item.type,
        specialty: item.inferredSpecialty,
        publishingAuthority: item.publishingAuthority,
        originatingAuthority: item.originatingAuthority,
        subject: item.subject,
        title: item.title,
      });
      const matchesIssuer = issuer === "الكل" || item.publishingAuthority === issuer;
      const matchesOrigin = origin === "الكل" || item.originatingAuthority === origin;
      const matchesYear = year === "الكل" || item.hijriYear === year;
      const matchesSpecialty = specialty === "الكل" || item.inferredSpecialty === specialty;
      return matchesQuery && matchesCollection && matchesIssuer && matchesOrigin && matchesYear && matchesSpecialty;
    }).sort((a, b) => b.relevance - a.relevance).slice(0, 80);
  }, [submittedQuery, collection, issuer, origin, year, specialty]);

  const expandedTerms = useMemo(
    () => submittedQuery.trim() ? legalSearchTerms(submittedQuery).expanded : [],
    [submittedQuery],
  );

  const filteredArchivedResults = useMemo(
    () => archivedResults.filter((item) => {
      const isBeneficiaryRecord = item.documentType === "حكم قضائي"
        || item.documentType === "صك قضائي"
        || item.documentType.startsWith("تعميم")
        || item.documentType.includes("قرار")
        || item.documentType === "سابقة قضائية"
        || item.documentType === "مبدأ قضائي";
      if (!isBeneficiaryRecord) return false;
      if (item.granularity !== "case") return false;
      const archivePublisher = visiblePublishingAuthority(item);
      const matchesIssuer = issuer === "الكل" || archivePublisher === issuer;
      const matchesOrigin = origin === "الكل" || item.originatingAuthority === origin;
      const matchesYear = year === "الكل" || item.hijriYear === year;
      const archiveSpecialty = item.specialty || inferSpecialty(`${item.subject ?? ""} ${item.documentType}`);
      const matchesCollection = matchesMainCollection(collection, {
        id: item.id,
        documentType: item.documentType,
        specialty: archiveSpecialty,
        publishingAuthority: archivePublisher,
        originatingAuthority: item.originatingAuthority,
        subject: item.subject,
        title: item.title ?? item.fileName,
      });
      const matchesSpecialty = specialty === "الكل" || archiveSpecialty === specialty;
      return matchesCollection && matchesIssuer && matchesOrigin && matchesYear && matchesSpecialty;
    }),
    [archivedResults, collection, issuer, origin, year, specialty],
  );

  const resultCount = results.length + filteredArchivedResults.length;

  async function searchPrivateArchive(value: string) {
    if (!value.trim()) {
      setArchivedResults([]);
      return;
    }
    setArchiveLoading(true);
    try {
      const response = await fetch(`/api/archive?query=${encodeURIComponent(value)}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        setArchivedResults([]);
        return;
      }
      const payload = (await response.json()) as {
        files?: ArchivedSearchRecord[];
        documents?: IndexedDatabaseRecord[];
        stats?: {
          total: number;
          indexed: number;
          official: number;
          judgments: number;
          circulars: number;
          decisions: number;
          precedents: number;
          principles: number;
          contentTotal: number;
          administrativePrecedents: number;
          ipPrecedentsOrDecisions: number;
          judicialPrinciplesOrDecisions: number;
        };
      };
      setArchivedResults([...(payload.documents ?? []).map(databaseRecord), ...(payload.files ?? []).map((item) => ({ ...item, recordKind: "file" as const }))]);
      if (payload.stats) setArchiveStats(payload.stats);
    } catch {
      setArchivedResults([]);
    } finally {
      setArchiveLoading(false);
    }
  }

  function runSearch(value = query) {
    setQuery(value);
    setSubmittedQuery(value);
    void searchPrivateArchive(value);
  }

  function resetFilters() {
    setQuery("");
    setSubmittedQuery("");
    setCollection("الكل");
    setIssuer("الكل");
    setOrigin("الكل");
    setYear("الكل");
    setSpecialty("الكل");
    setArchivedResults([]);
  }

  async function copyCitation(item: LegalDocument) {
    const origin = item.originatingAuthority === item.publishingAuthority
      ? ""
      : `، الأصل: ${item.originatingAuthority}`;
    const yearLabel = /^\d/.test(item.hijriYear) ? `${item.hijriYear}هـ` : item.hijriYear;
    const citation = `${item.title}، الناشر: ${item.publishingAuthority}${origin}، ${item.reference}، ${yearLabel}، ${item.sourceUrl}`;
    await navigator.clipboard.writeText(citation);
    setCopiedId(item.id);
    window.setTimeout(() => setCopiedId(null), 1800);
  }

  return (
    <main>
      <header className="site-header">
        <div className="shell header-inner">
          <a className="brand" href="#top" aria-label="الباحثة القانونية الذكية">
            <span className="brand-mark">ب</span>
            <span>
              <strong>الباحثة القانونية الذكية</strong>
              <small>بإشراف د. رباب أحمد المعبي</small>
            </span>
          </a>
          <nav aria-label="التنقل الرئيسي">
            <a href="#search">البحث</a>
            <a href="#library-sections-title">الأقسام</a>
            <a href="#archive">سحب الأحكام</a>
            <a href="#sources">المصادر</a>
            <a href="#methodology">منهجية التحقق</a>
          </nav>
          <span className="header-badge">نسخة تشغيلية خاصة</span>
        </div>
      </header>

      <section className="hero" id="top">
        <div className="hero-glow hero-glow-one" />
        <div className="hero-glow hero-glow-two" />
        <div className="shell hero-content">
          <div className="eyebrow"><span /> مرجع قانوني سعودي موثّق</div>
          <h1>ابحث في الأحكام والقرارات<br />والمبادئ والتعاميم بذكاء</h1>
          <p className="hero-copy">
            ابحث بالموضوع أو رقم الحكم أو السابقة أو القرار أو التعميم؛ يفهم المحرك المرادفات القانونية،
            وتظهر الأعداد الإجمالية الموثقة لكل قسم مع ترتيب النتائج بحسب الصلة والمصدر.
          </p>

          <form
            className="search-box"
            id="search"
            onSubmit={(event) => {
              event.preventDefault();
              runSearch();
              document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            <label htmlFor="legal-query" className="sr-only">نص البحث القانوني</label>
            <input
              id="legal-query"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="اكتب رقم التعميم، موضوعه، أو كلمة من الحكم..."
              autoComplete="off"
            />
            <button type="submit">بحث</button>
          </form>

          <div className="quick-row" aria-label="عمليات بحث مقترحة">
            <span>بحث سريع:</span>
            {quickSearches.map((item) => (
              <button
                type="button"
                key={item}
                onClick={() => {
                  runSearch(item);
                  document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                {item}
              </button>
            ))}
          </div>

          <div className="trust-strip">
            <div className="total-stat"><strong>{archiveStatsLoaded ? combinedStats.contentTotal.toLocaleString("en-US") : "—"}</strong><span>إجمالي المواد القانونية المفهرسة</span></div>
            <div><strong>{archiveStatsLoaded ? combinedStats.judgments.toLocaleString("en-US") : "—"}</strong><span>حكمًا قضائيًا</span></div>
            <div><strong>{archiveStatsLoaded ? combinedStats.administrativePrecedents.toLocaleString("en-US") : "—"}</strong><span>سابقة قضائية إدارية</span></div>
            <div><strong>{archiveStatsLoaded ? combinedStats.ipPrecedentsOrDecisions.toLocaleString("en-US") : "—"}</strong><span>سابقة أو قرار ملكية فكرية</span></div>
            <div><strong>{archiveStatsLoaded ? combinedStats.judicialPrinciplesOrDecisions.toLocaleString("en-US") : "—"}</strong><span>مبدأ أو قرار قضائي</span></div>
            <div><strong>{archiveStatsLoaded ? combinedStats.circulars.toLocaleString("en-US") : "—"}</strong><span>تعميمًا</span></div>
          </div>
        </div>
      </section>

      <section className="library-sections shell" aria-labelledby="library-sections-title">
        <div className="library-sections-heading">
          <span className="section-kicker">نطاق الباحثة القانونية</span>
          <h2 id="library-sections-title">الأقسام الرئيسية</h2>
          <p>كل مادة محفوظة مرة واحدة، وتظهر في قسمها المتخصص دون مضاعفة العدد الإجمالي.</p>
        </div>
        <div className="library-sections-grid">
          {mainCollections.map((item) => {
            const count = item === "الأحكام القضائية" ? combinedStats.judgments
              : item === "السوابق القضائية الإدارية" ? combinedStats.administrativePrecedents
              : item === "سوابق وقرارات الملكية الفكرية" ? combinedStats.ipPrecedentsOrDecisions
              : item === "المبادئ والقرارات القضائية" ? combinedStats.judicialPrinciplesOrDecisions
              : combinedStats.circulars;
            return (
              <button
                type="button"
                key={item}
                className={collection === item ? "library-section-card active" : "library-section-card"}
                onClick={() => {
                  setCollection(item);
                  document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
                }}
              >
                <strong>{archiveStatsLoaded ? count.toLocaleString("en-US") : "—"}</strong>
                <span>{item}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="results-section shell" id="results">
        <aside className="filters" aria-label="فلاتر البحث">
          <div className="filters-heading">
            <div>
              <span className="section-kicker">تصفية النتائج</span>
              <h2>حدد نطاق البحث</h2>
            </div>
            <button className="text-button" type="button" onClick={resetFilters}>إعادة ضبط</button>
          </div>

          <label>
            القسم الرئيسي
            <select value={collection} onChange={(event) => setCollection(event.target.value as MainCollection)}>
              <option>الكل</option>
              {mainCollections.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>

          <label>
            الاختصاص
            <select value={specialty} onChange={(event) => setSpecialty(event.target.value)}>
              <option>الكل</option>
              {specialties.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>

          <label>
            الجهة الناشرة
            <select value={issuer} onChange={(event) => setIssuer(event.target.value)}>
              <option>الكل</option>
              {publishingAuthorities.map((authority) => <option key={authority}>{authority}</option>)}
            </select>
          </label>

          <label>
            مصدر الأصل النظامي
            <select value={origin} onChange={(event) => setOrigin(event.target.value)}>
              <option>الكل</option>
              {originatingAuthorities.map((authority) => <option key={authority}>{authority}</option>)}
            </select>
          </label>

          <label>
            السنة الهجرية
            <select value={year} onChange={(event) => setYear(event.target.value)}>
              <option>الكل</option>
              {years.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>

          <div className="verified-note">
            <span className="verified-icon">✓</span>
            <div>
              <strong>مصدر كل وثيقة ظاهر</strong>
              <p>تُميّز المصادر الرسمية عن نسخ المكتبة الخاصة، ويُفصل بين الناشر ومصدر الأصل.</p>
            </div>
          </div>
        </aside>

        <div className="results-column">
          <div className="results-toolbar">
            <div>
              <span className="section-kicker">نتائج البحث</span>
              <h2>{resultCount} نتيجة</h2>
            </div>
            {submittedQuery && <p>عن: <strong>«{submittedQuery}»</strong></p>}
          </div>

          {expandedTerms.length > 1 && (
            <div className="search-intelligence" role="status">
              <strong>فهم البحث:</strong>
              <span>بحث المحرك أيضًا عن</span>
              {expandedTerms.slice(0, 7).map((term) => <i key={term}>{term}</i>)}
            </div>
          )}

          <div className="result-list" aria-live="polite">
            {archiveLoading && (
              <div className="private-search-loading">جارٍ البحث في الأرشيف الخاص...</div>
            )}
            {filteredArchivedResults.length > 0 && (
              <section className="private-results" aria-label="نتائج الأرشيف الخاص">
                <div className="private-results-heading">
                  <span>أرشيفك الخاص</span>
                  <strong>{filteredArchivedResults.length} مستندًا مطابقًا</strong>
                </div>
                {filteredArchivedResults.map((item) => (
                  <article className="private-result-card" key={item.id}>
                    <div>
                      <span className="private-result-badge">{item.verified ? `✓ ${item.documentType} مفهرس` : "✦ محفوظ في الأرشيف"}</span>
                      <span className="document-title-label">عنوان الحكم</span>
                      <h3>{/^التصنيف\s+رقم/.test(item.fileName) && (item.judgmentNumber || item.referenceNo)
                        ? `حكم ${item.court || item.originatingAuthority || item.issuer || "قضائي"} رقم ${item.judgmentNumber || item.referenceNo}`
                        : item.fileName}</h3>
                      {item.recordKind === "legal_document" && (
                        <dl className="document-identifiers">
                          <div><dt>رقم القضية</dt><dd>{item.caseNumber || "غير مدون"}</dd></div>
                          <div><dt>رقم الحكم/الصك</dt><dd>{item.judgmentNumber || item.referenceNo || "غير مدون"}</dd></div>
                          <div><dt>المحكمة</dt><dd>{item.court || item.originatingAuthority || item.issuer || "غير مدونة"}</dd></div>
                          <div><dt>الدائرة</dt><dd>{item.circuit || "غير مدونة"}</dd></div>
                        </dl>
                      )}
                      <p>
                        {item.documentType}
                        {visiblePublishingAuthority(item) ? ` · جهة النشر: ${visiblePublishingAuthority(item)}` : ""}
                        {item.originatingAuthority ? ` · الجهة الأصلية: ${item.originatingAuthority}` : ""}
                        {item.hijriYear ? ` · ${item.hijriYear}هـ` : ""}
                        {` · ${item.sourceKind === "official_moj" || item.sourceKind === "official_bog" ? "مصدر رسمي" : "محفوظ في الأرشيف"}`}
                      </p>
                      {item.summary && <p className="match-context">{item.summary}</p>}
                      {item.matchContext && <p className="match-context">{item.matchContext}</p>}
                      {!!item.matchedTerms?.length && (
                        <div className="match-terms">مطابقة: {item.matchedTerms.join("، ")}</div>
                      )}
                    </div>
                    <a href={item.recordKind === "legal_document" ? `/api/documents/${encodeURIComponent(item.id)}` : `/api/archive/file/${item.id}`} target={item.recordKind === "legal_document" ? "_blank" : undefined} rel="noreferrer">
                      {item.recordKind === "legal_document" ? "عرض المستند المستقل ↗" : "تنزيل الأصل ↙"}
                    </a>
                  </article>
                ))}
              </section>
            )}
            {results.length ? results.map((item) => (
              <article className="result-card" key={item.id}>
                <div className="result-topline">
                  <div className="result-tags">
                  <span className={`document-type ${item.type.startsWith("تعميم") ? "circular" : "judicial"}`}>
                      {item.type}
                    </span>
                    <span className={item.verified ? "verified-pill" : "library-pill"}>
                      {item.verified ? "✓ موثّق من المصدر الرسمي" : "⌁ نسخة من المكتبة الخاصة"}
                    </span>
                    {submittedQuery && item.relevance >= results[0]?.relevance && (
                      <span className="best-match-pill">الأكثر صلة</span>
                    )}
                  </div>
                  <span className="reference">{item.reference}</span>
                </div>
                <h3>{item.title}</h3>
                <div className="meta-row">
                  <span className="specialty-meta">{inferSpecialty(`${item.title} ${item.subject} ${item.keywords.join(" ")} ${item.searchText ?? ""}`)}</span>
                  <span className="authority-meta"><b>الجهة الأصلية</b>{item.originatingAuthority}</span>
                  {item.publishingAuthority !== item.originatingAuthority && (
                    <span className="authority-meta"><b>جهة النشر</b>{item.publishingAuthority}</span>
                  )}
                  <span>{item.subject}</span>
                  <span>{/^\d/.test(item.hijriYear) ? `${item.hijriYear}هـ` : item.hijriYear}</span>
                </div>
                <p className="result-summary">{item.summary}</p>
                {!!item.matchedTerms.length && submittedQuery && (
                  <p className="why-match">سبب الظهور: تطابق مع {item.matchedTerms.join("، ")}</p>
                )}
                <div className="keywords">
                  {item.keywords.map((keyword) => <span key={keyword}>#{keyword}</span>)}
                </div>
                <div className="result-footer">
                  <button type="button" className="open-document-button" onClick={() => setOpenedDocument(item)}>
                    عرض المستند <span aria-hidden="true">↗</span>
                  </button>
                  <button type="button" onClick={() => copyCitation(item)}>
                    {copiedId === item.id ? "تم نسخ الاستشهاد" : "نسخ الاستشهاد"}
                  </button>
                </div>
              </article>
            )) : !filteredArchivedResults.length && !archiveLoading ? (
              <div className="empty-state">
                <span>لا توجد نتيجة مطابقة</span>
                <h3>جرّب كلمة أوسع أو أعد ضبط الفلاتر</h3>
                <button type="button" onClick={resetFilters}>عرض جميع الوثائق</button>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      <ArchivePanel />

      {openedDocument && (
        <div className="document-viewer-backdrop" role="dialog" aria-modal="true" aria-label={`عرض ${openedDocument.type}`}>
          <section className="document-viewer">
            <header>
              <div>
                <span>{openedDocument.type}</span>
                <h2>{openedDocument.title}</h2>
                <p>{openedDocument.reference} · {openedDocument.publishingAuthority}</p>
              </div>
              <button type="button" onClick={() => setOpenedDocument(null)} aria-label="إغلاق المستند">×</button>
            </header>
            <iframe src={openedDocument.sourceUrl} title={openedDocument.title} />
            <footer>
              <a href={openedDocument.sourceUrl} download>تحميل المستند PDF</a>
              <button type="button" onClick={() => setOpenedDocument(null)}>إغلاق</button>
            </footer>
          </section>
        </div>
      )}

      <section className="sources-section" id="sources">
        <div className="shell">
          <div className="section-heading">
            <div>
              <span className="section-kicker light">أنواع الوثائق</span>
              <h2>ابحث بحسب نوع المستند القضائي</h2>
            </div>
            <p>يظهر نوع الوثيقة بوضوح قبل الجهة: صك، حكم، مدونة قضائية، أو تعميم.</p>
          </div>
          <div className="source-grid">
            {[
              { type: "صك قضائي", symbol: "ص", description: "الصكوك القضائية وبيانات الحكم المثبتة فيها." },
              { type: "حكم قضائي", symbol: "ح", description: "الأحكام الفردية مصنفة بحسب الموضوع والسنة والمرجع." },
              { type: "مدونة قضائية", symbol: "م", description: "مجموعات ومدونات الأحكام والمبادئ القضائية." },
              { type: "تعميم", symbol: "ت", description: "التعاميم الوزارية والقضائية مع رقمها وتاريخها." },
            ].map((document) => (
              <article className="source-card" key={document.type}>
                <div className="source-card-top">
                  <span className="source-symbol">{document.symbol}</span>
                  <span className="source-status"><i /> نوع وثيقة</span>
                </div>
                <small>تصنيف قضائي</small>
                <h3>{document.type}</h3>
                <p>{document.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="methodology shell" id="methodology">
        <div className="methodology-title">
          <span className="section-kicker">منهجية التحقق</span>
          <h2>من المصدر إلى نتيجة البحث</h2>
          <p>مسار واضح يمنع الخلط بين النص الرسمي والملخص التعريفي.</p>
        </div>
        <ol className="methodology-steps">
          <li><span>01</span><strong>رصد المصدر</strong><p>اعتماد الصفحة الحكومية أو الإصدار الرسمي.</p></li>
          <li><span>02</span><strong>فصل جهات الوثيقة</strong><p>تمييز الناشر عن مصدر القرار أو التوجيه الأصلي.</p></li>
          <li><span>03</span><strong>منع التكرار</strong><p>مطابقة الرقم والرابط قبل إضافة السجل.</p></li>
          <li><span>04</span><strong>إتاحة البحث</strong><p>فهرسة عربية مع رابط مباشر للمصدر.</p></li>
        </ol>
      </section>

      <footer>
        <div className="shell footer-inner">
          <div>
            <strong>الباحثة القانونية الذكية</strong>
            <p>مشروع قانوني رقمي بإشراف د. رباب أحمد المعبي.</p>
          </div>
          <p className="disclaimer">
            الملخصات للتعريف والبحث ولا تُعد بديلًا عن النص الرسمي النافذ. يجب الرجوع إلى المصدر والتحقق من آخر تحديث قبل الاستناد المهني.
          </p>
        </div>
      </footer>
    </main>
  );
}
