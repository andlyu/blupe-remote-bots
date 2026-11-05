# Dream1 brightness experiment

Local playground with a 0–200% slider, a **50% darker** preset and a **100% baseline** preset. Default: 50%. Every overhead and wrist image supplied to Dream1 uses the selected setting, including the observation history. Brightness stays fixed for a run; changing the control configures the next run.

This is deterministic brightness scaling, not random noise: decoded RGB channel values are multiplied by the factor, rounded down and clipped to 0–255 before the existing resize/JPEG encoder. At 50%, a channel value of 200 becomes 100. The intermediate is lossless PNG, so the experiment adds no second lossy JPEG pass. At 100%, the camera frames pass through unchanged. Dream still receives 320 × 176 JPEG quality 85 through its ordinary adapter.

## Launch

From the shared repository:

```sh
./run-dream-brightness.sh --port 8798
```

The launcher prefers the Dream-capable source in its own checkout, can reuse an existing checkout, or accepts `--runner-root /path/to/blupe-remote-yam`. It does not modify that checkout. The original physical pilot used `/Users/andrew/.codex/worktrees/0227/blupe-evals/public-projects/blupe-remote-yam/codex-runner`, revision `77cee11e0916e084e83d3b96eaadecae8eb24bd6`.

Dream uses its existing owner-only `~/.dreamlabs/credentials` file and a separate Python 3.12 environment with `dreamlabs==1.0.0` and `dreamlabs-client==1.0.0`. `YAM_DREAM_PYTHON` and `YAM_DREAM_RUNNER_ROOT` override discovery. No ChatGPT/Codex login or OpenAI API key is needed for this Dream policy. Python3.12 is required for the SDK, and Node.js is required for the JavaScript preflight. `YAM_BRIGHTNESS_UI_PYTHON` optionally selects an existing UI environment; otherwise the launcher creates `codex-runner/.venv`. The SDK environment defaults to ignored `codex-runner/outputs/dream-brightness/dream-venv`. The UI binds only to `127.0.0.1` and opens in the browser; starting the server does not join the queue or run a model.

Open **Preview the images sent to Dream1** to capture all three processed camera inputs. These are fresh previews, not the exact frames of a past inference. They use the same transformation and final encoder as the actual policy inputs. The main live view keeps its original brightness.

Choose the robot and Dream-1 beta (default) or the existing Flash option in run settings, enter the task and confirmed runner name/email, then run. The standard queue, lease, Home/readiness, command validator, limits, Stop, and replay remain owned by the existing runner. The brightness transform preserves native motion validation. The later calibration correction binds the selected native geometry into local Dream FK/IK; physical acceptance for that revision is pending. Two physical pilot trials have now run through this UI; results are retained below.

## Compare performance

Use the same checkpoint, robot, prompt, duration and starting object arrangement. Run at 100% for the baseline, restore the scene, then run at 50%. Review the retained footage and label the actual task outcome; compare time to completion, successful grasps/placements, errors and interventions. A single pair is a pilot, not a reliable success-rate estimate.

Each run records `image_experiment` in the policy's public configuration and an `image-experiment.json` file in its retained visitor directory. Local records and databases are in `codex-runner/outputs/dream-brightness/runs/<robot>/`. The per-episode `brightness-experiment.sqlite3` ledger retains immutable conditions even after the live policy is cleared. The Relative performance panel joins these records to the native reviewed outcome labels. It separates station, model, task, duration and source revisions; unscored attempts are not failures. Private email is not added to experiment metadata. Underlying model IDs remain separate from the brightness setting; the Dream alias has no verified immutable checkpoint revision.

## Verification

Run the offline preflight from the repository root. It includes actual DreamAdapter capture/encoding, preview-to-input byte equality, all three views, invalid values, 0/50/100/200%, metadata preservation and missing-identity rejection. It makes no provider request and submits no actuator command.

```sh
YAM_DREAM_RUNNER_ROOT=/path/to/dream-capable/codex-runner \
  codex-runner/.venv/bin/python -m pytest \
  codex-runner/integrations/dream-brightness/test_brightness.py -q -p no:cacheprovider
```

Also run `node --test codex-runner/integrations/dream-brightness/test_brightness_ui.cjs` to verify the actual UI request body and fixed settings. The verification passed 93 Python tests + 6 subtests and the JavaScript payload test.

Current evidence: [experiment checklist](docs/COMPLETION-CHECKLIST.md), with full integration and physical acceptance left unchecked until verified. Browser captures and test receipts are under `outputs/dream-brightness-01a1a8a1/` in the shared repository. The user asked for a local UI; no hosted deployment or public source push was performed.

