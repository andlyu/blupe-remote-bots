# Astra 6.2 playground release

User request (2026-11-20 Pacific): “Lets make sure that Astra 6.2 is live on the playground”. Adopted AGENTS.md routes this verification to the [shared harness](../integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness). This updates the foundation-model selection in the existing Astra method. No robot control primitive, safety gate, recording mode, or unrelated model changes.

- Requested/default ID: `gpt-6.2-astra`; existing explicit older model selections and `?model=gpt-6-astra` stay exact. `?model=astra` and `?model=gpt-6.2-astra` select 6.2.
- Official capability source: [GPT-6.2 Astra](https://developers.openai.com/api/docs/models/gpt-6.2-astra), fetched 2026-11-20. Text/image input, structured output, reasoning; `none` effort is unsupported.
- Signed-in existing server account: Codex 0.159.0 model/list omitted 6.2. Official pinned npm `@openai/codex@0.171.0` model/list includes 6.2 with low/medium/high/xhigh/max/ultra. Existing subscription and Fast/default effort choices are preserved; no API fallback.
- Real staged broker-executor check: requested `gpt-6.2-astra`, low effort, synthetic green image, 6.1164097786s. Complete thread/turn and valid decision `action=done`, all targets null, summary `Green`. Robot transport was not connected; no queue or identity submission. Provider alias is retained as returned by its catalog; no immutable model snapshot is claimed.

## Verification checklist

- [x] Researcher’s exact selected model retained.
- [x] Account lists requested model and real vision/structured decision succeeds.
- [x] Shared UI/default routing and hosted broker default updated; explicit older models preserved.
- [x] Focused shared checks: 94 Python tests and 21 subtests pass; picker/link checks: 18 pass.
- [x] Live deployment at 2026-11-21 00:47:28 UTC, public subscription catalog and enabled browser selection verified. Deployed broker server-default synthetic vision check: 6.8852286758s, done/null targets/Green. Public hosted.js SHA256 eb895780150dab3205e04661e95831fa4c2353f1eaed38456630b7ce21bdbc46; model-picker.js 186ad7354bfaf1eacf38be3b9a2b35918156682641aa32bde6b7b6185176a6d3. Four queues were empty; only web and broker restarted.
- [ ] Physical task execution, onset timing, recording and replay on Astra 6.2 verified. This model-release check does not establish those physical integration acceptance gates. Existing controller/command-contract code is unchanged. No simulation executed.

Public site: https://playground.blupe.io/?model=astra
Public source: https://github.com/andlyu/blupe-remote-bots
Visibility exceptions: none; the initial release check produced no run recordings. The later physical trial below has a public replay. No identity or private contact fields are included in this evidence.

Hosted model checks: 203 passed, 8 subtests, 1 unrelated ASPIRE test deselected (required module absent from public source). Broad JS has one unchanged replay-history baseline failure, reproduced using origin/main source and test in a temporary fixture; model-related checks pass.


## Physical Extra High / Fast trial — November 20, 2026

User invocation: “Lets test it”, following the explicit Astra6.2 / Extra High / Fast selection. Existing saved runner identity was used through the normal website, with optional video email off. Method: existing Astra Cartesian policy; underlying model `gpt-6.2-astra`; execution mode: agent-assisted normal-UI test.

[Exact run and replay](https://playground.blupe.io/?robot_id=robot-ba8413962083809c&model=astra&run=ep_30fa0d815cd94f51). Task: pick up the upright orange block behind the gray plate, place it on the plate’s empty left half, release and withdraw while leaving the existing plate block undisturbed. Two-minute run limit; existing queue, readiness, command/hardware limits, Stop and parking preserved. No automatic timed-out-motion retry.

| Check | Result and evidence |
| --- | --- |
| Exact model / settings | PASS: observed live process flags `--model gpt-6.2-astra`, `model_reasoning_effort="xhigh"`, `features.fast_mode=true`, `service_tier="fast"`. |
| Offline deployed command path | PASS:50 tests+14subtests; supplemental18legal/18invalid zero-dispatch cases through parser/generator/serializer/client validator, including fractional gripper0.9992793312193716 and exact0/0.5/1 endpoints on both arms. Pitch/roll are pinned0 in this existing method. No physical sends during these checks. |
| Physical execution | PASS: live arm motion, approach and attempted grasp observed; retained run metrics report8model calls and120confirmed waypoints. |
| Requested placement | FAIL: stopped at the two-minute limit while correcting grasp alignment; block not placed. |
| Measured model latency | First completed step9.8348s. Six retained completed-step timings:8.4588–18.9759s, median10.1324s. These are model timings, not Run-to-motion or task-completion times. |
| Queue/Home/onset budgets | UNVERIFIED: Send task launched directly using saved identity; exact click and visually corroborated Home/first-method-motion boundaries were not captured. Public run_started_at1795229798.4631095 does not replace the missing UI/visual boundaries. No timing pass or exception claimed. |
| Recording/replay | Eventual playback+seeking PASS: exact-episode7.6s edited three-camera preview, source timestamp overlays, native browser currentTime advanced3.1399→3.8598 while unpaused/readyState4. Replay was stillprocessing more than2min after Stop before it appeared; immediate-review timing FAIL/UNVERIFIED. No optional download/export used. |
| Replay attribution | FAIL: run record identifiesgpt-6.2-astra, but playable replay caption saysModel not recorded. |

The physical trial establishes model execution, not successful manipulation or complete harness acceptance. The combined physical acceptance box above remains unchecked. No simulation executed.
