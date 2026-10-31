CREATE TABLE `runs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`skill` text NOT NULL,
	`instruction` text NOT NULL,
	`runner_name` text NOT NULL,
	`runner_email` text NOT NULL,
	`status` text NOT NULL,
	`stage` text NOT NULL,
	`created_at` integer NOT NULL,
	`updated_at` integer NOT NULL,
	`cancel_requested` integer DEFAULT 0 NOT NULL,
	`worker` text,
	`result` text,
	`assets` text DEFAULT '[]' NOT NULL
);
--> statement-breakpoint
CREATE TABLE `workers` (
	`id` text PRIMARY KEY NOT NULL,
	`heartbeat` integer NOT NULL,
	`detail` text NOT NULL
);
