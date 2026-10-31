# RoboSkills × BluPe — verified behavior

Timing contract update (October 30, 2026): the shared harness now requires
15 seconds after settled startup Home (or documented no-Home robot readiness)
and 30 seconds after Run/Start excluding evidenced initial queue-admission wait.
Site entry is context only. References below to older timing gates are preserved
historical assessments. The 107.56-second packet-preparation time and approximate
97-second queue/readiness description do not establish a queue-adjusted pass
without matched admission, Home/readiness and visual motion evidence. Current
timing remains unverified; see the maintained checklist. No retest was performed.

Site: https://blupe-bimanual-skills.andlyu.chatgpt.site/
Shared source: https://github.com/andlyu/blupe-remote-bots/tree/main/codex-runner/integrations/roboskills

The live website executes the pinned RoboSkills persistent Python agent through the shared BluPe remote-arms harness. Model is RoboSkills; the current physical planner is gpt-6-sol, configured separately. Normal queue, lease, readiness, IK/workspace/pacing checks, hardware limits, Stop and parking remain intact. Name/email defaults are editable. Public run projections omit private email and capabilities. Viewing cameras, results and replay does not require sign-in; shared compute/control uses the connected operator.

Physical run2ea288ea830e471a86eb6d1d98971c50 completed a20mm paired lift goal, one-second hold and return, with the unchanged3mm Cartesian tolerance. Measured rises17.80/20.97mm, lift errors2.21/0.98mm, return errors2.14/0.08mm; grippers changed less than0.0001. Native status confirmed parked and torque off. Task success is a measured primitive check, not the upstream benchmark's native success score (unset).

[Actual physical replay](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/2ea288ea830e471a86eb6d1d98971c50/assets/physical.mp4) played and seeked through the website; anonymous byte-range access returned206. Completed progress stages and exact earlier measured failure reasons remain visible.

The15-second startup requirement remains unmet: latest Run04:21:30.927Z, first packet prepared04:23:18.484Z,107.56s later, including about97s queue/readiness. Exact visual onset was not separately timed. No GPU or research exception is claimed. The long wait does not alone prove a handoff bug. The backend's legacy public conversation projection labels callers API caller; this website/journal/receipts retain the actual confirmed runner.

Earlier tool review denied publishing the specific original failed-test recording; it remains local and no alternate upload route was used. New authorized tests and their automatic replays worked. This denial is not missing routine motion permission.

The native simulation check generated a real MuJoCo task and Blender replay: demonstration8/8; build rejected robot-rest and scene-framing; frozen-task solver not run. All outputs are reviewable in the website. Full fresh simulation build/solve success is not claimed.

Validation: focused22tests+8subtests passed; broader1621passed,4skipped,254subtests with CI dependencies; Node358passed; TypeScript/production build passed. The accumulated-offset regression failed before its fix and passed after.

See [the complete preserved checklist](docs/COMPLETION-CHECKLIST.md). Timing/full qualification remain open pending evidence or an explicit user exception.


Final recovery release: restored source after temporary-checkout loss; TypeScript and six lifecycle-display tests pass. New UI clears recovered connection errors, exposes operator access, and retains observed queue/admission/preparation stages. Public auth callback404 leaves final normal-UI physical retest unavailable in the current anonymous browser. Historical physical proof remains2ea288ea830e471a86eb6d1d98971c50. See the current preserved checklist for exact timing boundaries, qualification and unresolved prior denial.


## Owner clarification: physical queue needs no sign-in

The user explicitly stated “you don't need operator sign in. Arms are live if something goes to the queue it will run”, followed by “yes, remove it”. This removes the website's operator-only gate for physical queue submission. Keep confirmed editable human name/email, same-origin requests, the existing single-active-run bound, worker-role authentication and all BluPe queue/lease/readiness/validation/Stop safeguards. A private Secure/HttpOnly/SameSite browser capability allows only the submitting browser to stop its run. The public projection exposes neither that capability nor email. No sign-in or authentication redirect is needed for this flow. The earlier platform auth restriction is avoided through the user-requested public physical flow; no auth token, forged header or privileged bypass is used. This specific clarification does not authorize publishing the separately denied older recording.

