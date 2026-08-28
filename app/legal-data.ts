import caseIndex from "./case-index.generated.json";
import referenceText from "./reference-text.generated.json";
import specializedText from "./specialized-text.generated.json";
import specializedCaseIndex from "./specialized-case-index.generated.json";
import snippetIndex from "./snippet-index.generated.json";

export type LegalDocument = {
  id: string;
  title: string;
  type: "تعميم وزاري" | "تعميم قضائي" | "مدونة قضائية" | "مجموعة أحكام" | "مبدأ قضائي" | "سابقة قضائية" | "بحث قضائي" | "حكم قضائي" | "دليل قانوني";
  publishingAuthority: string;
  originatingAuthority: string;
  hijriYear: string;
  reference: string;
  subject: string;
  summary: string;
  keywords: string[];
  sourceUrl: string;
  sourceLabel: string;
  verified: boolean;
  searchText?: string;
  granularity?: "document" | "case";
};

const mojCircularsUrl =
  "https://portaleservices.moj.gov.sa/TameemPortal/TameemList.aspx?id=27063";
const bogCollectionsUrl =
  "https://www.bog.gov.sa/knowledge-center/JudicialBlogs/Pages/JudgmentsDefault.aspx?PageIndex=1";
const scjCircularsUrl = "https://www.scj.gov.sa/";

