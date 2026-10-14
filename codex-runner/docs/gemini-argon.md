# Local Gemini 4 Argon playground

Run `./run-gemini.sh --env-file /absolute/path/to/local-gemini.env` from the shared
repository root. The file contains `GEMINI_API_KEY=...`; alternatively set
`GEMINI_API_KEY` or `GOOGLE_API_KEY` in the process environment. Keys are read as
data and never copied into browser state or recordings. The launcher does not
start a robot run; an explicit Run uses the existing queue/controller controls.

Open the model menu and select **Calling mode** before starting a Gemini run:

- **Sparse calling** (default) retains the 1st, 2nd, 3rd, 5th, 7th and 10th most
  recent completed model calls. The selected calls are sent oldest to newest.
  Every retained call keeps all its camera observations, native thoughts,
  function calls and completed results. The current observation, task, safety
  instructions and owner corrections stay available. Other past calls are
  omitted from model input; the full recordings are preserved.
- **Normal calling** sends the full accumulated history, as before.

These settings apply only to Gemini. Mode changes during a run are rejected;
`gemini-config.json`, status metadata and each actual `gemini_request` record show
which mode was selected. Sparse mode enforces a conservative 65,536-token input
estimate and an 8 MiB request-size limit, failing before sending if the exact
selected context is too large. Normal mode retains the existing full-history
behavior. Both use medium thinking by default and a 32,768 output-token cap.

Sparse history passed twelve live synthetic tool/image requests with real native
thought signatures. However, Google's current thinking guide requires full
thought replay, so Sparse calling remains experimental. See
[provider references and probe receipt](refs/gemini-argon/INDEX.md) for the exact
contract, sizing method and limitations. No robot run was used for verification.

For a reviewable UI with **all robot runs disabled**, no key and no queue access:

```sh
./run-gemini.sh --preview --port 8797 --no-browser
```

The preview uses mock control sessions and its own browser cookie. It can show
public read-only video; the preview cannot admit a run. Choose a free port if
another local UI is already running. Existing local services need not be stopped.

`--thinking-level low|medium|high`, `--model`, `--api`, `--camera-origin`,
`--robot-id`, `--recording-root`, `--port` and `--no-browser` are supported.
`--local-subscriptions` adds the existing Codex/Claude choices without applying
Gemini's context selection to them. No sponsored visitor quota applies locally.
