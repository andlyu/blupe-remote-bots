# Queue several prompts to one model

Use **Add prompt** below the task composer, write each task separately, and submit once. The selected robot, provider/model, duration, reasoning, speed, system prompt and sharing settings apply to every prompt. The server runs them in order through normal admission; the tab can close while the batch continues. Settings controls the replay-email opt-in and recipient for every run.

Each prompt receives its own session, recording and private consent receipt. The status list shows each prompt and its state. Stop cancels the current run and remaining prompts. A normal run time limit advances to the next distinct submitted prompt, without retrying the timed-out task. A native safety stop or lost session connection ends the batch; new admission errors are reported with remaining prompts unstarted. Existing readiness, queue/lease, hardware limits, Stop and per-run budgets remain in force.

## Supported request

POST `/api/run` with the existing session cookie, Origin and runner CSRF token. Add `prompts` containing 2–10 strings, each 1–4,000 characters, at most16,000 characters combined, to the ordinary run payload. A single prompt continues to use the existing `prompt` field and path. The first prompt is admitted before a successful response; the rest are server-pending and join the normal queue in order. Credentials remain private in memory and are cleared from the batch when it ends. The batch itself does not send mail; each run uses the existing opted-in notification pipeline.

The response and owner-only `/api/status` include `prompt_batch` with its phase, current/total, per-prompt states and exact session/episode IDs as assigned. The hosted admission hook can reject a batch exceeding the remaining guest allowance before the first prompt starts. Every later prompt still goes through the existing funded/BYOK admission path and atomic per-run accounting.

A browser reload preserves a live batch on that server. A server restart ends it; queued motion is never silently reconstructed or retried. The durable per-run journal and replay/email receipts remain separate from this in-memory submission batch.

## Verification and scope

The user's November22 playground bug-fix and multi-prompt request, together with adopted AGENTS.md instructions, invokes the shared [authorization-by-use contract](../integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness). Existing user-selected models are preserved; this feature introduces no new model or policy. Test attribution is explicitly synthetic and no physical model run or identity submission was used for offline verification. The owner's no-email-send instruction takes precedence; message validation uses drafts and mock delivery.

- [x] Three real hosted MockSessionAPI sessions advance without browser polling and retain distinct identities and replay consent.
- [x] Owner/CSRF isolation, input limits, cancellation, eight concurrent Stops during provider preparation and eight late active events after an acknowledged Stop are covered.
- [x] Normal time limits move to the next distinct prompt; safety stops do not retry or start another.
- [x] Hosted guest batches use existing admission/accounting and reject insufficient allowance before starting.
- [x] Desktop and390×844 browser controls support adding/removing/renumbering prompts; no console errors observed.
- [ ] Final deployed physical batch and replay readiness verification: exact robot/model/prompts requested from the owner and pending.
- [ ] Live replay-email inbox delivery: no email is sent by the agent under the owner's standing rule.

Broader baseline limits are recorded in the private task report:11 hosted model/default/ASPIRE tests also fail with the pre-task hosted source. The stale five-second replay test now explicitly covers a non-YAM robot, with separate immediate-replay checks for both YAM stations. They are not evidence of this feature passing end to end on hardware.
