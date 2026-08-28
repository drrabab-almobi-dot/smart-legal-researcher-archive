const LEGAL_SYNONYMS: Record<string, string[]> = {
  تعويض: ["ضمان", "اضرار", "ضرر", "جبر الضرر"],
  اضرار: ["تعويض", "ضرر", "مسؤوليه"],
  اختصاص: ["ولايه", "اختصاص مكاني", "اختصاص نوعي", "مكان الدعوي"],
  استحكام: ["حجه استحكام", "تملك عقار", "اثبات ملكيه"],
  تجاري: ["تجاره", "شركات", "عقود تجاريه", "منازعه تجاريه"],
  اداري: ["قرار اداري", "ديوان المظالم", "جهه اداريه"],
  تنفيذ: ["سند تنفيذي", "قاضي التنفيذ", "محكمه التنفيذ"],
  اثبات: ["بينه", "قرينه", "شهاده", "اقرار"],
  فسخ: ["انهاء العقد", "انفساخ", "ابطال"],
  عقد: ["اتفاق", "التزام", "تعاقد"],
  دعوي: ["خصومه", "مدعي", "مدعي عليه"],
  تقادم: ["مرور الزمن", "عدم سماع الدعوي", "مده نظاميه"],
};

const STOP_WORDS = new Set([
  "في", "من", "الي", "على", "عن", "او", "و", "ما", "هل", "مع", "هذا", "هذه",
  "التي", "الذي", "كان", "تكون", "بشان", "حكم", "احكام",
]);

export function normalizeArabic(value: string) {
  return value
    .toLocaleLowerCase("ar")
    .replace(/[^\p{L}\p{N}\s/.-]/gu, " ")
    .replace(/[\u064B-\u065F\u0670]/g, "")
    .replace(/[إأآٱ]/g, "ا")
    .replace(/ى/g, "ي")
    .replace(/ؤ/g, "و")
    .replace(/ئ/g, "ي")
    .replace(/ء/g, "")
    .replace(/ة/g, "ه")
    .replace(/ـ/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function legalSearchTerms(query: string) {
  const normalized = normalizeArabic(query);
  const tokens = normalized
    .split(" ")
    .filter((token) => token.length > 2 && !STOP_WORDS.has(token));
  const expanded = new Set(tokens);
  for (const token of tokens) {
    for (const synonym of LEGAL_SYNONYMS[token] ?? []) expanded.add(normalizeArabic(synonym));
  }
  return {
    normalized,
    tokens,
    expanded: Array.from(expanded)
      .map(normalizeArabic)
      .filter((term) => term.length > 2)
      .slice(0, 16),
  };
}

function containsWholeTerm(field: string, term: string) {
  if (!field || !term) return false;
  const padded = ` ${field.replace(/[./-]+/g, " ").replace(/\s+/g, " ")} `;
  return padded.includes(` ${term.replace(/[./-]+/g, " ").replace(/\s+/g, " ")} `);
}

export function relevanceScore(fields: {
  title: string;
  reference?: string | null;
  subject?: string | null;
  keywords?: string[];
  summary?: string | null;
  fullText?: string | null;
}, query: string) {
  const { normalized, tokens, expanded } = legalSearchTerms(query);
  if (!normalized) return { score: 1, matchedTerms: [] as string[] };

  const title = normalizeArabic(fields.title);
  const reference = normalizeArabic(fields.reference ?? "");
  const subject = normalizeArabic(fields.subject ?? "");
  const keywords = normalizeArabic((fields.keywords ?? []).join(" "));
  const summary = normalizeArabic(fields.summary ?? "");
  const fullText = normalizeArabic(fields.fullText ?? "");
  let score = 0;
  const matched = new Set<string>();

  if (reference && containsWholeTerm(reference, normalized)) score += 140;
  if (containsWholeTerm(title, normalized)) score += 100;
  if (containsWholeTerm(subject, normalized)) score += 70;
  if (containsWholeTerm(keywords, normalized)) score += 55;
  if (containsWholeTerm(summary, normalized)) score += 30;
  if (containsWholeTerm(fullText, normalized)) score += 18;

  for (const token of tokens) {
    let tokenScore = 0;
    if (containsWholeTerm(reference, token)) tokenScore += 45;
    if (containsWholeTerm(title, token)) tokenScore += 30;
    if (containsWholeTerm(subject, token)) tokenScore += 22;
    if (containsWholeTerm(keywords, token)) tokenScore += 18;
    if (containsWholeTerm(summary, token)) tokenScore += 10;
    if (containsWholeTerm(fullText, token)) tokenScore += 5;
    if (tokenScore) matched.add(token);
    score += tokenScore;
  }

  for (const term of expanded) {
    if (tokens.includes(term)) continue;
    if (containsWholeTerm(`${title} ${subject} ${keywords} ${summary} ${fullText}`, term)) {
      score += 6;
      matched.add(term);
    }
  }

  if (tokens.length > 1 && tokens.every((token) =>
    containsWholeTerm(`${title} ${subject} ${keywords} ${summary} ${fullText}`, token))) score += 24;

  return { score, matchedTerms: Array.from(matched).slice(0, 6) };
}

export function textExcerpt(text: string | null | undefined, query: string, max = 240) {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  if (!clean) return null;
  const { tokens } = legalSearchTerms(query);
  const normalized = normalizeArabic(clean);
  const firstIndex = tokens
    .map((token) => normalized.indexOf(token))
    .filter((index) => index >= 0)
    .sort((a, b) => a - b)[0] ?? 0;
  const start = Math.max(0, firstIndex - 70);
  const excerpt = clean.slice(start, start + max);
  return `${start > 0 ? "…" : ""}${excerpt}${start + max < clean.length ? "…" : ""}`;
}
