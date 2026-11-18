# Controller / simulation handoff

The source23a1aac5 worker accepted a run as complete when the agent simulated
one controller and then wrote different source without another simulation.
The saved controller hash differed from its report's controller hash. This
was reproduced through actual run_agent with a scripted SDK/engine, not a
Google or robot request. The baseline red receipt and source hashes are in
`evidence/controller-handoff`.

Each executor now captures the exact controller and station bytes before
launch. After confirmed removal of its uniquely named container, it retains
those originals, report, replay, command packets, bounded log and a host-created
execution receipt outside the generated-code mount. A changed input, mismatched
report, failed process or unconfirmed cleanup cannot qualify that execution.
These are source/replay consistency checks, not task-success certification.

A different controller write invalidates the previous eligible simulation; an
identical byte-for-byte write preserves valid evidence. Final preparation checks
the current controller and station against the accepted host receipt. Every new
simulation restores the original captured station from host evidence, rather
than accepting a scene changed by a previous generated controller. Atomic writes
replace owned job filenames without following symlinks or blocking on FIFOs.
After actual unconfirmed cleanup, the same executor cannot launch another attempt
until cleanup is confirmed. Bounded removal/exists checks reuse the existing
Podman4.9.3 channel commands; hardware limits, safeguards and queue are unchanged.

All attempts stay retained and are served through the authenticated site gateway
with digest checks, even when later attempts replace their source. The Simulation
panel selects the latest replay and links older attempts separately. History
selection brings its actual details tab into view; unchanged artifact links stay
stable during status refresh.

Required preflight covers source edits, identical-source reuse, scene restoration,
zero-exit/report forgery, symlink/FIFO/size handling, timeout cleanup, cleanup
failure, retained historical artifact bytes and authentication. Removing or
skipping required binding coverage fails the release. The executor tests use a
trusted local engine double, not an actual Podman image. A local UI fixture played
a prior handwritten4.3s engineering replay at320x180 and exposed both attempts'
links; it is not a real hosted model run or physical acceptance.

For the baseline red reproduction, export the exact original public worker:

```sh
git show 23a1aac5:codex-runner/integrations/gemini-blupe/backend/gemini_worker.py > /tmp/gemini-baseline-worker.py
python tools/reproduce_unbound_handoff.py --worker-file /tmp/gemini-baseline-worker.py --runner-root ../..
```

Expected baseline exit1 reports `complete != failed`. The current required
`python tools/preflight.py --runner-root ../..` must pass. Use the documented
isolated Python3.12/Google/MuJoCo environment, not the API-only venv.

Production API remains e075e8d3 and selected Google credits are unavailable. The
new host executor still needs actual qualification on the existing worker after
SSH access returns. The image65f9521a runtime's eight pinned source files are
unchanged. YAM1 source is offline; model-generated task, matched scene/contact,
production physical orchestration, native physical checks, onset and physical
replay acceptance remain open. Physical Run is still unavailable; checklist1/17.
