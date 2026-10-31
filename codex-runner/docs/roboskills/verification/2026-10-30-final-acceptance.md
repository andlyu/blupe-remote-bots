# Final RoboSkills acceptance audit

Reviewed 2026-10-31T06:35:11.310491+00:00. **15/15 checked**, with the two explicit owner archival exceptions recorded below.

Website: https://blupe-bimanual-skills.andlyu.chatgpt.site/#physical-yam
Tested deployment: v13, source `01bac7438e6284716b0f85fd2ce158f2f20ca744`; physical run `b1d79ff0fe8944e8ab47342bdcffbad2`.

| # | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Website and associated source | PASS | Public Site v13; source01bac7438e6284716b0f85fd2ce158f2f20ca744; associated public repository code merged inPR177. |
| 2 | Public demo and source | PASS with explicit archive exception | Site access_mode=public and GitHub isPrivate=false; current physical replays and simulation artifacts open anonymously. Original failed development clip453a9a is excluded by the latest owner scope decision and remains local. |
| 3 | Actual method clearly named | PASS | RoboSkills labels match executed RoboSkillsPolicy; foundation inference gpt-6-sol is separate. Live adapter source matches public main byte-for-byte. |
| 4 | Confirmed editable human name/email | PASS | Anonymous physical form exposes editable required fields. Known account defaults are used when available. Current normal-UI run confirmed Andrew Lyubovsky and the existing email; public projection excludes email. |
| 5 | Approach and runner in run context | PASS | Runb1d79ff0fe8944e8ab47342bdcffbad2 and captured live backend feed name Andrew Lyubovsky and RoboSkills; same identity in replay/history. |
| 6 | Human attribution distinct from execution mode | PASS | All six retained physical run records name the actual human. Audit metadata identifies automated verification separately; model=RoboSkills and underlying inference IDs stay separate. |
| 7 | Method runs on physical YAMs | PASS | Normal public UI runb1d79f executed pinned upstream core.agent.run/Repl through BluPe measured tools.20mm lift,1s hold and return all within3mm; four matched packets, no uncertain-motion retry. |
| 8 | Actual arms visible live | PASS | Live camera visible during the physical run; current fixed public top-camera endpoint returns200 JPEG; station and runner online. |
| 9 | Immediate just-completed replay | PASS | Newb1d79f replay appeared after completion and played through normal website UI; retained29.5s MP4 and anonymous HTTP206 verified. |
| 10 | Previous-run browsing and replay | PASS | Selected and played earlier2ea288 run, then reselected the new run through physical history. |
| 11 | Simulation executions reviewable | PASS | Native-lift-20261030 has public receipt, generated task.py, workflow result and real replay. Build rejection/demo8of8/solver-not-run are shown honestly, separate from physical footage; source/upstream examples credited. |
| 12 | Usable visitor path | PASS | Live YAM arms → editable name/email → Run on physical YAMs. No operator sign-in. Original15-item checklist retains this fulfilled diagnostic; latest shared harness no longer adds a separate visitor gate. |
| 13 | Every-run startup timing | PASS with explicit historical exceptions | Currentb1d79f conservative upper bounds:13.865s after Run excluding only guaranteed queue wait and13.134s after measured Home readiness. Owner accepted the fixed five pre-version-13 timing failures/missing measurements as historical exceptions. Original failures remain visible; all future runs retain15s/30s limits. |
| 14 | Persistent honest progress and recovery | PASS | Run immediately shows submission then queue/admission, preparation, scene/model, measured motion and saving replay, retaining observed timestamps. Stop available on owned run. Connection recovery clears stale errors; real failures retain measured reasons. |
| 15 | Final normal-UI physical verification | PASS | Final functional deployment v13 was tested end-to-end by anonymous normal UI, with live footage, timing, actual attribution, new/prior replay and native parked/torque-off evidence. Current Sites version/source is unchanged; subsequent changes are audit documentation only. |

## Method fidelity

The physical provider imports the exact pinned upstream RoboSkills agent and invokes its genuine persistent Python REPL loop. Live RGB and measured arm tools connect it to BluPe. Simulation demonstrations and the native build/check receipt are separately labelled and reviewable. This is a physical tool adapter; it does not advertise the entire upstream RoboKit/SAM surface or a paper benchmark score. The native simulation build failure remains visible.

## Explicit owner exceptions

1. “Accept historical exceptions”: fixed five pre-version-13 runs retain their original failed/unverified timing outcomes. Current v13 passes normally; future runs keep the15-second post-Home and30-second queue-adjusted Run targets.
2. The owner said the original failed clip “simply doesn’t matter” and directed focus to method fidelity and the15 requirements. That one old development clip is outside the required public archive, remains local and is no longer an unfinished release item. The prior specific upload denial is preserved; no upload was retried. This introduces no new privacy concern.

Current deployment and source were rechecked. Public method/replay/simulation endpoints passed; repo/sourcePR177 is public and merged with all four checks successful. No functional changes followed the tested v13 deployment.

Supporting receipts:2026-10-30-no-signin-final.json,2026-10-30-no-signin-lifecycle.json,2026-10-30-all-runs-audit.json and2026-10-30-final-public-checks.json.
