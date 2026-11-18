# Gemini queue admission without email

The existing Session API sends an operator email for every session creation;
email_run_video=false does not suppress that separate alert. This integration
uses the dedicated POST /v1/sessions/no-email endpoint and never falls back to
ordinary session creation. Both email_queue_alert and email_run_video are false.
The new endpoint uses the same FIFO, capability/lease, registration checks,
Home, validated trajectory path and Stop. Existing callers' notification defaults
and independent fault alerts are unchanged.

GeminiSessionAPI subclasses the canonical HttpSessionAPI. It checks the publicly
advertised session_create_no_email schema before transmitting identity, then
uses the unique endpoint. An old API returns404 before creating a session; even
a rollback between capability read and POST cannot fall back to sending email.
Canonical session capabilities and trajectory serialization remain untouched.
Ambiguous session-creation replies are not retried. Actual runner name/email are
private operational attribution; Model remains Gemini Robotics and execution mode
is separate. No anonymous or invented attribution is substituted.

Five zero-network tests use the actual canonical HTTP serializer for fixed
attribution, both false flags, unsupported/invalid schema zero-POST, rollback
no-fallback, ambiguous-POST no-retry and invalid identity zero-transport. The
private backend overlay adds the quiet route and explicit boolean policy, while
preserving other advertised schemas and all existing image layers/configuration.
Seven packaged ASGI tests use a Mock publisher with networking disabled; the old
image separately rejects the new route with zero queue/email calls. No real
queue or email was used to test this.

The backend extension is prepared, not yet activated. Gemini's new worker release
is not deployed while SSH access is pending. Its original model-key approval
remains valid, but Google credits and YAM1 source connectivity are unresolved.
Physical Run stays unavailable. This is a protocol/notification prerequisite,
not physical/model/task-scene/contact/timing or replay qualification.
