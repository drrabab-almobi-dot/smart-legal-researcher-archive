import {
  archiveBytes,
  authenticatedEmail,
  getCollectorState,
  setCollectorState,
} from "@/lib/archive-storage";

export const dynamic = "force-dynamic";

const CHANNEL_USERNAME = "robiai33";
const STATE_KEY = `telegram_public_before_${CHANNEL_USERNAME}`;
const MAX_PAGES_PER_RUN = 3;

type PublicPost = {
  id: number;
  text: string;
  date: string | null;
  sourceUrl: string;
  attachments: Array<{ url: string; fileName: string }>;
};

function decodeHtml(value: string) {
  return value
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;|&#34;/gi, '"')
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_, code: string) => String.fromCodePoint(Number(code)))
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function parseDirectHtml(html: string): PublicPost[] {
  const marker = new RegExp(`data-post=["']${CHANNEL_USERNAME}/(\\d+)["']`, "gi");
  const matches = Array.from(html.matchAll(marker));
  return matches.map((match, index) => {
    const id = Number(match[1]);
    const start = match.index ?? 0;
    const end = matches[index + 1]?.index ?? html.length;
    const block = html.slice(start, end);
    const textHtml = block.match(/tgme_widget_message_text[^>]*>([\s\S]*?)<\/div>/i)?.[1] ?? "";
    const documentNames = Array.from(
      block.matchAll(/tgme_widget_message_document_title[^>]*>([\s\S]*?)<\/div>/gi),
      (item) => decodeHtml(item[1]),
    ).filter(Boolean);
    const date = block.match(/datetime=["']([^"']+)["']/i)?.[1] ?? null;
    const mediaUrls = Array.from(
      block.matchAll(/(?:background-image\s*:\s*url\(|href=)["']?(https:\/\/[^"')\s<>]+)/gi),
      (item) => decodeHtml(item[1]),
    ).filter((url) => /(?:cdn\d*\.telesco\.pe|\.pdf(?:\?|$)|\.docx?(?:\?|$)|\.png(?:\?|$)|\.jpe?g(?:\?|$)|\.tiff?(?:\?|$))/i.test(url));
    const attachments = Array.from(new Set(mediaUrls)).slice(0, 8).map((url, mediaIndex) => ({
      url,
      fileName: documentNames[mediaIndex] || `telegram-${id}-media-${mediaIndex + 1}`,
    }));
    const text = [decodeHtml(textHtml), ...documentNames.map((name) => `مرفق: ${name}`)]
      .filter(Boolean)
      .join("\n\n");
    return { id, text, date, sourceUrl: `https://t.me/${CHANNEL_USERNAME}/${id}`, attachments };
  });
}

function parseReaderMarkdown(markdown: string): PublicPost[] {
  const marker = new RegExp(`\\[\\]\\(https?://t\\.me/${CHANNEL_USERNAME}/(\\d+)\\)`, "gi");
  const matches = Array.from(markdown.matchAll(marker));
  return matches.map((match, index) => {
    const id = Number(match[1]);
    const start = (match.index ?? 0) + match[0].length;
    const end = matches[index + 1]?.index ?? markdown.length;
    let text = markdown.slice(start, end)
      .replace(/\[_?!\[Image[^\n]+\n?/g, " ")
      .replace(/\[([^\]]+)\]\((?:https?:\/\/)?t\.me\/[^)]+\)/g, "$1")
      .replace(/^(?:July|August|September) \d{1,2}$/gim, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    const permalink = `[t.me/${CHANNEL_USERNAME}/${id}](https://t.me/${CHANNEL_USERNAME}/${id})`;
    text = text.replace(permalink, "").trim();
    return { id, text, date: null, sourceUrl: `https://t.me/${CHANNEL_USERNAME}/${id}`, attachments: [] };
  });
}

function extensionForMime(mimeType: string) {
  const extensions: Record<string, string> = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/tiff": "tiff",
  };
  return extensions[mimeType.split(";")[0].trim()] || null;
}

async function archivePostAttachments(post: PublicPost, uploadedBy: string) {
  let archived = 0;
  let duplicates = 0;
  const errors: string[] = [];
  for (const [index, attachment] of post.attachments.entries()) {
    try {
      const response = await fetch(attachment.url, {
        headers: { "user-agent": "Mozilla/5.0 (compatible; LegalArchive/1.0)" },
      });
      if (!response.ok) throw new Error("تعذر تنزيل المرفق العام.");
      const contentType = response.headers.get("content-type") || "";
      const extension = extensionForMime(contentType);
      if (!extension) continue;
      const bytes = await response.arrayBuffer();
      if (!bytes.byteLength || bytes.byteLength > 25 * 1024 * 1024) continue;
      const suppliedName = attachment.fileName.includes(".")
        ? attachment.fileName
        : `${attachment.fileName}.${extension}`;
      const result = await archiveBytes({
        bytes,
        fileName: suppliedName || `telegram-${post.id}-media-${index + 1}.${extension}`,
        relativePath: `telegram/${CHANNEL_USERNAME}/${post.id}/media-${index + 1}.${extension}`,
        mimeType: contentType,
        sourceKind: "telegram",
        sourceLabel: `مرفق من قناة تيليجرام العامة: @${CHANNEL_USERNAME}`,
        uploadedBy,
        telegramChatId: `@${CHANNEL_USERNAME}`,
        telegramMessageId: String(post.id),
      });
      if (result.duplicate) duplicates += 1;
      else archived += 1;
    } catch (error) {
      errors.push(error instanceof Error ? error.message : "فشل حفظ المرفق.");
    }
  }
  return { archived, duplicates, errors };
}

async function fetchPage(before?: number | null) {
  const query = before ? `?before=${before}` : "";
  const directUrl = `https://t.me/s/${CHANNEL_USERNAME}${query}`;
  try {
    const response = await fetch(directUrl, {
      headers: { "user-agent": "Mozilla/5.0 (compatible; LegalArchive/1.0)" },
    });
    if (response.ok) {
      const html = await response.text();
      const posts = parseDirectHtml(html);
      if (posts.length) return posts;
    }
  } catch {
    // Free public reader fallback when Telegram blocks the hosting datacenter.
  }

  const readerUrl = `https://r.jina.ai/http://t.me/s/${CHANNEL_USERNAME}${query}`;
  const response = await fetch(readerUrl, { headers: { accept: "text/plain" } });
  if (!response.ok) throw new Error("تعذر قراءة القناة العامة في الوقت الحالي.");
  return parseReaderMarkdown(await response.text());
}

function safeSubject(text: string, id: number) {
  const firstLine = text
    .split("\n")
    .map((line) => line.replace(/[*_#`📍⚖️📌]/g, "").trim())
    .find(Boolean);
  const subject = (firstLine || "مادة قانونية")
    .replace(/[\\/:*?"<>|]/g, "-")
    .replace(/\s+/g, " ")
    .slice(0, 70);
  return `تيليجرام-${id}-${subject}.md`;
}

function postMarkdown(post: PublicPost) {
  return [
    `# ${safeSubject(post.text, post.id).replace(/^تيليجرام-\d+-|\.md$/g, "")}`,
    "",
    post.text || "مادة قانونية مرفقة في المنشور.",
    "",
    "## بيانات المصدر",
    "",
    `- القناة: @${CHANNEL_USERNAME}`,
    `- رقم المنشور: ${post.id}`,
    `- تاريخ النشر: ${post.date || "غير متاح في صفحة القراءة العامة"}`,
    `- رابط الأصل: ${post.sourceUrl}`,
    "",
    "> مادة مجمعة من قناة عامة وتحتاج مراجعة المصدر الرسمي قبل الاعتماد القانوني.",
  ].join("\n");
}

export async function GET(request: Request) {
  return Response.json({ error: "تم تعطيل هذا المصدر؛ الأرشيف يعتمد المصادر الرسمية والملفات المرفوعة فقط." }, { status: 410 });
  if (!authenticatedEmail(request)) {
    return Response.json({ error: "يلزم تسجيل الدخول لفحص القناة." }, { status: 401 });
  }
  const cursor = await getCollectorState(STATE_KEY).catch(() => null);
  return Response.json({
    configured: true,
    channel: `@${CHANNEL_USERNAME}`,
    hasSynced: Boolean(cursor),
    mode: "public",
  });
}

export async function POST(request: Request) {
  return Response.json({ error: "تم تعطيل هذا المصدر؛ الأرشيف يعتمد المصادر الرسمية والملفات المرفوعة فقط." }, { status: 410 });
  const uploadedBy = authenticatedEmail(request);
  if (!uploadedBy) {
    return Response.json({ error: "يلزم تسجيل الدخول لتشغيل الأرشفة." }, { status: 401 });
  }

  try {
    const savedCursor = Number(await getCollectorState(STATE_KEY));
    let before = Number.isFinite(savedCursor) && savedCursor > 1 ? savedCursor : null;
    let archived = 0;
    let duplicates = 0;
    let ignored = 0;
    let pages = 0;
    let reachedBeginning = false;
    const errors: string[] = [];

    while (pages < MAX_PAGES_PER_RUN && !reachedBeginning) {
      const posts = await fetchPage(before);
      if (!posts.length) {
        reachedBeginning = true;
        break;
      }

      const uniquePosts = Array.from(new Map(posts.map((post) => [post.id, post])).values())
        .filter((post) => post.id > 0)
        .sort((a, b) => b.id - a.id);
      if (!uniquePosts.length) {
        reachedBeginning = true;
        break;
      }

      for (const post of uniquePosts) {
        try {
          const markdown = postMarkdown(post);
          const bytes = new TextEncoder().encode(markdown).buffer;
          const result = await archiveBytes({
            bytes,
            fileName: safeSubject(post.text, post.id),
            relativePath: `telegram/${CHANNEL_USERNAME}/${post.id}.md`,
            mimeType: "text/markdown; charset=utf-8",
            sourceKind: "telegram",
            sourceLabel: `قناة تيليجرام عامة: @${CHANNEL_USERNAME}`,
            uploadedBy,
            telegramChatId: `@${CHANNEL_USERNAME}`,
            telegramMessageId: String(post.id),
          });
          if (result.duplicate) duplicates += 1;
          else archived += 1;
          const attachmentSummary = await archivePostAttachments(post, uploadedBy);
          archived += attachmentSummary.archived;
          duplicates += attachmentSummary.duplicates;
          errors.push(...attachmentSummary.errors.map((message) => `${post.id}: ${message}`));
        } catch (error) {
          errors.push(`${post.id}: ${error instanceof Error ? error.message : "فشل حفظ المنشور."}`);
        }
      }

      const nextBefore = Math.min(...uniquePosts.map((post) => post.id));
      if (before !== null && nextBefore >= before) {
        reachedBeginning = true;
      } else {
        before = nextBefore;
        await setCollectorState(STATE_KEY, String(nextBefore));
      }
      ignored += posts.length - uniquePosts.length;
      pages += 1;
    }

    return Response.json({
      configured: true,
      channel: `@${CHANNEL_USERNAME}`,
      summary: { archived, duplicates, ignored, errors: errors.length, pages, reachedBeginning },
      errors: errors.slice(0, 10),
    });
  } catch (error) {
    return Response.json(
      { error: error instanceof Error ? error.message : "تعذر تشغيل أرشفة القناة العامة." },
      { status: 502 },
    );
  }
}
