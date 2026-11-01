# Run-library data conversation

The library's **Ask about these runs** action opens a read-only conversation beside
Cloud or Table. The baseline is the complete public collection across robots.
Current robot, model/search filters, box selection and opened replay are separate
context. Changing them preserves the conversation. The scope selector offers an
explicit filtered/box or opened-replay focus. Each answer retains its own scope,
counts, denominator, evidence sample size and actual model identifier.

The server reloads authoritative public archive metadata and human assessments,
then applies the same search/filter implementation as the library. It separately
computes all-collection, current-library and requested-focus aggregates. A box
must contain existing IDs that match the current robot/filters; an empty box stays
empty. Opened replays are robot-validated. Client-supplied labels, counts, model
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
existing setup.” Selected `gpt-6.1-terra`, OpenAI Responses API, low reasoning,
maximum 2,200 output tokens, `store:false`, no model tools and no fallback. The
model suits short evidence-grounded synthesis and structured outputs. Current
capability documentation was fetched November 1 UTC / October 31 local:
[model](https://developers.openai.com/api/docs/models/gpt-6.1-terra),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses).
Requested and returned IDs appear with each answer. This provider ID is an alias;
no immutable checkpoint resolution is claimed.

`YAM_DATA_CHAT_CONFIG` opts the feature into a private server-side JSON file with
`api_key` or `model_key`. `YAM_DATA_CHAT_MODEL` overrides the model; otherwise the
optional `data_chat_model` setting or the documented default is used. The existing
hosted server has an OpenAI credential configuration and a separate subscription
broker limited to robot decisions. Reuse the API configuration explicitly for
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

Implementation and focused checks are recorded in [CHECKLIST.md](CHECKLIST.md).
Public-source CI and production compatibility/deployment proof will be appended
there. Local visual fixtures use actual public metadata and explicitly say when
the answer is a fixture. A fixture is not live model verification.
