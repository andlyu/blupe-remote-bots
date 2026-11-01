# RoboSkills point-cloud visibility — November 1, 2026

Invocation: “I selected ROboSkills, and could n't see any runs on the point cloud”.
The adopted shared harness selects a requested playground-fix workflow. Its
authorization-by-use contract covers the public website/source repair at
https://playground.blupe.io and https://github.com/andlyu/blupe-remote-bots.
This task performs no robot command, policy/model test, identity submission,
new recording or media upload. Existing visibility exceptions are unchanged.

## Root cause

The selected model returned 35 correctly attributed runs, but all had `xyz=null`.
The actual Cloud UI reported “35 runs. 0 mapped runs shown.” and rendered zero
points. Across the collection, 58 runs were unmapped. Earlier verification of
the cloud endpoint's run count did not establish finite coordinates or rendering.

The background mapper failed loading the actual frozen UMAP artifact:

```text
RuntimeError: cannot cache function 'rdist': no locator available
```

The website retains `ProtectSystem=strict` and `ProtectHome=read-only`. Numba
could not write its compilation cache under the installed virtualenv or home.
The existing dependencies and saved embeddings were present; this was a hosting
cache configuration failure, not a model filter or canvas problem.

## Repair and protected preflight

[Hosting PR201](https://github.com/andlyu/blupe-evals/pull/201) merged as
`139236631bf931201572631c4d066e8382e3a858`. The base service template and a drop-in
for the existing website supply:

```ini
[Service]
CacheDirectory=yam-web/task-cloud-numba
CacheDirectoryMode=0750
Environment=NUMBA_CACHE_DIR=/var/cache/yam-web/task-cloud-numba
```

Systemd owns the writable cache lifecycle. Both read-only protections, package
ownership, application/shared dependency pin, task database, embedding
model/revision and frozen projection remain unchanged. No coordinates are
manufactured or projection refit performed.

A separate transient systemd unit ran the real projector under the same strict
protections on a consistent SQLite backup. It used only the saved task
embeddings; an explicit guard rejected any new embedding inference. All 35
RoboSkills runs and all 58 previously unmapped runs gained finite coordinates.
It added 24 distinct tasks, preserved all 820 existing coordinates and the exact
projection version, and populated 46 real Numba cache files. Index runtime was
106.030 seconds; transient-service runtime 109.431 seconds, CPU 41.618 seconds,
peak memory 393.5M. Production data was untouched by this preflight. Ownership
and diff checks passed. The GitHub hosted job did not start due account billing/
spending limits (run `41352836085`); no workflow/protection setting was bypassed.
This three-file deployment/documentation change was validated by the protected
real-component test rather than new tests that merely inspect config strings.

## Live and browser evidence

Activation at 2026-11-01T21:37:35Z installed the persistent cache drop-in on the
existing website service. All four queues were empty; existing ledgers were
backed up privately. Only the website restarted, taking 4.130 seconds. Both
Spotter service PIDs stayed unchanged. The drop-in SHA-256 is
`abf18b493678605ef194a150cabed8080e8ef9cac90a859eb65ed5b790f368a8`.

The normal background index, not a copied preflight result, populated production.
Public readiness observation reached `cloud.status=ready`, `missing=0` and
35/35 finite RoboSkills coordinates after 84.387 seconds. The projection remains
`cosine-umap3-frozen-v1-d877223fed8c98be`. A production read comparison confirmed
all 820 old positions unchanged and 24 new task positions. The website and
RoboSkills metadata refresh timer remain active. No new embedding calls were
required; 844 stored embeddings were retained.

The normal browser selection displayed “35 runs. 35 mapped runs shown.” and
the actual canvas had `data-rendered-points=35`. The visible circles were
inspected in a screenshot. Those 35 runs occupy 14 distinct task positions;
the renderer's existing offsets separate repeated-task runs. These are
unlabeled records, so missing success/failure area highlights are expected.

With focus in the actual canvas, its ordinary `[` navigation focused
`ep_a41fd6cf5ebd402e`; Enter opened that point's retained recording. Its details
showed RoboSkills. The 0.8-second quick preview played to 0.401157 seconds and
sought to 0.2 seconds, readyState 4 and no media error. The control robot remained
Robo-house while the library covered All robots. No Table fallback was used for
this point-selection proof.

## Scoped acceptance

- [x] Reproduce selected RoboSkills with zero mapped/rendered points.
- [x] Identify and repair the actual protected-runtime cache failure persistently.
- [x] Real projector preflight maps new tasks without moving any existing point.
- [x] Public Cloud reports 35 finite RoboSkills coordinates and ready status.
- [x] Real canvas renders 35 points; point selection opens playable/seekable media.

This point-cloud repair is complete. The broader integration remains incomplete:
representative physical task execution, intuitive visitor flow, every-run startup
timing, all meaningful waits and final end-to-end qualification remain unchecked
in the current preserved [integration checklist](../../../integrations/roboskills/site/docs/COMPLETION-CHECKLIST.md).
Prior owner exceptions and the specifically excluded historical recording remain
unchanged. Existing replay verification does not qualify a new physical task.
