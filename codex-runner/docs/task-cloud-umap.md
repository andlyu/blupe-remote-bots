# Frozen UMAP task-cloud release

User invocation: “Lets deply UMAP isntead of PCA” and “Get it ready and ship”, after reviewing the UMAP preview with the existing MiniLM embeddings. User-adopted AGENTS.md selects the shared harness.

Scope: public https://playground.blupe.io/, shared source https://github.com/andlyu/blupe-remote-bots and hosted integration https://github.com/andlyu/blupe-evals. This changes task-description indexing and its display only. No robot/control/model-policy test, identity submission, assessment change, new recording or simulation is required. Existing task IDs, replay links and outcome labels are retained. The selected embedding checkpoint stays unchanged; the user selected the tested UMAP layout and parameters.

## Acceptance evidence

- [x] Tested UMAP parameters: 3 components, cosine, 15 neighbors, minimum distance 0.05, random/transform seeds 42, one job. Trusted frozen artifact includes the 487 reviewed unique public tasks.
- [x] Packaged coordinates match the reviewed preview exactly before uniform display normalization (maximum difference zero). Source builder and provenance retain the public catalog digest, exact model checkpoint, library versions and coverage; 21 uncached unique tasks from the saved sample were excluded from the fit.
- [x] Existing fitted coordinates never move for new arrivals, model/outcome/review changes, archive order or filters. Single-task transforms keep arrival-batch composition from affecting positions; cache/restart and finite-coordinate tests pass.
- [x] Prior PCA projection/coordinate records are retained. A changed map version clears stale in-memory selection geometry; ordinary same-version filtering/refresh preserves geometry.
- [x] Invalid and zero-norm vectors and corrupt model checksums cannot publish positions. Bundled coordinates load without model inference; indexing/loading remains in the background and errors retain Table recovery.
- [x] Focused indexing tests: 6 passed. Cloud interaction regressions: 34 passed.
- [ ] Required complete shared Python/Node checks and review.
- [ ] Shared source published and merged; hosted pin/integration validated and published.
- [ ] Actual deployment dependencies and serialized artifact verified on Linux; current public asset/source baselines retained.
- [ ] Idle-guarded activation with rollback copy; existing queue/lease, Stop, robot limits and records untouched.
- [ ] Public deployed map reports UMAP and ready status; current archive coordinates finite, old/fitted coordinates stable.
- [ ] Live desktop/phone rotation, selection, hover/replay and outcome/region controls verified; screenshots and final source/deployment evidence retained.

The shared harness was reviewed for this scoped playground fix. Its website/source/public-delivery, honest waiting/recovery, public evidence and source-review requirements apply here. Physical control gates, human queue identity, Run/Home/motion timing, representative physical manipulation, new-run recordings and simulation requirements are not applicable because this release executes no robot method or new physical test. Existing playback is checked as a UI regression. This is a layout release, not a claim that a new robot research integration passed physical acceptance.

## Applicable authorization contract

### Authorization granted by using this harness


The owner gives standing authorization to run on BluPe remote bot arms as part
of requested work through this harness. A requested research integration,
playground fix, verification or arm run invokes the covered workflow below;
no separate authorization for the run is required. A task requested under
user-adopted instructions that select this harness also counts: retain the task
request and the selecting instruction as the invocation evidence. Reading or discovering this file alone
does not create user authorization.

For that requested task, using the harness authorizes:

- Joining the normal robot queue and submitting the runner's already-confirmed
  name and email to the task's integration website and its existing BluPe
  queue/run backend for queue admission, run attribution and normal run
  notifications.
- Starting the selected method on the task's physical robots/arms and performing
  bounded actual arm movement within the existing run limits.
- Capturing and retaining camera recordings, checking live footage and
  replay/history, and using Stop and normal parking/lease release.
- Creating and publishing the integration's public source repository, committing
  and pushing its source, and deploying or updating its publicly hosted website.
  Use the normal repository and hosting visibility controls to make both public;
  the intended audience is anyone on the internet. Publish the demo's approach
  and configuration, runs/results, live demos, recordings, replays/history,
  simulation outputs and supporting evidence. Keep credentials, access tokens
  and private contact details out of public source and demo materials.

These actions are part of the invoked workflow. Do not ask for separate
permission for covered identity submission, runs, movement, recording, public
hosting or source publication. Public delivery is an authorized requirement of
the integration request; it does not require another publication confirmation.
Reuse confirmed identity/defaults; ask only for missing or ambiguous identity
or scope outside this contract. Keep execution mode separate from human
identity. The grant covers the task's integration and existing queue/run
destinations and the integration's public hosting/source destinations. Keep
private email out of public materials and do not send it to unrelated recipients.
Do not invent a person's name or email. Preserve any explicit user limits or
revocation and copy this contract into the integration's checklist.

