CREATE TABLE physical_runs(id text PRIMARY KEY NOT NULL,owner text NOT NULL,instruction text NOT NULL,runner_name text NOT NULL,runner_email text NOT NULL,status text NOT NULL,stage text NOT NULL,created_at integer NOT NULL,updated_at integer NOT NULL,worker text,cancel_requested integer DEFAULT 0 NOT NULL,result text,assets text DEFAULT '[]' NOT NULL);
--> statement-breakpoint
CREATE TABLE physical_workers(id text PRIMARY KEY NOT NULL,heartbeat integer NOT NULL,detail text NOT NULL);
--> statement-breakpoint
CREATE UNIQUE INDEX physical_one_active ON physical_runs((1)) WHERE status IN ('queued','preparing','running','recording');