const baseLegalDocuments: LegalDocument[] = [
  {
    id: "library-uncitral-arbitration-2024",
    title: "السوابق القضائية المستندة إلى نصوص الأونسيترال (كلاوت) — القضايا 2163–2168",
    type: "مجموعة أحكام",
    publishingAuthority: "لجنة الأمم المتحدة للقانون التجاري الدولي (الأونسيترال)",
    originatingAuthority: "محاكم أجنبية ووطنية مختارة ضمن نظام كلاوت",
    hijriYear: "2024م",
    reference: "A/CN.9/SER.C/ABSTRACTS/236",
    subject: "التحكيم التجاري الدولي واتفاقية نيويورك",
    summary:
      "وثيقة أممية عربية مؤرخة في 31 يوليو 2024، تضم ملخصات القضايا 2163–2168 بشأن قانون الأونسيترال النموذجي للتحكيم واتفاقية نيويورك في عدة ولايات قضائية دولية؛ وليست سوابق قضائية سعودية.",
    keywords: ["أونسيترال", "كلاوت", "تحكيم دولي", "اتفاقية نيويورك", "قانون نموذجي", "تنفيذ حكم التحكيم", "بطلان حكم التحكيم"],
    sourceUrl: "/library/uncitral-arbitration-precedents-2024.pdf",
    sourceLabel: "نسخة PDF مرفوعة — وثيقة أممية",
    verified: false,
    granularity: "document",
    searchText: specializedText["uncitral-arbitration-2024"],
  },
  {
    id: "library-bog-administrative-precedents-1402-1436",
    title: "السوابق القضائية لأحكام ديوان المظالم الإدارية 1402–1436هـ",
    type: "مدونة قضائية",
    publishingAuthority: "ديوان المظالم — مكتب الشؤون الفنية",
    originatingAuthority: "محاكم ديوان المظالم الإدارية",
    hijriYear: "1402–1436",
    reference: "رقم الإيداع 7120/1440",
    subject: "سوابق القضاء الإداري",
    summary:
      "مجموعة رسمية لسوابق القضاء الإداري تشمل الاختصاص والخدمة المدنية والعسكرية وإلغاء القرارات والتعويض والعقود الإدارية والتأديب والطلبات العاجلة. اعتمدت النسخة الأصغر بعد إثبات التطابق النصي مع النسخة الأخرى.",
    keywords: ["ديوان المظالم", "قضاء إداري", "إلغاء قرار", "تعويض", "عقد إداري", "تأديب", "خدمة مدنية", "اختصاص"],
    sourceUrl: "/library/bog-administrative-precedents-1402-1436.pdf",
    sourceLabel: "نسخة PDF مرفوعة إلى مكتبة المنصة",
    verified: false,
    granularity: "document",
    searchText: specializedText["bog-administrative-precedents"],
  },
  {
    id: "library-nafa-judicial-library-1445",
    title: "مكتبة نفع القضائية — فهرس قانوني متعدد الاختصاصات",
    type: "دليل قانوني",
    publishingAuthority: "إعداد القاضي حمد بن خالد القاسم",
    originatingAuthority: "فهرس شخصي لمصادر وروابط قانونية متعددة",
    hijriYear: "1445",
    reference: "الإصدار الأول — 2023م",
    subject: "دليل روابط ومراجع قضائية",
    summary:
      "دليل ببليوغرافي يصف أكثر من 800 ملف في 16 قسمًا رئيسيًا و59 قسمًا فرعيًا. هو بوابة روابط لا يحتوي بذاته على جميع نصوص الأحكام؛ واعتمدت النسخة التي تحتفظ بـ804 روابط خارجية.",
    keywords: ["مكتبة نفع", "فهرس قضائي", "أحوال شخصية", "جزائي", "تنفيذ", "تجاري", "عمالي", "إداري", "روابط قانونية"],
    sourceUrl: "/library/nafa-judicial-library-1445.pdf",
    sourceLabel: "نسخة PDF مرفوعة — دليل غير رسمي",
    verified: false,
    granularity: "document",
    searchText: specializedText["nafa-judicial-library"],
  },
  {
    id: "library-ip-judgments-1446",
    title: "أحكام قضائية في الملكية الفكرية",
    type: "مجموعة أحكام",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمتان التجاريتان في الرياض وجدة",
    hijriYear: "1446",
    reference: "ذو الحجة 1446هـ — يونيو 2025م",
    subject: "الملكية الفكرية والعلامات التجارية وحقوق المؤلف",
    summary:
      "تجميع بحثي غير رسمي لسبعة أحكام أو مقتطفات أحكام من عام 1445هـ في العلامات التجارية وحقوق المؤلف والصور وتقليد العلامات ودعاوى إلغاء قرارات الهيئة السعودية للملكية الفكرية.",
    keywords: ["ملكية فكرية", "علامة تجارية", "حقوق مؤلف", "تقليد علامة", "الهيئة السعودية للملكية الفكرية", "المحكمة التجارية"],
    sourceUrl: "/library/ip-judgments-1446.pdf",
    sourceLabel: "نسخة PDF مرفوعة — تجميع بحثي غير رسمي",
    verified: false,
    granularity: "document",
    searchText: specializedText["ip-judgments-1446"],
  },
  {
    id: "library-ip-precedents-guide",
    title: "السوابق القضائية في الملكية الفكرية — كشاف روابط",
    type: "دليل قانوني",
    publishingAuthority: "أضداد للمحاماة — إعداد عزيزة القحطاني",
    originatingAuthority: "كشاف مهني لمراجع خارجية",
    hijriYear: "غير مؤرخ",
    reference: "دليل من 10 إحالات",
    subject: "دليل سوابق الملكية الفكرية وإجراءاتها",
    summary:
      "كشاف مهني غير رسمي يحيل إلى تسعة مجلدات للسوابق ومجلد عن إجراءات دعاوى الملكية الفكرية. لا يحتوي نصوص تلك الأحكام، ولذلك صُنّف دليلًا لا مجموعة أحكام.",
    keywords: ["ملكية فكرية", "سوابق قضائية", "دليل روابط", "إجراءات دعوى", "أضداد", "علامات تجارية"],
    sourceUrl: "/library/ip-precedents.pdf",
    sourceLabel: "نسخة PDF مرفوعة — كشاف غير رسمي",
    verified: false,
    granularity: "document",
    searchText: specializedText["ip-precedents"],
  },
  {
    id: "library-insurance-precedents",
    title: "مدونة السوابق القضائية التأمينية للجنة الاستئنافية",
    type: "مدونة قضائية",
    publishingAuthority: "الأمانة العامة للجان الفصل في المنازعات والمخالفات التأمينية",
    originatingAuthority: "اللجنة الاستئنافية واللجان الابتدائية التأمينية",
    hijriYear: "حتى 1446",
    reference: "نحو 221 سابقة تأمينية",
    subject: "منازعات ومخالفات التأمين",
    summary:
      "إصدار رسمي لقرارات لجان تأمينية مختصة، يشمل المسائل الإجرائية وتأمين المركبات والصحي والممتلكات والهندسي والنقل والطيران والسفر والائتمان والحماية والادخار. لا يُخلط مع أحكام محاكم وزارة العدل.",
    keywords: ["تأمين", "لجنة استئنافية", "مركبات", "تأمين صحي", "ممتلكات", "مقاولات", "حريق", "نقل", "طيران", "حماية وادخار"],
    sourceUrl: "https://idc.gov.sa/ar-sa/DocLib1/%D9%85%D8%AF%D9%88%D9%86%D8%A9%20%D8%A7%D9%84%D8%B3%D9%88%D8%A7%D8%A8%D9%82%20%D8%A7%D9%84%D9%82%D8%B6%D8%A7%D8%A6%D9%8A%D8%A9%20%D8%A7%D9%84%D8%AA%D8%A3%D9%85%D9%8A%D9%86%D9%8A%D8%A9.pdf",
    sourceLabel: "النسخة الرسمية — الأمانة العامة للجان التأمينية",
    verified: true,
    granularity: "document",
    searchText: specializedText["insurance-precedents"],
  },
  {
    id: "library-banking-finance-principles-1443",
    title: "مدونة المبادئ القضائية في المنازعات المصرفية والتمويلية",
    type: "مدونة قضائية",
    publishingAuthority: "الأمانة العامة للجان المنازعات والمخالفات المصرفية والتمويلية",
    originatingAuthority: "اللجان المصرفية والتمويلية الابتدائية والاستئنافية",
    hijriYear: "1443",
    reference: "إصدار 1443هـ / 2022م — نحو 1,023 مبدأ",
    subject: "المنازعات المصرفية والتمويلية",
    summary:
      "إصدار رسمي لمبادئ اللجان المرتبطة بالبنك المركزي السعودي، يغطي الاختصاص والإجراءات والحسابات والائتمان والضمانات والأوراق التجارية والتعويض والتنفيذ والرهن والإيجار التمويلي.",
    keywords: ["مصرفي", "تمويلي", "البنك المركزي السعودي", "ائتمان", "ضمانات", "أوراق تجارية", "رهن", "إيجار تمويلي", "تعويض"],
    sourceUrl: "/library/banking-finance-principles.pdf",
    sourceLabel: "نسخة PDF مرفوعة — إصدار رسمي للجان المصرفية والتمويلية",
    verified: false,
    granularity: "document",
    searchText: specializedText["banking-finance-principles"],
  },
  {
    id: "library-higher-judiciary-principles-1391-1437",
    title: "مبادئ وقرارات الجهات القضائية العليا من 1391هـ إلى 1437هـ",
    type: "مبدأ قضائي",
    publishingAuthority: "وزارة العدل — مركز البحوث",
    originatingAuthority: "الهيئة القضائية العليا والهيئة الدائمة العامة بمجلس القضاء الأعلى والمحكمة العليا",
    hijriYear: "1391–1437",
    reference: "إصدار 1438هـ",
    subject: "مبادئ وقرارات قضائية عليا متعددة المجالات",
    summary:
      "مجموعة رسمية تشمل مبادئ وقرارات ثلاث جهات قضائية عليا متعاقبة، في الأحوال الشخصية والأوقاف والعقار والحدود والقصاص والإجراءات والقواعد العامة. أُبقي فصل الجهة الناشرة عن الجهات المصدرة للأصول.",
    keywords: ["المحكمة العليا", "مجلس القضاء الأعلى", "الهيئة القضائية العليا", "مبادئ قضائية", "أحوال شخصية", "أوقاف", "عقار", "قصاص", "إجراءات"],
    sourceUrl: "/library/higher-judiciary-principles-1391-1437-runtime.pdf",
    sourceLabel: "نسخة PDF مرفوعة — إصدار رسمي لوزارة العدل",
    verified: false,
    granularity: "document",
    searchText: specializedText["higher-judiciary-principles"],
  },
  {
    id: "library-judicial-precedents-links-compilation",
    title: "تجميعات سوابق قضائية — كشاف موضوعي للروابط",
    type: "دليل قانوني",
    publishingAuthority: "تجميع @Splllaw",
    originatingAuthority: "كشاف غير رسمي لمصادر خارجية متعددة",
    hijriYear: "2025م",
    reference: "73 رابطًا خارجيًا",
    subject: "كشاف سوابق متعدد الموضوعات",
    summary:
      "دليل غير رسمي يوزع روابط خارجية على الأحوال الشخصية والجنائي والمخدرات والعقود والتأمين والتنفيذ والعمالي والعقار وغيرها. لا تُعامل الروابط كأحكام مفهرسة قبل جلب أصولها والتحقق من جهاتها.",
    keywords: ["سوابق قضائية", "دليل روابط", "أحوال شخصية", "جنائي", "مخدرات", "عقود", "تأمين", "تنفيذ", "عمالي", "عقار"],
    sourceUrl: "/library/judicial-precedents-compilation.pdf",
    sourceLabel: "نسخة PDF مرفوعة — كشاف غير رسمي",
    verified: false,
    granularity: "document",
    searchText: specializedText["judicial-precedents-compilation"],
  },
  {
    id: "library-moj-judgments-1434-volume-17",
    title: "مجموعة الأحكام القضائية لعام 1434هـ - المجلد السابع عشر",
    type: "مجموعة أحكام",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "المحاكم العامة والجزائية",
    hijriYear: "1434",
    reference: "المجلد 17",
    subject: "قضايا المخدرات والمؤثرات العقلية",
    summary:
      "نسخة مرفوعة من إصدار مركز البحوث بوزارة العدل، وتضم أحكامًا مصدّقة في قضايا التهريب والترويج والتعاطي والحيازة والعقوبات التعزيرية والمصادرة والإبعاد.",
    keywords: ["مخدرات", "تهريب", "ترويج", "تعاطي", "حيازة", "حشيش", "حبوب محظورة", "سجن", "جلد", "إبعاد", "مصادرة"],
    sourceUrl: "/library/moj-judgments-1434-volume-17.pdf",
    sourceLabel: "نسخة PDF مرفوعة إلى مكتبة المنصة",
    verified: false,
  },
  {
    id: "library-commercial-contract-precedents",
    title: "السوابق القضائية في عقود المعاوضات التجارية في المملكة العربية السعودية",
    type: "بحث قضائي",
    publishingAuthority: "الجمعية الفقهية السعودية",
    originatingAuthority: "دراسة تأصيلية تطبيقية",
    hijriYear: "1444",
    reference: "دراسة تأصيلية تطبيقية",
    subject: "عقود المعاوضات التجارية",
    summary:
      "مرجع تطبيقي للدكتور عبدالله بن عبدالرحمن الشهري يعالج السوابق القضائية في عقود المعاوضات التجارية في المملكة، وقد أضيفت نسخة واحدة بعد استبعاد ثلاث نسخ مطابقة.",
    keywords: ["سوابق قضائية", "عقود تجارية", "معاوضات", "بيع", "إجارة", "مقاولة", "توريد", "فسخ العقد", "تعويض", "التزامات"],
    sourceUrl: "/library/commercial-contract-precedents.pdf",
    sourceLabel: "نسخة PDF مرفوعة إلى مكتبة المنصة",
    verified: false,
  },
  {
    id: "library-judicial-precedents-study",
    title: "السوابق القضائية",
    type: "بحث قضائي",
    publishingAuthority: "الجمعية العلمية القضائية السعودية (قضاء)",
    originatingAuthority: "بحث علمي قضائي",
    hijriYear: "غير مؤرخ",
    reference: "بحث قضائي",
    subject: "تعريف السوابق القضائية وحجيتها",
    summary:
      "بحث للشيخ عبدالله بن محمد بن سعد آل خنين يتناول تعريف السابقة القضائية ووظيفتها وفوائدها وحجيتها وما جرى به العمل، وموقع السوابق في القضاء السعودي والقوانين الوضعية.",
    keywords: ["سوابق قضائية", "حجية السابقة", "القضاء السعودي", "ما جرى به العمل", "اجتهاد قضائي", "تمييز", "مبادئ قضائية"],
    sourceUrl: "/library/judicial-precedents-study.pdf",
    sourceLabel: "نسخة PDF مرفوعة إلى مكتبة المنصة",
    verified: false,
  },
  {
    id: "moj-25921",
    title: "صرف التعويض عند اختلاف المساحة بين الصك والطبيعة",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "وزارة العدل",
    hijriYear: "1404",
    reference: "12/73/ت",
    subject: "تعويضات",
    summary:
      "تعميم عدلي يتناول آلية التعامل مع صرف التعويض عند ظهور اختلاف بالزيادة أو النقص بين المساحة المدونة في الصك والمساحة الفعلية.",
    keywords: ["تعويض", "مساحة", "صك", "عقار"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "moj-26038",
    title: "تسجيل ملكية العقارات باسم الجمعيات الخيرية",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "وزارة العدل",
    hijriYear: "1421",
    reference: "13/ت/1670",
    subject: "المنح",
    summary:
      "تعميم يتعلق بتسجيل ملكية الأراضي أو العقارات باسم الجمعيات الخيرية عند انتقال الملكية إليها بالمنح أو بغيرها من الأسباب النظامية.",
    keywords: ["جمعيات خيرية", "تسجيل ملكية", "عقار", "منح"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "moj-26358",
    title: "نظر المعارضات على حجج الاستحكام",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "المجلس الأعلى للقضاء",
    hijriYear: "1410",
    reference: "8/ت/124",
    subject: "استحكام",
    summary:
      "تعميم إلحاقي بشأن نظر المعارضات على حجج الاستحكام ضمن إجراءات الحجة والاستفادة من قرار مجلس القضاء الأعلى المرتبط بها.",
    keywords: ["استحكام", "اعتراض", "حجة", "مجلس القضاء الأعلى"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "moj-26474",
    title: "تمييز الأحكام التي يقنع بها محامو البلديات",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "وزارة العدل",
    hijriYear: "1406",
    reference: "12/80/ت",
    subject: "أنظمة التمييز",
    summary:
      "تعميم يتناول مسألة تمييز الأحكام التي يقنع بها محامو البلديات في ضوء قرار الدائرة المختصة وما ورد بشأنه من دراسة.",
    keywords: ["تمييز", "أحكام", "بلديات", "محامون"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "moj-27131",
    title: "المسؤولية في حوادث السيارات وآثار العلاج الطبي",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "فتوى رسمية",
    hijriYear: "1392",
    reference: "109/1/ك",
    subject: "حوادث السيارات",
    summary:
      "تعميم بشأن الاستنارة بفتوى تتناول ما ينشأ عن حوادث السيارات وما قد يترتب على العلاج الطبي من أضرار أو وفيات.",
    keywords: ["حوادث سيارات", "مسؤولية", "تعويض", "علاج طبي"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "moj-27277",
    title: "مكان إقامة الدعوى واختصاص المحكمة",
    type: "تعميم وزاري",
    publishingAuthority: "وزارة العدل",
    originatingAuthority: "وزارة العدل",
    hijriYear: "1397",
    reference: "31/12/ت",
    subject: "الدعوى ومكان إقامتها",
    summary:
      "تعميم عدلي يتناول جواز رفع الدعوى أمام المحكمة التي يقع في نطاق اختصاصها المكان المرتبط بالدعوى وفق ما ورد في المصدر.",
    keywords: ["دعوى", "اختصاص مكاني", "محكمة", "إجراءات"],
    sourceUrl: mojCircularsUrl,
    sourceLabel: "بوابة التعاميم — وزارة العدل",
    verified: true,
  },
  {
    id: "bog-admin-1402-1426",
    title: "مجموعة الأحكام والمبادئ الإدارية للأعوام 1402–1426هـ",
    type: "مدونة قضائية",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1402–1426",
    reference: "مجموعة إدارية",
    subject: "قضاء إداري",
    summary:
      "مجموعة رسمية منشورة من ديوان المظالم تضم أحكامًا ومبادئ إدارية صادرة خلال الأعوام من 1402هـ إلى 1426هـ.",
    keywords: ["إداري", "ديوان المظالم", "مبادئ قضائية", "أحكام"],
    sourceUrl:
      "https://www.bog.gov.sa/knowledge-center/JudicialBlogs/AA1402-1426/Pages/default.aspx",
    sourceLabel: "مجموعات الأحكام القضائية — ديوان المظالم",
    verified: true,
  },
  {
    id: "bog-commercial-1408-1423",
    title: "مجموعة الأحكام والمبادئ التجارية للأعوام 1408–1423هـ",
    type: "مدونة قضائية",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1408–1423",
    reference: "مجموعة تجارية",
    subject: "قضاء تجاري",
    summary:
      "مجموعة رسمية للأحكام والمبادئ التجارية المنشورة عن الفترة من 1408هـ إلى 1423هـ ضمن مركز المعرفة بديوان المظالم.",
    keywords: ["تجاري", "شركات", "عقود", "ديوان المظالم"],
    sourceUrl:
      "https://www.bog.gov.sa/knowledge-center/JudicialBlogs/1408-1423/Pages/default.aspx",
    sourceLabel: "مجموعات الأحكام القضائية — ديوان المظالم",
    verified: true,
  },
  {
    id: "bog-1434",
    title: "مجموعة الأحكام والمبادئ القضائية لعام 1434هـ",
    type: "مجموعة أحكام",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1434",
    reference: "إصدار 1434هـ",
    subject: "أحكام ومبادئ",
    summary:
      "إصدار سنوي رسمي يضم مجموعات الأحكام والمبادئ القضائية المنشورة لعام 1434هـ.",
    keywords: ["1434", "أحكام", "مبادئ", "ديوان المظالم"],
    sourceUrl:
      "https://www.bog.gov.sa/knowledge-center/JudicialBlogs/1434/Pages/default.aspx",
    sourceLabel: "مجموعات الأحكام القضائية — ديوان المظالم",
    verified: true,
  },
  {
    id: "bog-1440",
    title: "مجموعة الأحكام الإدارية لعام 1440هـ",
    type: "مجموعة أحكام",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1440",
    reference: "إصدار 1440هـ",
    subject: "قضاء إداري",
    summary:
      "مجموعة الأحكام الإدارية المنشورة رسميًا لعام 1440هـ ضمن مركز المعرفة بديوان المظالم.",
    keywords: ["1440", "إداري", "أحكام", "ديوان المظالم"],
    sourceUrl:
      "https://www.bog.gov.sa/knowledge-center/JudicialBlogs/1440/Pages/default.aspx",
    sourceLabel: "مجموعات الأحكام القضائية — ديوان المظالم",
    verified: true,
  },
  {
    id: "bog-1441",
    title: "مجموعة الأحكام الإدارية لعام 1441هـ",
    type: "مجموعة أحكام",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1441",
    reference: "إصدار 1441هـ",
    subject: "قضاء إداري",
    summary:
      "إصدار مدرج في الفهرس الرسمي لمجموعات الأحكام القضائية، ويختص بالأحكام الإدارية المنشورة لعام 1441هـ.",
    keywords: ["1441", "إداري", "أحكام", "قضاء"],
    sourceUrl: bogCollectionsUrl,
    sourceLabel: "الفهرس الرسمي — ديوان المظالم",
    verified: true,
  },
  {
    id: "bog-1442",
    title: "مجموعة الأحكام الإدارية لعام 1442هـ",
    type: "مجموعة أحكام",
    publishingAuthority: "ديوان المظالم",
    originatingAuthority: "ديوان المظالم",
    hijriYear: "1442",
    reference: "إصدار 1442هـ",
    subject: "قضاء إداري",
    summary:
      "إصدار مدرج في الفهرس الرسمي لمجموعات الأحكام القضائية، ويختص بالأحكام الإدارية المنشورة لعام 1442هـ.",
    keywords: ["1442", "إداري", "أحكام", "قضاء"],
    sourceUrl: bogCollectionsUrl,
    sourceLabel: "الفهرس الرسمي — ديوان المظالم",
    verified: true,
  },
];

const volumeMetadata = [
  { volume: 3, subject: "التعويض والضمان والأمانات", keywords: ["تعويض", "ضمان", "سرقة", "احتيال", "خيانة أمانة", "بيع"] },
  { volume: 4, subject: "القروض والديون والإعسار", keywords: ["قرض", "دين", "إعسار", "حجر", "سداد", "يمين"] },
  { volume: 6, subject: "الحيازة والوديعة والإجارة", keywords: ["وضع يد", "وديعة", "أمانة", "إجارة", "إخلاء", "استرداد حيازة"] },
  { volume: 7, subject: "الإجارة والعقارات المؤجرة", keywords: ["إجارة", "إخلاء عقار", "وقف", "إيجار منتهٍ بالتمليك", "فسخ إيجار"] },
  { volume: 8, subject: "المقاولات والجعالة والأتعاب", keywords: ["مقاولة", "تصميم", "جعالة", "سمسرة", "أتعاب محاماة", "شفعة"] },
  { volume: 9, subject: "الأوقاف والتركات", keywords: ["وقف", "ناظر وقف", "غلة", "تركة", "قسمة", "ورثة"] },
  { volume: 10, subject: "الحوادث المرورية وفسخ النكاح", keywords: ["حادث مروري", "أرش إصابة", "تلف مركبة", "فسخ نكاح", "نفقة", "شقاق"] },
  { volume: 12, subject: "النفقة والسكن الزوجي", keywords: ["نفقة زوجة", "نفقة أولاد", "نفقة ماضية", "حمل", "عدة", "سكن", "نشوز"] },
  { volume: 14, subject: "الزنا والخلوة والابتزاز", keywords: ["زنا", "خلوة", "ابتزاز", "تهديد", "جرائم معلوماتية", "درء الحدود"] },
  { volume: 15, subject: "قضايا الآداب والتحرش والقذف", keywords: ["تحرش", "قذف", "سب", "تهديد", "تخبيب", "خلوة"] },
  { volume: 16, subject: "المسكرات", keywords: ["مسكر", "قيادة تحت التأثير", "حد المسكر", "تصنيع", "ترويج", "مقاومة رجال الأمن"] },
  { volume: 18, subject: "المخدرات والترويج", keywords: ["مخدرات", "أمفيتامين", "حشيش", "ترويج", "قات", "مصادرة", "منع من السفر"] },
  { volume: 19, subject: "المخدرات والتعاطي", keywords: ["مخدرات", "حشيش", "حبوب منبهة", "تعاطي", "ترويج", "حد المسكر"] },
  { volume: 20, subject: "المخدرات والعصابات المنظمة", keywords: ["مخدرات", "كوكايين", "هيروين", "عصابة منظمة", "تستر", "إبعاد"] },
  { volume: 21, subject: "المخدرات والتهريب", keywords: ["مخدرات", "ترامادول", "أفيون", "هيروين", "قات", "تهريب", "إدخال للسجن"] },
  { volume: 22, subject: "المخدرات والاتجار بالأشخاص", keywords: ["مخدرات", "حشيش", "حبوب محظورة", "مسكر", "منع من السفر", "اتجار بالأشخاص"] },
  { volume: 23, subject: "الاعتداء والإصابات والعنف الأسري", keywords: ["اعتداء", "مضاربة", "إصابات", "تقرير طبي", "عنف أسري", "ضرب", "قذف"] },
  { volume: 24, subject: "التزوير والجرائم المعلوماتية", keywords: ["تزوير", "جريمة معلوماتية", "دخول غير مشروع", "قذف", "قضايا أمنية", "إساءة للوالدين"] },
  { volume: 25, subject: "السرقة وشروط الحد", keywords: ["سرقة", "حد السرقة", "درء الحد", "شبهة", "اعتراف", "إنكار", "قرائن"] },
  { volume: 26, subject: "السرقة والاختلاس", keywords: ["سرقة", "محاولة سرقة", "صراف آلي", "أسلاك", "اختلاس", "تعويض", "حق خاص"] },
  { volume: 27, subject: "خيانة الأمانة والحرابة والخطف", keywords: ["خيانة أمانة", "اختلاس", "حرابة", "خطف", "إكراه", "قرائن"] },
  { volume: 28, subject: "الاختصاص والإجراءات والتحكيم", keywords: ["اختصاص ولائي", "اختصاص نوعي", "اختصاص مكاني", "تنازع", "تحكيم", "صفة", "وقف نظر"] },
  { volume: 29, type: "مدونة قضائية", subject: "كشاف الأسانيد الشرعية والنظامية", keywords: ["آيات", "أحاديث", "قواعد فقهية", "أقوال العلماء", "أنظمة", "تعليمات", "أسانيد"] },
  { volume: 30, type: "مدونة قضائية", subject: "كشاف موضوعات القضايا للمجلدات 1-28", keywords: ["كشاف موضوعي", "فهرس أحكام", "تصنيف القضايا", "ملخص القضية", "رقم الصفحة"] },
] as const;

const volumeDocuments: LegalDocument[] = volumeMetadata.map((item) => ({
  id: `library-moj-1434-volume-${item.volume}`,
  title: `مجموعة الأحكام القضائية لعام 1434هـ - المجلد ${item.volume}`,
  type: "type" in item ? item.type : "مجموعة أحكام",
  publishingAuthority: "وزارة العدل",
  originatingAuthority: "المحاكم العامة والجزائية",
  hijriYear: "1434",
  reference: `المجلد ${item.volume}`,
  subject: item.subject,
  summary: item.volume === 29
    ? "كشاف جامع للمستندات والأسانيد الشرعية والنظامية المرتبة موضوعيًا، ويضم الآيات والأحاديث والقواعد الفقهية وأقوال العلماء والأنظمة والتعليمات المستند إليها في المجموعة."
    : item.volume === 30
      ? "الكشاف الموضوعي لمجموعة الأحكام القضائية؛ يربط تصنيف القضية بملخص موضوعها ورقم الصفحة داخل مجلدات المجموعة من 1 إلى 28."
      : `مجلد من إصدار مركز البحوث بوزارة العدل المنشور عام 1436هـ، مفهرس على مستوى الأحكام الفردية ويغطي: ${item.subject}.`,
  keywords: [...item.keywords, "مجموعة الأحكام القضائية", "وزارة العدل"],
  sourceUrl: `/library/moj-judgments-1434-volume-${item.volume}.pdf`,
  sourceLabel: "نسخة PDF مرفوعة إلى مكتبة المنصة",
  verified: false,
  granularity: "document",
  searchText: referenceText[String(item.volume) as keyof typeof referenceText],
}));

const caseDocuments: LegalDocument[] = caseIndex.map((item) => ({
  id: `case-${item.id}`,
  title: item.title,
  type: "حكم قضائي",
  publishingAuthority: "وزارة العدل",
  originatingAuthority: "المحاكم العامة والجزائية",
  hijriYear: "1434",
  reference: item.deedNumber
    ? `صك ${item.deedNumber}`
    : item.lawsuitNumber
      ? `دعوى ${item.lawsuitNumber}`
      : `المجلد ${item.volume} - ص ${item.pdfPage}`,
  subject: item.title.split(" - ")[0].slice(0, 110),
  summary: item.title,
  keywords: [
    "حكم قضائي",
    `المجلد ${item.volume}`,
    ...(item.deedNumber ? [`صك ${item.deedNumber}`] : []),
    ...(item.lawsuitNumber ? [`دعوى ${item.lawsuitNumber}`] : []),
  ],
  sourceUrl: item.archive?.preservedOriginalPages
    ? `/api/cases/${item.id}`
    : `/library/${item.sourceFile}#page=${item.pdfPage}`,
  sourceLabel: `مجموعة الأحكام القضائية 1434هـ - المجلد ${item.volume}`,
  verified: false,
  searchText: item.searchText,
  granularity: "case",
}));

const ipCaseDocuments: LegalDocument[] = [
  {
    id: "case-ip-4530226536",
    title: "عدم قبول الطعن على تسجيل علامة KLEENZ لفوات المدة",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بالرياض",
    hijriYear: "1445",
    reference: "الحكم 4530226536",
    subject: "الطعن على قرار تسجيل علامة تجارية",
    summary: "عدم قبول الدعوى شكلًا لرفع الطعن بعد انقضاء مدة الثلاثين يومًا المقررة نظامًا.",
    keywords: ["KLEENZ", "KLEENEX", "علامة تجارية", "فوات المدة", "عدم قبول", "الهيئة السعودية للملكية الفكرية"],
    sourceUrl: "/api/cases/case-ip-4530226536",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 2",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530301286",
    title: "التعويض عن نشر صورة فوتوغرافية دون إذن صاحبها",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بالرياض",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530301286",
    subject: "حقوق المؤلف والتعويض عن نشر الصور",
    summary: "ثبوت الاعتداء على صورة فوتوغرافية، وإلزام المدعى عليها بإزالة الاعتداء وتعويض صاحب الصورة بمبلغ عشرة آلاف ريال.",
    keywords: ["حقوق المؤلف", "صورة فوتوغرافية", "نشر دون إذن", "تعويض", "إزالة الاعتداء", "10000"],
    sourceUrl: "/api/cases/case-ip-4530301286",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 5",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530360213",
    title: "عدم قبول دعوى شطب علامة Lale Thermos لرفعها قبل أوانها",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بالرياض",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530360213",
    subject: "شطب العلامة التجارية وسبق الفصل",
    summary: "عدم قبول دعوى الشطب لوجود دعوى سابقة على العلامة ذاتها وانعدام محل يمكن نظره قضاءً.",
    keywords: ["THERMOS", "شطب علامة", "سبق الفصل", "رفع قبل الأوان", "عدم قبول"],
    sourceUrl: "/api/cases/case-ip-4530360213",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 7",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530405408",
    title: "إدانة حيازة وعرض منتجات تحمل علامات مقلدة",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بجدة",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530405408",
    subject: "تقليد العلامات التجارية",
    summary: "إدانة المدعى عليه بحيازة وعرض وبيع منتجات تحمل علامات تجارية مقلدة والحكم بالغرامة.",
    keywords: ["علامة مقلدة", "نايك", "أديداس", "حيازة", "عرض", "بيع", "غرامة"],
    sourceUrl: "/api/cases/case-ip-4530405408",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 9",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530406780",
    title: "إدانة بيع منتجات مقلدة مع المصادرة والإتلاف",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بجدة",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530406780",
    subject: "بيع منتجات تحمل علامة تجارية مقلدة",
    summary: "إدانة صاحب المنشأة ببيع وعرض وحيازة منتجات مقلدة، مع الغرامة ومصادرة المضبوطات وإتلافها.",
    keywords: ["علامة مقلدة", "مصادرة", "إتلاف", "منتجات مقلدة", "غرامة"],
    sourceUrl: "/api/cases/case-ip-4530406780",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 11",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530329147",
    title: "إدانة بيع نظارات تحمل علامات تجارية مقلدة",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بجدة",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530329147",
    subject: "تقليد علامات النظارات التجارية",
    summary: "إدانة صاحبة المنشأة ببيع وعرض وحيازة نظارات تحمل علامات مقلدة، مع الغرامة والمصادرة والإتلاف.",
    keywords: ["نظارات مقلدة", "راي بان", "مونت بلانك", "مصادرة", "إتلاف", "غرامة"],
    sourceUrl: "/api/cases/case-ip-4530329147",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 13",
    verified: false,
    granularity: "case",
  },
  {
    id: "case-ip-4530253532",
    title: "رفض دعوى إلغاء قرار تسجيل علامة لانتفاء التشابه المضلل",
    type: "حكم قضائي",
    publishingAuthority: "إعداد عمر صالح الشهري",
    originatingAuthority: "المحكمة التجارية بالرياض",
    hijriYear: "1445",
    reference: "الحكم الابتدائي 4530253532",
    subject: "التشابه بين العلامات التجارية",
    summary: "رفض الدعوى بعد انتهاء الدائرة إلى عدم وجود تشابه يوهم المستهلكين أو يشكل اعتداءً على علامة المدعية.",
    keywords: ["علامة تجارية", "تشابه مضلل", "إلغاء قرار", "رفض الدعوى", "مونسـتر إنرجي"],
    sourceUrl: "/api/cases/case-ip-4530253532",
    sourceLabel: "تجميع أحكام الملكية الفكرية — ص 15",
    verified: false,
    granularity: "case",
  },
];

const uncitralCaseDocuments: LegalDocument[] = specializedCaseIndex
  .filter((item) => item.id.startsWith("uncitral-"))
  .map((item) => ({
    id: item.id,
    title: item.title,
    type: "سابقة قضائية",
    publishingAuthority: "لجنة الأمم المتحدة للقانون التجاري الدولي (الأونسيترال)",
    originatingAuthority: "محاكم دولية مختارة ضمن نظام كلاوت",
    hijriYear: "2024م",
    reference: `القضية ${item.reference}`,
    subject: "التحكيم التجاري الدولي",
    summary: `${item.title} ضمن السوابق القضائية المستندة إلى نصوص الأونسيترال.`,
    keywords: ["أونسيترال", "كلاوت", "تحكيم دولي", item.reference],
    sourceUrl: `/api/cases/${item.id}`,
    sourceLabel: "وثيقة أممية عربية",
    verified: false,
    granularity: "case",
  }));

const principleDocuments: LegalDocument[] = snippetIndex
  .filter((item) => item.documentType === "مبدأ قضائي")
  .map((item) => ({
    id: item.id,
    title: item.title,
    type: "مبدأ قضائي",
    publishingAuthority: "وزارة العدل — مركز البحوث",
    originatingAuthority: "الجهات القضائية العليا والمحكمة العليا",
    hijriYear: "1391–1437",
    reference: `المبدأ ${item.reference}`,
    subject: "مبادئ قضائية عليا",
    summary: "مبدأ قضائي مفصول من الإصدار الرسمي مع الاحتفاظ بتصميم صفحته الأصلية.",
    keywords: ["مبدأ قضائي", "المحكمة العليا", "مجلس القضاء الأعلى", item.reference],
    sourceUrl: `/api/cases/${item.id}`,
    sourceLabel: "مبادئ وقرارات الجهات القضائية العليا — وزارة العدل",
    verified: true,
    searchText: item.searchText,
    granularity: "case",
  }));

const administrativePrecedentDocuments: LegalDocument[] = snippetIndex
  .filter((item) => item.documentType === "سابقة قضائية")
  .map((item) => ({
    id: item.id,
    title: item.title,
    type: "سابقة قضائية",
    publishingAuthority: "ديوان المظالم — مكتب الشؤون الفنية",
    originatingAuthority: "محاكم ديوان المظالم الإدارية",
    hijriYear: "1402–1436",
    reference: item.reference,
    subject: "سوابق القضاء الإداري",
    summary: "سابقة قضائية مفصولة من المدونة الرسمية مع الاحتفاظ بتصميمها ومرجعها الأصليين.",
    keywords: ["سابقة قضائية", "ديوان المظالم", "قضاء إداري", item.reference],
    sourceUrl: `/api/cases/${item.id}`,
    sourceLabel: "السوابق القضائية لأحكام ديوان المظالم الإدارية",
    verified: true,
    searchText: item.searchText,
    granularity: "case",
  }));

const commercialPrecedentDocuments: LegalDocument[] = specializedCaseIndex
  .filter((item) => item.id.startsWith("commercial-precedent-"))
  .map((item) => ({
    id: item.id,
    title: item.title,
    type: "سابقة قضائية",
    publishingAuthority: "الجمعية الفقهية السعودية",
    originatingAuthority: "دراسة تأصيلية تطبيقية للأحكام التجارية",
    hijriYear: "1444",
    reference: `السجل ${item.reference}`,
    subject: "عقود المعاوضات التجارية",
    summary: "سابقة تجارية مفصولة من المرجع التطبيقي مع الاحتفاظ بصفحاتها الأصلية.",
    keywords: ["سابقة قضائية", "عقود تجارية", "معاوضات", item.reference],
    sourceUrl: `/api/cases/${item.id}`,
    sourceLabel: "السوابق القضائية في عقود المعاوضات التجارية",
    verified: false,
    granularity: "case",
  }));

export const indexedCaseCount = caseDocuments.length + ipCaseDocuments.length;
export const indexedPrincipleCount = principleDocuments.length;
export const indexedPrecedentCount = administrativePrecedentDocuments.length + commercialPrecedentDocuments.length + uncitralCaseDocuments.length;
export const privateLibraryFileCount = 35;

export const legalDocuments: LegalDocument[] = [
  ...baseLegalDocuments,
  ...volumeDocuments,
  ...ipCaseDocuments,
  ...uncitralCaseDocuments,
  ...principleDocuments,
  ...administrativePrecedentDocuments,
  ...commercialPrecedentDocuments,
  ...caseDocuments,
];

export const indexedCircularCount = legalDocuments.filter((item) => item.type.startsWith("تعميم")).length;
export const indexedDecisionCount = legalDocuments.filter((item) => item.type.includes("قرار")).length;

export const sourceRegistry = [
  {
    name: "بوابة التعاميم العدلية",
    authority: "وزارة العدل",
    description: "فهرس رسمي للتعاميم مع البحث بالموضوع والفترة ورقم التعميم.",
    url: mojCircularsUrl,
    status: "متصل",
    records: 6,
  },
  {
    name: "مجموعات الأحكام القضائية",
    authority: "ديوان المظالم",
    description: "مدونات ومجموعات سنوية للأحكام والمبادئ الإدارية والتجارية والجزائية.",
    url: bogCollectionsUrl,
    status: "متصل",
    records: 6,
  },
  {
    name: "تعاميم المجلس الأعلى للقضاء",
    authority: "المجلس الأعلى للقضاء",
    description: "تعاميم وقواعد قضائية مستقلة عن تعاميم وزارة العدل، تُصنف بحسب ناشرها وأصلها.",
    url: scjCircularsUrl,
    status: "قيد الربط",
    records: 0,
  },
];
