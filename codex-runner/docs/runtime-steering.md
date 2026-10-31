# Steering an active rollout

The browser session that started a run can send a correction from **Steer your
run** in Task chat. The original goal, completed tool calls and measured robot
feedback remain in the conversation. Spectators can read shared messages but
cannot submit instructions to another visitor's controller.

## Related work

| Work | Where the correction enters | Implication for this runner |
| --- | --- | --- |
| [Inner Monologue (2022)](https://inner-monologue.github.io/) | Human interaction, scene descriptions and success feedback enter the ongoing LLM planning prompt. The authors demonstrate changing tasks during execution. | Append owner feedback to the existing conversation, alongside observations and execution results. |
| [RT-H (2024)](https://rt-hierarchy.github.io/) | A policy predicts an intermediate language motion, then actions conditioned on it, the task and images. Human language can replace the intermediate motion at inference time. | Corrections can describe a local action such as lifting an arm without replacing the entire task. RT-H uses a trained hierarchy; it is not simply an LLM prompt edit. |
| [Yell At Your Robot (2024)](https://arxiv.org/html/2403.12910v1) | Human language corrections guide a hierarchical language-conditioned policy during execution; collected corrections also train the high-level policy. | Keep corrections explicit and recorded. This implementation supports runtime prompting, not training from corrections. |

These works motivate the interface and prompt integration. Their robot success
rates do not establish the performance of this implementation.

## Prompt and execution boundary

Conversational RoboCurve providers (OpenAI/Astra, Codex, Anthropic and Claude,
including their joint, SO101, MakerArm and Codex depth variants) share the inbox.
Dream-1 beta and Flash also support owner steering through their language input
(below). Fixed code programs, hosted remote policies
and other VLA adapters report live steering unavailable.

The inference thread appends each accepted message once, after its fresh camera
observation, as a **user** turn:

```text
Run-owner steering update #1:
Use the right arm instead; lift before moving sideways.
```

Additional system guidance accompanies the first steering message, leaving the
versioned robot system prompt unchanged. It explains that later owner updates supersede conflicting task
instructions; relative corrections should not repeat indefinitely. The original
goal remains unchanged for run identity. Updates do not alter safety limits,
tool schemas, lease checks, IK validation, or measured completion requirements.
Codex and Claude resume their existing conversation using the new user turns.

Messages received while a trajectory runs wait for measured completion. If a
message arrives during a model request, its returned tool calls receive a
`superseded` result without execution, and the policy requests a new decision
with the correction and refreshed observation. Motion already dispatched is not
interrupted by steering. Use **Stop** to halt a run. Depth measurement subcalls
may finish before the outer decision loop consumes a correction.

### Dream-1 prediction boundary

Dream receives one task string rather than conversational user turns. At the
next prediction boundary, the runner combines the original task and accepted
owner guidance in submission order, stating that newer guidance takes precedence.
This becomes the `prompt` in the observations passed to SDK1.0.0
`set_observation`; `get_action` consumes that latest prompt. Subsequent
predictions retain the guidance when the controller passes the original run
task again. The original task still identifies the run.

Guidance does not reset the SDK episode, model session, camera window or
completed command anchor. A correction arriving during inference discards that
unused prediction and requests a new one at the same gateway step with fresh
input. On the first prediction, measured pose supplies the anchor instead of an
unexecuted result. Already dispatched motion finishes through the existing
completion path before another prediction. Stop retains its existing behavior.

`included` means the updated prompt was put into the outbound prediction
context. It does not establish live model obedience or a physical outcome.
`test_dream_steering.py` covers this through the authenticated owner endpoint,
real adapter and worker subprocess with a controlled SDK; it makes no paid
model request or robot command.

Delivery states mean:

- `queued`: accepted by the runner, awaiting the model decision boundary.
- `included`: appended to model context. This is not proof of model obedience,
  successful network delivery, or arm movement.
- `not_delivered`: the run ended with this message still queued.

Messages appear in the local interaction journal and shared conversation under
the run's existing sharing settings. The exact outbound model request contains
the appended user turns. Sharing to the public gateway includes the owner text
as a user message; it does not expose internal request IDs or new capabilities.

## Endpoint and ownership

`POST /api/steer` accepts `attempt_id`, `request_id`, and `text` through the same
visitor cookie, exact Origin, JSON and CSRF checks as Run/Stop. It always uses
the authenticated visitor's controller. `attempt_id` must match that
controller's currently running attempt; it never selects someone else's run.

`request_id` is a client-generated identifier (16–80 letters, digits, `_` or
`-`). Repeating it with the same text returns the existing receipt; changing its
text returns 409. Messages contain 1–2,000 trimmed characters. Limits are one
new message per second, eight pending messages, 32 per run and 16,000 total
characters. The endpoint rejects inactive, expired and unsupported runs.

The UI preserves drafts on network errors, reuses request IDs on retries, and
discards late responses when the run, robot or browser session changes.

## Verification

`test_runtime_steering.py` exercises the ASGI ownership and CSRF boundaries,
idempotency, bounds, prompt order, in-flight response replacement, completion
feedback, Codex resume and the real controller with a mock Session API.
`test_runtime_steering_ui.cjs` covers owner-only presentation, polling, retry
identity, terminal states and stale responses. Browser fixture
`tests/browser/runtime_steering.js` exercises the full shared UI without a
model, robot or external API connection.

Run the browser fixture from `codex-runner`:

```sh
python3 tests/browser/serve_runtime_steering.py --port 8897
```

Open `http://127.0.0.1:8897/`. The visible report should show eight passing
checks; the fixture leaves the owner composer available for inspection.
