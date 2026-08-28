ALTER TABLE `archive_files` ADD `granularity` text DEFAULT 'document' NOT NULL;--> statement-breakpoint
ALTER TABLE `legal_documents` ADD `granularity` text DEFAULT 'case' NOT NULL;--> statement-breakpoint
ALTER TABLE `legal_documents` ADD `specialty` text DEFAULT 'أخرى' NOT NULL;