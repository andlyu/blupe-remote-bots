# Run-library data conversation

The library shows **Discuss the data** by default beside Cloud or Table.
**Close** hides the read-only conversation; **Ask about these runs** reopens it. The baseline is the complete public collection across robots.
Current robot, model/search filters, box selection and opened replay are separate
context. Changing them preserves the conversation. The scope selector offers an
explicit filtered/box or opened-replay focus. Each answer retains its own scope,
counts, denominator, evidence sample size and actual model identifier.

Data chat has no name/email prompt or harness enrollment. It is separate from
robot execution and queue attribution.

The server reloads authoritative public archive metadata and human assessments,
merges any available public pre-publication receipts with archive rows taking
precedence, then applies the same search/filter implementation as the library. It separately
computes all-collection, current-library and requested-focus aggregates. A box
must contain existing IDs that match the current robot/filters; an empty box stays
empty. Opened replays are robot-validated. Recorded station names accompany robot IDs in model context and evidence links;
task text is not used to infer execution identity. Client-supplied labels, counts, model
providers and replay URLs are never trusted.

Success rate is Success/(Success+Failure); Uncertain and unlabeled/excluded runs
remain separate. Human exclusions take priority over imported reviews. Automatic
labels include saved prediction reasons, confidence, limitations and label-model
provenance. They remain predictions. The discussion receives **no images or
video**. It cannot claim direct visual observation. Nearby cloud points encode
similar task descriptions, not equivalent physical conditions or a causal test.

The context includes complete aggregate counts and up to 32 examples balanced
across outcomes and ranked by the question, plus the opened run and current
library examples when within the requested scope. Repeated-task groups are
bounded to 40, with total/shown counts; they are descriptive, not causal
comparisons. Answers return up to eight validated evidence IDs. The server
creates replay links; same-robot links open the existing replay inspector,
while cross-robot links use the normal robot/run deep link.

## Model decision and configuration

The user explicitly delegated: “Choose a suitable OpenAI model that fits BluPe’s
existing setup.” Selected `gpt-6.1-terra`, low reasoning, no model tools and no fallback. The optional API transport uses
the Responses API, maximum 2,200 output tokens and `store:false`. Production uses
the explicitly configured ChatGPT subscription transport described below. The
model suits short evidence-grounded synthesis and structured outputs. Current
capability documentation was fetched November 1 UTC / October 31 local:
[model](https://developers.openai.com/api/docs/models/gpt-6.1-terra),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses).
Requested and provider-returned IDs appear with each API answer. The subscription
CLI receives the exact selected ID but does not expose a resolved ID; the UI
reports that limit without inventing a returned model. This provider ID is an alias;
no immutable checkpoint resolution is claimed.

`YAM_DATA_CHAT_SOCKET` explicitly selects a separate private text-only ChatGPT
subscription socket. It takes precedence over optional API configuration. The
existing credential owner runs `remote_yam.run_data_chat_subscription`, with
`--socket`, `--binary`, `--home`, `--model` and `--client-uid`. The service accepts
only the existing web service UID, fixed discussion schema and bounded message
history. It executes Codex with the exact model, low effort, ephemeral sessions,
read-only sandbox, approval never, disabled shell/apps/hooks/multi-agent/web,
and a 55-second deadline. The environment excludes API/robot credentials. Each
connection is independent, with only the supplied conversation history. There
is no browser-selectable executable, home, endpoint, schema or CLI flag. The
robot decision broker and protocol remain unchanged. See the provided
[systemd example](../../deploy/data-chat/blupe-data-chat.service).

Production access verification found the configured API credential expired
(`401 expired_secret_key`), before any paid generation. The existing subscription
was ready and its account catalog explicitly listed `gpt-6.1-terra`/low. After
reporting the access constraint, selection stayed on that model through the
separate subscription transport. Andrew's live metadata-only test completed
in 10.412 seconds and returned validated citations. A resolved model ID is not
exposed by this CLI. No API key is requested for subscription use, and no login
credentials are copied.

`YAM_DATA_CHAT_CONFIG` opts the feature into a private server-side JSON file with
`api_key` or `model_key`. `YAM_DATA_CHAT_MODEL` overrides the model; otherwise the
optional `data_chat_model` setting or the documented default is used. The existing
hosted server has an OpenAI credential configuration and a separate subscription
broker limited to robot decisions. An API installation must opt its configuration into
this text feature; do not send discussion prompts through robot-decision adapters,
copy credentials or ask subscription users for an API key. Standalone installations
without this optional configuration show a clear unavailable state.

POST `/api/run-data-chat` uses the existing browser session, same-origin and CSRF
checks. Input/history are bounded. One request per visitor can run at a time,
with a three-second minimum interval; each application provider allows two
concurrent calls and 30 requests per ten minutes. Provider timeout is 55 seconds.
Raw provider diagnostics and credentials stay out of responses. Failures keep the
question editable; Stop waiting discards the browser result honestly while the
bounded server call may finish. Conversations are tab-local, with the last 12
messages sent for follow-up context; New conversation clears them. Model calls
do not spend robot guest-run allowances or create a robot policy/session.

## Verification status

The feature is live in the [public run library](https://playground.blupe.io/#past-runs).
[CHECKLIST.md](CHECKLIST.md) records the complete applicable acceptance evidence,
exact validated source/pin/CI links, screenshots, transcripts and explicit N/A
research-hardware requirements. No user name/email is required.

Public Chrome verification covered complete collection versus current filters,
preserved follow-ups, independent opened-replay context, a decoded/played cited
recording, explicit last-replay focus and the 390px phone layout. Model statements
remain predictions to inspect against their supporting runs, not verified causes.
