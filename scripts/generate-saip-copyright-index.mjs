import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const sourcePath = resolve(
  process.argv[2] || "public/library/saip-copyright-precedents-2019.pdf",
);
const outputPath = resolve(
  process.argv[3] || "app/saip-copyright-index.generated.json",
);

const localTitles = [
  "حيازة مواد منسوخة واستخدام برمجيات منسوخة",
  "الاعتداء على شعار حملة والمطالبة بالتعويض",
  "تحميل أجهزة الحاسب ببرامج منسوخة",
  "شروط قبول الدعوى وتركها لخطأ عنوان المدعى عليه",
  "نشر صورة قاصر في كتاب مدرسي دون إذن وليه",
  "اعتداء قناة فضائية على قصيدة",
  "حيازة كتب منسوخة ومصورة",
  "الاعتداء على لحن قصيدة",
  "الاعتداء على رسالة دكتوراه وحجب الصفحة الإلكترونية",
  "نشر صورة على غلاف مجلة",
  "ضبط وسائط منسوخة وإحالة المخالفة للنيابة العامة",
  "نشر مقطع فيديو من تصوير المدعي",
  "نشر صورة فوتوغرافية دون إذن صاحبها",
  "الاعتداء على تصميمات ذهب وتقليدها وبيعها",
  "نشر قصيدة دون إذن ونسبتها إلى غير قائلها",
  "نشر أجزاء من كتاب في مقالات صحفية",
  "ضبط وسائط منسوخة مع السجن والتشهير",
  "نشر صورة دون ذكر المصدر",
  "استخدام رسائل نصية صحية وتسويقها دون إذن",
  "طباعة كتاب دون إذن صاحبه",
  "إغفال اسم المشارك في تأليف الكتب",
  "بيع منتجات منسوخة",
  "نشر صورة شخصية في موقع صحيفة",
  "الاعتداء على صور محمية",
  "طباعة ونشر كتب دون موافقة مالكها",
  "الاعتداء على رسومات وتصاميم لقوالب زجاجية",
  "مخالفة محل لنظام حماية حقوق المؤلف",
  "توزيع قنوات فضائية مشفرة بمقابل مادي",
  "نسخ كتب في محل تجاري",
  "الاعتداء على تصميم وبيعه عبر إنستغرام",
  "استخدام برامج حاسب منسوخة",
  "الاعتداء على كتابين وتوزيعهما دون إذن",
  "بيع أسطوانات ألعاب منسوخة",
  "إتاحة كتاب بصيغة PDF دون إذن المؤلف",
  "عرض بيع كتاب إلكترونيًا دون إذن المؤلف",
  "اعتداء قناة على قصيدة وبثها للمشاهدين",
];

const localStarts = [
  7, 8, 11, 13, 14, 17, 23, 25, 27, 29, 32, 35, 39, 41, 44, 46, 51, 54,
  57, 63, 65, 78, 79, 82, 85, 95, 100, 102, 104, 106, 110, 112, 115, 117,
  119, 121,
];

const internationalTitles = [
  "التفرقة بين الفكرة والتعبير عنها",
  "الابتكار معيار الحماية",
  "الحماية القانونية لأفلام الفيديو",
  "اشتراط الإذن المكتوب لحماية المصنف المشتق",
  "حق المؤلف في تحديد زمان وطريقة نشر مصنفه",
  "وجوب ذكر اسم المؤلف قرين مصنفه",
  "حق المؤلف في تعديل مصنفه أو تحويره",
  "حدود الدراسات التحليلية والاقتباسات القصيرة",
  "حق المترجم في ذكر اسمه قرين اسم المؤلف",
  "حق المؤلف في المصنف الجماعي",
  "حقوق الموظفين على المصنفات التي أبدعوها",
  "الإذن الكتابي لنشر المصنف واستغلاله ماليًا",
  "الأمر على عريضة لحماية المصنف مؤقتًا",
  "الحكم في التظلم من الأمر الوقتي",
  "قرينة العلم بتقليد المصنف",
  "القصد الجنائي في جريمة تقليد المصنف",
  "التعويض عن امتناع الناشر عن نشر المصنف",
];

const internationalStarts = [
  128, 130, 132, 134, 136, 138, 140, 142, 144, 145, 147, 149, 151, 153,
  155, 156, 158,
];

const rawText = execFileSync("pdftotext", ["-layout", sourcePath, "-"], {
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const pages = rawText.split("\f");
const checksum = createHash("sha256").update(readFileSync(sourcePath)).digest("hex");

function clean(value) {
  return value
    .normalize("NFKC")
    .replace(/[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, "")
    .replace(/[\u064b-\u065f\u0670]/g, "")
    .replace(/ـ/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

const starts = [...localStarts, ...internationalStarts];
const titles = [...localTitles, ...internationalTitles];
if (starts.length !== 53 || titles.length !== 53) {
  throw new Error("يجب أن يحتوي فهرس الهيئة على 53 سجلًا.");
}

const records = starts.map((startPage, index) => {
  const endPage = index + 1 < starts.length ? starts[index + 1] - 1 : pages.length;
  const number = index + 1;
  const isLocalDecision = number <= 36;
  const extractedText = clean(
    pages.slice(startPage - 1, endPage).join(" "),
  ).slice(0, 180_000);
  return {
    id: `saip-copyright-${number}`,
    documentType: isLocalDecision ? "قرار ملكية فكرية" : "مبدأ قضائي دولي",
    title: isLocalDecision
      ? `قرار حقوق المؤلف رقم ${number} — ${titles[index]}`
      : `مبدأ قضائي دولي رقم ${number} — ${titles[index]}`,
    reference: String(number),
    subject: titles[index],
    sourceFile: "saip-copyright-precedents-2019.pdf",
    sourceChecksum: checksum,
    startPage,
    endPage,
    searchText: extractedText,
    granularity: "case",
    specialty: "ملكية فكرية",
    publishingAuthority: "الهيئة السعودية للملكية الفكرية",
    originatingAuthority: isLocalDecision
      ? "لجنة النظر في مخالفات نظام حماية حقوق المؤلف"
      : "سوابق قضائية دولية مختارة في حقوق المؤلف",
    hijriYear: "2019م",
    verified: true,
  };
});

writeFileSync(outputPath, `${JSON.stringify(records, null, 2)}\n`);
console.log(`Generated ${records.length} independent SAIP copyright records.`);
