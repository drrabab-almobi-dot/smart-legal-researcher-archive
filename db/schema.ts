import { sql } from "drizzle-orm";
import { integer, sqliteTable, text, uniqueIndex } from "drizzle-orm/sqlite-core";

export const archiveFiles = sqliteTable(
  "archive_files",
  {
    id: text("id").primaryKey(),
    fileName: text("file_name").notNull(),
    relativePath: text("relative_path"),
    objectKey: text("object_key").notNull(),
    mimeType: text("mime_type").notNull(),
    sizeBytes: integer("size_bytes").notNull(),
    checksum: text("checksum").notNull(),
    searchText: text("search_text").notNull().default(""),
    sourceKind: text("source_kind").notNull(),
    sourceLabel: text("source_label").notNull(),
    granularity: text("granularity").notNull().default("document"),
    telegramChatId: text("telegram_chat_id"),
    telegramMessageId: text("telegram_message_id"),
    status: text("status").notNull().default("pending_indexing"),
    documentType: text("document_type").notNull().default("مدونة قضائية"),
    issuer: text("issuer"),
    publishingAuthority: text("publishing_authority"),
    originatingAuthority: text("originating_authority"),
    hijriYear: text("hijri_year"),
    referenceNo: text("reference_no"),
    subject: text("subject"),
    uploadedBy: text("uploaded_by").notNull(),
    createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
    indexedAt: text("indexed_at"),
  },
  (table) => [
    uniqueIndex("archive_files_checksum_unique").on(table.checksum),
    uniqueIndex("archive_files_object_key_unique").on(table.objectKey),
  ],
);

export const legalDocuments = sqliteTable("legal_documents", {
  id: text("id").primaryKey(),
  title: text("title").notNull(),
  documentType: text("document_type").notNull(),
  issuer: text("issuer"),
  publishingAuthority: text("publishing_authority"),
  originatingAuthority: text("originating_authority"),
  hijriYear: text("hijri_year"),
  referenceNo: text("reference_no"),
  subject: text("subject"),
  summary: text("summary").notNull().default(""),
  extractedText: text("extracted_text").notNull().default(""),
  textChecksum: text("text_checksum"),
  sourceKind: text("source_kind").notNull(),
  sourceUrl: text("source_url"),
  sourceLabel: text("source_label").notNull(),
  granularity: text("granularity").notNull().default("case"),
  specialty: text("specialty").notNull().default("أخرى"),
  archiveFileId: text("archive_file_id").references(() => archiveFiles.id),
  verified: integer("verified", { mode: "boolean" }).notNull().default(false),
  createdAt: text("created_at").notNull().default(sql`CURRENT_TIMESTAMP`),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
}, (table) => [
  uniqueIndex("legal_documents_text_checksum_unique").on(table.textChecksum),
]);

export const collectorState = sqliteTable("collector_state", {
  key: text("key").primaryKey(),
  value: text("value").notNull(),
  updatedAt: text("updated_at").notNull().default(sql`CURRENT_TIMESTAMP`),
});
