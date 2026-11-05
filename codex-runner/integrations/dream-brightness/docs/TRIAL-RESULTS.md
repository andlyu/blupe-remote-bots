# Dream1 brightness: exploratory physical pilot

User invocation: add 50%-darker Dream1 images, launch an adjustable local UI, keep brightness fixed per run, and compare relative performance. Confirmed runner: Andrew. His confirmed private email was entered only into the local operational UI and existing BluPe queue/run destinations. Execution mode: agent-operated normal UI; outcome review by the agent on Andrew's behalf. No person was invented.

## Actual configuration and outcomes

- UI: http://127.0.0.1:8798. Backend: https://yam-session-api.n5hthc3gj4cqy.us-east-1.cs.amazonlightsail.com.
- Robo-house YAM `robot-ba8413962083809c`; both arms; normal queue/lease, Home, native validator, limits, Stop and parking retained.
- Requested Dream1; actual `dreamlabs/dream-1-beta`, Dream SDK/client1.0.0. Provider alias did not expose a verified immutable checkpoint. No Flash/substitute was used.
- Same task and 60s limit: “Pick up the green pen and put it in the cup, then withdraw your gripper and hold.”
- All overhead/left-wrist/right-wrist policy images, including history, received the selected fixed brightness. Live and recorded spectator footage retains normal brightness.
- Run base source `77cee11e0916e084e83d3b96eaadecae8eb24bd6`; executed experiment code digest `804d1e42ddebe9fe63b819eb403cce87727d67ea1e7c8eac9b679f340ba988b6`. Later bookkeeping fixes preserve that digest for the historical episodes.

| Condition | Episode | Reviewed result | Successful SDK responses | Completed packets | Mean SDK RTT | Mean controller decision |
| --- | --- | --- | --- | --- | --- | --- |
| 100% | `ep_17a7cf3b22d34fbf` | Failure | 10 | 9 | 1190.66ms | 1965.95ms |
| 50% | `ep_9a2ff3550b444f7f` | Failure | 8 | 8 | 1131.53ms | 2527.12ms |

Baseline footage shows a grasp/lift but no release into the cup followed by withdrawal before the deadline. The 50% replay also shows no completed placement. These are task failures, not unscored infrastructure failures. Both ended at the normal policy duration cap and the native controller parked the arms at zero and disabled torque. Baseline public status was `safety_aborted` after the native duration-limit event; darker status was `timed_out`. No uncertain/timed-out movement was automatically retried. The darker controller counted 9 decision attempts but retained only 8 successful SDK response events; the table does not relabel attempts as successful responses. Generic text-model accounting reported zero and is not used for Dream counts.

The difference in observed success proportions is **0 percentage points (0/1 versus 0/1)**. Another station user moved the objects between conditions; the changed scene was documented before the second trial. The scenes were not restored to match. Single attempts with unmatched scenes are insufficient to infer brightness robustness or a latency effect. SDK RTT includes gateway/network time; controller decision latency additionally includes capture and IK. Neither is a controlled model-speed benchmark.

## Evidence

All following links are local retained artifacts relative to the repository:

- [Preregistered plan and scene mismatch](../evidence/TRIAL-PLAN.md).
- [Structured results and full timing boundaries](../evidence/trial-results.json).
- [Original condition/source records](../evidence/retained-trial-records.json).
- [100% physical replay](../evidence/baseline-replay.mp4) and [50% physical replay](../evidence/dark-replay.mp4). These are native accelerated edits (about6s at10×), not unedited minute-long videos.
- [Current relative-results screenshot](../evidence/relative-results.jpg), [baseline UI timeline](../evidence/baseline-timeline/timeline.json), [dark UI timeline](../evidence/dark-timeline/timeline.json), and [native Home/parking log](../evidence/native-operator-log.txt).
- [Release preflight receipt](../evidence/release-preflight.xml):45 Python tests; actual JS body test also passed. Actual Dream conversion and HTTP serializer feed the exact deployed canonical parser, including fractional gripper starts, endpoints, invalid values, lease/freshness rejection and zero-dispatch failures. Full dependency versions are retained in `dream-dependencies.txt`.

Both runs were visible live and their immediate native replay opened through the normal UI; their past-run entries can be selected after server restart, with Andrew, Dream model and Failure labels retained. Replay footage has missing/stalled camera segments, especially the observer view; do not claim continuous complete four-camera coverage. The normal live view also reported lag/catch-up honestly.

## Startup timing and readiness

The newer control harness Launch endpoint returned404 with `write_started=false`; it did not move a robot. The native operator UI was inspected and used normally: Launch Arms, Park at Zero & Stop, then enable the existing automatic FIFO. The queue had been paused by controller restart, not an explicit denial. An initial Park request rejected locally because arms were not initialized; no movement occurred from that rejection. Required command-contract validation against the exact deployed parser passed before actual physical action. Other users' sessions were left undisturbed.

Home completion (native log, second resolution), queue records, timestamped Run-click brackets, first confirmed waypoint progress and full/queue-adjusted durations are retained in `trial-results.json`. The backend first-waypoint proxies occur about7.0–7.3s after the queue-adjusted baseline click and6.2–6.5s for the darker click; post-Home proxies are about7.74s and6.42s. These are not a precise visual first-motion measurement. UI screenshot sequences have gaps and do not establish every required visual timing boundary. The mandatory first-observed-motion timing requirement remains **unchecked**. No GPU-startup exemption was applied. Baseline SDK configuration took48.297s while in the382.098s evidenced queue wait; do not subtract it again.

## Remaining acceptance

Current checklist11/17, including explicit simulation N/A. Unmet: public deployment/source/evidence delivery and deployed revision verification; matched-scene representative task acceptance; strict visual timing proof for every run; full meaningful-wait/failure/recovery verification; and a final end-to-end physical run on the final deployed version. No user-directed visibility exception is claimed. Local requested UI is running; the research integration is not declared complete.
