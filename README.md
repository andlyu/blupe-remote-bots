# BluPe

Run your own AI policy on real robot arms. Watch the
[playground](https://playground.blupe.io/), or run it locally with your Codex or
Claude subscription. No robot or model API key is needed for subscription use.

<a id="run-the-blupe-playground-locally"></a>
<a id="download-launch-run"></a>

## Quick start

Requires Git and Python 3.10+ on macOS or Linux (Windows: WSL).
Codex subscription use also requires Node.js/npm and an account with Astra access.

```bash
git clone https://github.com/andlyu/blupe-remote-yam.git
cd blupe-remote-yam
./run-codex.sh
```

Complete your own OpenAI browser sign-in if prompted, then keep the terminal open.
Choose a robot, enter a task, and click Run in the local playground. Run joins the
robot queue and enables command submission; station readiness and motion checks
still apply. Use Stop to finish. If the port is occupied, add `--port 8792`.

For Claude, use `./run-claude.sh`. To open the playground before choosing a
provider, use `./run-playground.sh`. Credentials stay on your computer.

[Robot API documentation](https://blupe.io/docs/robot-api/) — connect your own
model, inspect cameras/calibration, and control sessions through HTTP/WebSockets.

[Local setup and troubleshooting](docs/local-playground.md) ·
[API source](docs/API.md) · [Repository ownership](docs/REPOSITORY-OWNERSHIP.md)

The playground exists for demos and showing people how well approaches work.
Everything in the playground demo is public by default, including its website,
source, runs, results, recordings, replays, simulation outputs and supporting
evidence, unless a user explicitly changes visibility for the relevant materials.

Integrating a research paper or method? Start with the
[integration completion checklist](codex-runner/integration-harness/COMPLETION-CHECKLIST.md).
Its Model field identifies the approach being tested, with underlying model and
checkpoint configuration recorded separately. It includes actual user attribution,
separate execution mode and visible wait stages; verify every requirement with
evidence before claiming completion.
