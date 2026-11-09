# Fable 5.2 deployment and verification — November 9, 2026

Invocation: “please integrate Fable 5.2 into the playground,” under adopted
AGENTS.md and its [authorization-by-use contract](https://github.com/andlyu/blupe-remote-bots/blob/main/codex-runner/integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness).
The selected model is exactly `claude-fable-5-2`. No other model was substituted.

- Public site: [BluPe Playground](https://playground.blupe.io/).
- Public code: [PR #301](https://github.com/andlyu/blupe-remote-bots/pull/301),
  merged as `5c8ded16b213ac59b922ea3fba878a5989d27ad9`.
  The hosted pin `81989b4d96ef50891b8e03010c412cd1e21dd5d5` retains ASPIRE.
- Shared CI: [runner](https://github.com/andlyu/blupe-remote-bots/actions/runs/42695085589),
  [Dream preflight](https://github.com/andlyu/blupe-remote-bots/actions/runs/42695085488),
  and [RoboHarness command contract](https://github.com/andlyu/blupe-remote-bots/actions/runs/42695085644)
  passed. Hosted tests on the exact pin: 508 Python passed, 9 skipped, 25 subtests
  passed; 42 JavaScript tests passed. GitHub did not start the private runner
  because of its account billing or spending limit.
- Deployed: reviewed public asset hashes and broker at release v2, active
  overridden web runner at v3. The old Caddy asset mismatch rolled back before
  the corrected release. The active web interpreter accepted the exact model ID.
  The access release then published the API key picker and pre-queue hosted guard
  (private hosting change #212; 153 focused tests and 4 subtests). The logged-out
  playground offered “Fable 5.2 · API key” and an empty editable Claude API key
  field under More options. The API route defaulted to Standard speed.
- Offline Robo-house gate: 14 motion packets went from a synthetic Fable
  Messages response through the real RoboCurve tool parser, IK/pacing,
  HTTP serializer, gateway packet schema, and station validator. 19 invalid
  or mismatched responses produced zero packets. Checked both arms' X/Y/Z,
  yaw, gripper endpoints and partial values from fractional starts, and
  preservation of the other arm. The installed controller source and build
  each had SHA-256
  `1c640b6d144d8b55c2a77ae584e71a91cb50d036ddc5d548fe4d656dd5d74483`.
  Existing controller workspace tests cover the XYZ faces separately.
- Physical scope: Robo-house YAM (`robot-ba8413962083809c`), both arms for
  normal Home and park, one arm for the small blue cube task; 60 seconds,
  Low effort, existing queue/lease/Stop and safety controls. Origins:
  `https://playground.blupe.io` and
  `https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com`.
  Browser operated by the agent; actual confirmed runner: `andrew`.
  Email was supplied only in the normal BluPe form and is omitted here.
  Video email was not selected. Replay destination: playground and
  [Public-YAM-runs](https://huggingface.co/datasets/andlyu/Public-YAM-runs).
- Attempt 1: Run click bounded by 20:51:25.575–20:51:26.188 UTC. The old
  backend module rejected the model before admission. No lease, motion, or replay.
- Attempt 2: `ep_501d78382cdb4971`, public queue status stopped,
  recorded episode start 20:54:24.492702 UTC. Run click bounded by 20:54:12.892–20:54:12.954 UTC. Browser
  showed joining at 20:54:19.163, queued/preparing at 20:54:25.658, and
  admitted/Running with arms out of park by 20:54:30.711. The visible startup
  Home boundary and exact queue entry/admission timestamps were not measured
  precisely enough to compute queue exclusion or elapsed motion timings.
  Claude Code started its model session and rejected the request before
  returning a Fable decision. At 20:54:44.874 the run was failed and the cube
  remained in place. There was no model-driven arm motion and no motion
  target pass. The failure replay loaded and completed in the playground;
  it is evidence of the attempt, not a successful Fable run.
- Visibility and wait behavior: the public page and repository opened. The
  live UI showed prompt review, joining, queued/preparing, model startup and
  terminal failure. The main queue state updated to “Your turn”; the lower
  status still said “You’re in the queue.” There was no GPU provisioning.
  No visibility exception was requested.
- The lower status now follows the queue, preparation and running stages.
  [PR #302](https://github.com/andlyu/blupe-remote-bots/pull/302) merged as
  `9f8e3009fccd4ec6caa1928cf540bcae083031fd`. All eight public CI checks passed.
  Both reviewed hosted JavaScript overlays passed the focused transition test,
  including preservation of warnings and Stop acknowledgements. The public
  browser reopened the playground successfully and HTTPS served SHA-256
  `adbc195fbf2069edf5552daa2c83ceba421e32e5a789bbdc47e0109a9cdc23db`.
  The web and broker processes stayed up. The updated inline lifecycle still
  needs observation during a successful physical run.
- Access: the hosted Claude Code 2.1.296 rejected the requested model. The
  vendor-signed 2.1.321 candidate was staged and tested in a read-only
  catalog query under the same subscription. Anthropic's unfiltered catalog
  listed Fable 5.1 and Fable 5, but not Fable 5.2. The active launcher was
  left on its prior build. No alternate model was used.
- The researcher's signed-in Claude web account showed Fable 5.2 selected
  with a completed reply. After the researcher signed in to local Claude Code
  2.1.321, the exact Fable 5.2 ID appeared in its subscription catalog and the
  local BluPe launcher responded with HTTP 200.
- At 13:27 PST the active and staged hosted CLI executables both reported
  signed out under the broker account. The exact-model text check stopped at
  authentication before sending its prompt. A new anonymous Robo-house web
  session omitted sponsored Claude and still exposed Claude API-key support.
  No new robot attempt or model response resulted from these checks.
- The owner restored the dedicated hosted Claude subscription sign-in. The
  active 2.1.296 catalog still omitted Fable 5.2. The same account on 2.1.321
  listed `claude-fable-5-2` and returned a text response whose assistant stream
  confirmed that exact model. The first text probe misclassified rate-limit
  telemetry. The corrected probe checked the final result and exact assistant
  model identifier in 6.46 seconds.
- The dedicated broker now uses Claude Code 2.1.321. The Linux x64 binary
  matched Anthropic's official release SHA-256
  `426c33815ca6645a772f722fbff10dbf2cbdb124a8aeab733c1365dbf8bbf61f`.
  Activation checked all six robot queues were idle and kept the same broker
  process. The public catalog returned the exact model through the subscription
  route. The browser showed and selected “Fable 5.2 · BluPe subscription.”
- In user-started public episode `ep_a19a2ed66db04a2f`, Fable 5.2 was verified
  in the live UI and executed one right-arm move to approach the blue block.
  The first model call took 113.44 seconds. The robot confirmed all 20
  waypoints in one accepted packet, moved the right arm 10.77 cm and spent
  2.40 seconds executing. The next request timed out. The block stayed
  outside the cup, and the public record reports failure. The edited replay
  shows the different right-arm positions before and after the move.
  [Public replay](https://playground.blupe.io/api/quick-replays/ep_a19a2ed66db04a2f/93ce24da8d2fe1d7e8d5e1665d326710ba9ac1517bd0ed7ef60776d21cd43ee0.mp4)
- The observed hosted process for that run used Extra High effort and passed
  `fastMode: true`. Actual inference speed was unverified. Anthropic requires
  a Fable-specific `/fast` opt-in and usage credits for Claude Code Fast mode.
  The Run click, queue timestamps and settled Home boundary were not captured
  for this user-started run. The two motion timing targets remain unverified.
  [Claude Code Fast mode](https://code.claude.com/docs/en/fast-mode)
- The deployed picker now labels the sponsored entry “Fable 5.2” and defaults
  to Extra High when supported. The browser opened the direct link with the
  sponsored model selected and verified that Reset restores Extra High. The
  prior saved effort stayed selectable. [Picker PR #303](https://github.com/andlyu/blupe-remote-bots/pull/303)
  · [Direct Fable 5.2 link](https://playground.blupe.io/?robot_id=robot-ba8413962083809c&model=claude-fable-5-2)
- Representative task success, exact queue and motion timing, and successful
  replay and historical attribution are still required.
