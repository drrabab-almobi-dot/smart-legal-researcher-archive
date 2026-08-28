CREATE TABLE `archive_files` (
	`id` text PRIMARY KEY NOT NULL,
	`file_name` text NOT NULL,
	`relative_path` text,
	`object_key` text NOT NULL,
	`mime_type` text NOT NULL,
	`size_bytes` integer NOT NULL,
	`checksum` text NOT NULL,
	`source_kind` text NOT NULL,
	`source_label` text NOT NULL,
	`telegram_chat_id` text,
	`telegram_message_id` text,
	`status` text DEFAULT 'pending_indexing' NOT NULL,
	`document_type` text DEFAULT 'مدونة قضائية' NOT NULL,
	`issuer` text,
	`hijri_year` text,
	`reference_no` text,
	`subject` text,
	`uploaded_by` text NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`indexed_at` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `archive_files_checksum_unique` ON `archive_files` (`checksum`);--> statement-breakpoint
CREATE UNIQUE INDEX `archive_files_object_key_unique` ON `archive_files` (`object_key`);--> statement-breakpoint
CREATE TABLE `collector_state` (
	`key` text PRIMARY KEY NOT NULL,
	`value` text NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL
);
--> statement-breakpoint
CREATE TABLE `legal_documents` (
	`id` text PRIMARY KEY NOT NULL,
	`title` text NOT NULL,
	`document_type` text NOT NULL,
	`issuer` text,
	`hijri_year` text,
	`reference_no` text,
	`subject` text,
	`summary` text DEFAULT '' NOT NULL,
	`extracted_text` text DEFAULT '' NOT NULL,
	`source_kind` text NOT NULL,
	`source_url` text,
	`source_label` text NOT NULL,
	`archive_file_id` text,
	`verified` integer DEFAULT false NOT NULL,
	`created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	`updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
	FOREIGN KEY (`archive_file_id`) REFERENCES `archive_files`(`id`) ON UPDATE no action ON DELETE no action
);