Seven route-level tests pass for anonymous admission, required actual identity, cross-origin rejection, private Stop ownership, public redaction, one active run and protected worker APIs. Final production physical verification follows publication; keep its checkbox unchecked until measured.


## Public physical flow verified — October 30, 2026

The owner explicitly rejected the operator sign-in requirement and confirmed “yes, remove it”. The physical form now accepts a confirmed human name/email directly and uses normal BluPe queue admission. Same-origin validation, a private browser Stop capability, worker-role authentication and the existing single-active-run constraint remain. Shared simulation authorization is unchanged. This user instruction supersedes the earlier physical anonymous-admission restriction for this exact flow; no auth bypass was used. The older recording-publication denial remains separate.

- Final deployed Site: version13, source`01bac7438e6284716b0f85fd2ce158f2f20ca744`, published2026-10-31T06:01:32.292573Z.
- Fresh anonymous visitor path: reload/#physical-yam → Live YAM arms → editable name/email → Run on physical YAMs. No operator sign-in. Entry is context only.
- Actual Run click bracket06:02:27.070–06:02:27.330Z. Run`b1d79ff0fe8944e8ab47342bdcffbad2`, episode`ep_a41fd6cf5ebd402e`, session`sess_b0e6374a10c54309`. Model/approach`RoboSkills`; underlying`gpt-6-sol`; actual runner`Andrew Lyubovsky`; execution mode automated verification. Name/email went only to the Site and existing BluPe backend; email/capabilities stay outside public evidence. The live backend public run now shows the actual runner and RoboSkills.
- The real20mm lift/1s hold/return completed: measured rises18.064/22.063mm; lift errors1.936/2.141mm; return errors2.789/0.974mm. All within3mm tolerance. Hold-to-return preparation2.027s includes the program's1s hold. Gripper changes<0.00015. Four matched packets, including two bounded feedback corrections; no uncertain/rejected/timed-out movement was retried. Native physical score remains unset.
- Actual arms visible live beside Run and Stop. UI retained queue entry, observed completed admission, preparation, scene, model, motion and recording stages with timestamps. Final status and prior accuracy failures retained honest result/recovery.
- [Just-completed real replay](https://blupe-bimanual-skills.andlyu.chatgpt.site/api/physical/runs/b1d79ff0fe8944e8ab47342bdcffbad2/assets/physical.mp4) appeared after completion and played through the normal website. Anonymous range request206, bytes0–1023/660400. Selecting and playing previous run2ea288ea830e471a86eb6d1d98971c50, then reselecting the new run, worked.
- Timing uses original Run, matched queued response/initial grant, first episode-matched step0 homed+settled observation for both arms, and unchanged camera frames41/42 with23:03:06.0/23:03:06.8PDT clocks. Independent robot/backend clock offsets were bounded with read-only request/response receipts. Count all submission, preparation and inference. Deduct only the guaranteed queue interval≥25.949s, retaining uncertain boundary time. Conservative upper bounds: full Run→visible method motion39.813s; queue-adjusted13.865s≤30s (also≤owner's earlier15s rule); post-Home13.134s≤15s. No GPU/paper exception. This run passes both current timing measures; historical runs are not silently reclassified.
- Native status after normal policy completion: DISABLED, parked=true, torque_off_verified=true, auto_queue_enabled=true. No other run stopped.
- Validation: seven route tests passed for public admission, confirmed identity, same-origin rejection, private Stop ownership, redaction, one active run and protected worker APIs; eight launcher/progress tests passed; TypeScript and production build passed.
- Local UI capture sequence, lifecycle observations and clock receipts retained under the task's work/final-ui-proof. UI images containing private email stay local. The public replay screenshot and original physical timing frames contain no contact details. Public verification receipt and images are in codex-runner/docs/roboskills/verification/2026-10-30-no-signin-*.

Final audit: website's current public physical flow is verified. Historical every-run timing is still not fully qualified and the explicitly denied older failed clip remains local; those acceptance items stay unchecked. The native simulation failure remains honestly reviewable rather than claimed as a solved benchmark.
