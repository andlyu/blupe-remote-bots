# Controller-direct model execution

The existing runner route remains the API default. An omitted `executor` or JSON
`null` uses the current local/hosted runner adapter, observations and commands.
Controller selection creates a separate instance of the same provider adapter
on the selected robot's controller host. The model stays at its provider.
Queue admission, the existing lease, Home, Stop, cancellation, native trajectory
validation, receipts and duration expiry retain their existing paths. Video,
recording, background transfer, replay and dataset paths are unchanged.

## API and client selection

`POST /api/session` includes a robot-specific `controller_models` catalog.
Unavailable registrations include a bounded reason. An available registration
means installed/configured; provider entitlement and a successful inference are
separate evidence. Never infer physical task success from configuration or counts.

For a predefined model, add two fields to the ordinary `/api/run` request:

```json
{
  "provider": "openai",
  "model": "gpt-6-astra",
  "prompt": "Pick up the orange block.",
  "runner_name": "Andrew",
  "email": "your-address@example.com",
  "run_duration_s": 120,
  "executor": "controller",
  "controller_model": "astra"
}
```

Use registrations returned for that robot. The former `executor: "dream_one"`
RoboHouse API remains compatible. It selects the same installed Dream-1 model.
The generic route supports both RoboHouse and YAM1; a checkpoint's embodiment
restrictions remain authoritative.

```python
from remote_yam.runner_policy_client import RunnerPolicyClient

client = RunnerPolicyClient("https://playground.blupe.io", robot_id="yam-1")
client.connect()
client.start_model(provider="openai", model="gpt-6-astra", prompt="Your task",
    executor="controller", controller_model="astra", email="your-address@example.com")
# Retain this client for status() and stop(); an uncertain start is never retried.
```

The browser's Model execution control defaults to Automatic. It uses Robot
controller when the ordinary model picker matches an available registration by
exact model ID and provider family; otherwise it uses the existing BLUPE runner.
Codex/sponsored Astra and Claude/sponsored Claude aliases share their respective
provider families. An ASPIRE policy is not an Astra registration. Model, robot
and catalog readiness updates recompute Automatic; status polling supplies the
latest public controller catalog without making any provider request.

BLUPE runner remains an explicit choice and survives model/robot/readiness
updates. Explicit Robot controller offers the selected robot's installed models
and custom protocol. An explicitly retained controller model that becomes
unavailable is rejected clearly rather than substituted. Custom endpoint drafts
survive catalog refreshes and are never selected automatically. Normal hosted
email, guest allowance and ownership checks still apply. Hosted subscription
transports are never attached to controller policy objects.

## A session user's own endpoint

Users may supply their own endpoint; they do not need an administrator to
register each URL. A controller must have the `custom` registration with the
installed `responses_v1` adapter enabled. The request supplies:

```json
{
  "provider": "custom",
  "model": "your-model-id",
  "prompt": "Your task",
  "runner_name": "API operator",
  "email": "your-address@example.com",
  "run_duration_s": 120,
  "executor": "controller",
  "controller_model": "custom",
  "custom_endpoint": {
    "protocol": "responses_v1",
    "url": "https://your-service.example/v1/responses"
  }
}
```

`RunnerPolicyClient.start_model` accepts the same `custom_endpoint` object. The
UI exposes endpoint and model-ID fields. No filesystem paths, executable code,
API key values, headers or alternate prompts enter the execution envelope.
Endpoint/model selection is immutable for a lease, including status/predict.

The endpoint accepts the same Responses-style `input`, image data, `tools`,
`model`, `store` and reasoning fields as `RoboCurveResponsesAdapter`. It returns
Responses `output` items with exactly one `function_call` per turn, retaining
its `call_id`, `name` and JSON `arguments`. Supported tools are the installed
Cartesian `move_to`, `done` and `give_up` contract. The adapter performs existing
station-specific tool/IK validation before constructing native 10 Hz packets.
An arbitrary joint-array API or full managed robot service is not this protocol.

Only public HTTPS is accepted. The controller checks all resolved addresses,
connects to a validated numeric address with certificate/SNI verification for the
original hostname, and disables proxies and redirects. URL userinfo, queries,
fragments, private/link-local/loopback destinations and credential forwarding
are rejected. This session-user path sends **no Authorization header**. Users
whose provider requires a secret should expose their own authenticated proxy;
hosted/controller credentials are never forwarded to a supplied URL. A separate
administrator-owned fixed Responses registration may use its own private key.

## Host configuration and actual coverage

Private `blupe-controller-models-v1` configuration binds one `robot_id`, a models
map and fixed adapter names. Each registration has provider/model/label and
explicit availability. Supported reusable adapter implementations are Dream-1,
Dream-1 Flash, Codex/Astra, Claude/Opus, Gemini/Argon, GR00T, MolmoAct2 and the
Responses protocol. Provider keys reference private host-local files. CLI
adapters reuse the host's existing login; authentication is never copied.
Subscription runners continue to require ChatGPT login. A controller-owned
Codex registration can explicitly enable `existing_cli_auth` to reuse an already
authenticated local CLI API-key login. The CLI reads its own credentials;
the adapter never reads/copies the auth file or key. Its public configuration
reports `existing_cli_api_key` and API billing. This does not change subscription
runner defaults or forward credentials through a run request.

Dream uses a separate Python 3.12 SDK and prepared CPU IK pool; the native
operator keeps its existing environment. GR00T/MolmoAct2 require Pillow only
for encoding locally; the GPU remains at RunPod. Their currently configured
checkpoints require YAM1's embodiment and are rejected on RoboHouse.
Codex/Claude use the existing native Python, NumPy/MuJoCo geometry, CLI and login.
No local inference GPU or Dream SDK is required for them.

The current hosted catalog (October 29) has Dream-1 and Flash on both YAMs;
GR00T northstar-purple-crate step10000 and MolmoAct2 BimanualYAM on YAM1;
Astra via Codex, Opus via Claude, and Gemini 4 Argon. DreamZero is absent from
the active configuration and is not added by this rollout. XLab is a managed
session service, ASPIRE uses its distinct managed worker, and Reset bin is a
native recorded/reset policy. Those are retained on their existing routes;
ASPIRE is removed from selectable browser offerings while its existing internal
integration is retained. XLab is unchanged. These managed services cannot be
presented as Responses endpoints without an inference-only
adapter contract. Their separate services do not block lightweight deployment.

Private deployment receipts describe which registrations are actually installed,
which real provider checks ran, conversion evidence and physical execution per
robot. Missing credentials or incompatible dependencies stay explicit there.
Do not equate implemented adapter code with deployment or a successful request.

## No-motion verification

The existing `predict` operation converts one prediction without submitting any
native packet. A live read-only probe may use fresh initialized native feedback
in READY, STOPPED or API_ACTIVE without pausing admission or changing ownership.
DISABLED display-cache joints are never fresh measured input for execution.
Synthetic/recorded-input provider checks must label their inputs accordingly;
physical performance requires separate evidence from an authorized run.