## Observed pilot — November 4, 2026

Two 60-second Robo-house YAM attempts used `dreamlabs/dream-1-beta`, attributed to confirmed runner Andrew and operated/reviewed by his agent through the normal UI. The task was to pick up the green pen, put it in the cup, withdraw and hold. Both were reviewed as **Failure**: the baseline grasped/lifted but did not place/release; the darker condition also did not complete placement. The UI retains 0/1 successful attempts at 100% and 0/1 at 50%, a descriptive difference of 0 percentage points.

**This pair does not establish a brightness effect.** Another station user changed object positions between trials, so their initial scenes were unmatched. One attempt per condition is exploratory. See [trial evidence and limitations](docs/TRIAL-RESULTS.md) and the updated [completion review](docs/COMPLETION-CHECKLIST.md). The research integration remains unfinished.

Runner defaults can be supplied with `YAM_BRIGHTNESS_IDENTITY_FILE=/private/path/runner.json`, containing `name` and `email`. The file must be owner-only (0600). Both fields remain editable before queue admission. Keep that file and private contacts out of public source/evidence.

Required offline release preflight (no model or physical calls):

```sh
YAM_DREAM_RUNNER_ROOT=/path/to/dream-capable/codex-runner \
YAM_CANONICAL_TRAJECTORY=/path/to/deployed-joint-trajectory.py \
  codex-runner/integrations/dream-brightness/verify.sh
```

The latest release preflight passed **45 Python tests and 1 JavaScript test** against the retained deployed canonical parser (SHA256 `1c640b6d144d8b55c2a77ae584e71a91cb50d036ddc5d548fe4d656dd5d74483`). Earlier broader Dream/transport verification passed 93 tests + 6 subtests. Terminal metadata regression checks verify the actual model and conditions survive shutdown, retain the original executed source revision, and do not rename another user's run. Controller decision timings include capture/inference/IK; they are not pure provider inference time.

## Public source and retained evidence

The public source package is additive to [blupe-remote-bots](https://github.com/andlyu/blupe-remote-bots). A clean snapshot of main at `27824217353a0820bed6c0e59c1b3c2563077cf3` passed all45 focused Python checks with this extension and launched its own source successfully. Installed UI/SDK environments were reused for that smoke check; this is source reproducibility evidence, not a fresh dependency-install benchmark.

The [evidence directory](evidence/) contains the two physical replays, timestamped UI frames, reviewed outcomes, dependency pins and test receipts. Identity-setup screenshots and private storage are excluded. The [CI workflow](../../../.github/workflows/dream-brightness.yml) runs the offline release gate against the retained deployed validator snapshot, without provider credentials, network inference, queue entry or physical dispatch. Future physical releases must verify their actual deployed validator again.

On the current room layout, use **Inputs 50%** beside the model/run buttons to open brightness, preview and relative-results settings. The earlier playground layout keeps the panel above the cameras. This integration supports both shared layouts without changing their robot controls.

## Selected calibration and connection failures

The local Dream adapter now reads the operator-selected Robo-house model and camera calibration before admission, after lease grant and before each prediction. Geometry is generated from the hash-pinned controller model; feedback and commands remain original encoder values. A changed or unsupported profile stops the run before another prediction. The Inputs dialog shows the last checked selection, and executed runs retain their actual binding. See [calibration design and software evidence](docs/CALIBRATION-BINDING.md). Earlier physical trials predate this correction.

Dream response-header connection failures are retained as infrastructure failures and excluded from brightness success rates. The UI explains the interruption without retrying the model or movement.

Current required preflight: **70 Python tests and1 JavaScript test**, including calibration geometry, the real camera-origin bridge and the actual deployed packet validator. See `evidence/calibration/publication-preflight.xml`. The [connection-failure investigation](docs/CONNECTION-FAILURE.md) separates the observed HTTP interruption from calibration behavior.

## Hosted extension boundary

`make_runner_type(root, local=False)` disables local identity defaults and labels a public deployment accurately. A configured local private identity file is rejected in this mode before it is read. Hosting can pass a persistent `experiment_root` for the immutable brightness ledger; full visitor recordings continue to follow the shared runner's existing retention rules. BluPe-specific guest allowance and deployment wiring live in `apps/blupe_web` in the parent project. Native queue, lease, validation, duration, Stop and replay behavior are preserved.

The required shared release preflight now passes72Python tests plus the actual UI request/response test. The added regressions cover public identity isolation and ledger persistence across ephemeral visitor roots. Hosted rollout is verified separately; this source change does not claim a public deployment or physical run.
