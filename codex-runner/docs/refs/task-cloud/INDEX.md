# Task cloud reference index

Fetched October 28, 2026. These upstream references were read before implementation.

| Use case | Version / authoritative guidance |
| --- | --- |
| Sentence semantics, 384 dimensions, normalized vectors, 256-wordpiece truncation | [MiniLM model card](minilm-model-card.md), Apache-2.0 model `sentence-transformers/all-MiniLM-L6-v2`, immutable revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf` |
| CPU loading, pinned revision, explicit no-token/no-remote-code load, batch encode | [SentenceTransformer 5.1.2 constructor/encode API](sentence-transformer-v5.1.2.py.txt); upstream Apache-2.0, https://github.com/huggingface/sentence-transformers/tree/v5.1.2 |
| Centered principal components, right singular vectors, reduced SVD | [NumPy 2.2.6 SVD docstring](numpy-svd.rst); upstream BSD-3-Clause, https://github.com/numpy/numpy/blob/v2.2.6/LICENSE.txt |
| Canvas context, pointer-space picking, browser redraw | [MDN Canvas example](canvas-example.html), https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D (read current reference; upstream example CC0) |

`task_cloud.py` uses `SentenceTransformer(..., revision=..., device='cpu', token=False,
trust_remote_code=False)` and `encode(..., normalize_embeddings=True)`. It uses
NumPy (already a runner dependency via SciPy/MuJoCo), without a new projection or
rendering library. The Canvas view applies genuine xyz rotation and perspective;
its xy pixels are a camera projection of persisted 3D data.

## Frozen projection

`config/task-cloud-projection-v1.json` contains a centered PCA3 basis learned from
243 unique normalized public task descriptions (602 archive records fetched
October 28). Repeated attempts have equal representation weight, and model,
outcome and votes are never inputs. Initial fit uses sorted task hashes, normalized
MiniLM embeddings, `numpy.linalg.svd(matrix - mean, full_matrices=False)`, the first
three right singular vectors, and deterministic axis signs. Its fingerprint is
`centered-pca3-frozen-v1-7c3bdcfdde42cf96`. The bundled basis makes local and hosted
instances share the same coordinate system. New text is embedded and transformed
with the same frozen mean/basis. It never refits on browsing, filtering, reviews,
or new arrivals. Embeddings and xyz coordinates are cached in a separate SQLite
index keyed by representation and projection versions. Explicitly releasing a new
representation/projection requires a new version; keep the prior index for audit.

PCA preserves broad linear variation, not all high-dimensional neighborhoods.
Nearness is descriptive text similarity, not proof of equal task difficulty or
initial state. Long prompts are truncated by MiniLM. No embedding provider call,
API key, user account, model label, vote or machine outcome is used.

## Operations and failure states

The first Cloud request schedules indexing of the complete archive on a background
daemon. HTTP responses and robot control do not wait on encoder loading or inference.
Install the pinned `sentence-transformers==5.1.2` from runner requirements; existing
launchers check for it. The first index downloads the public model (about 90 MB)
into the index directory's `task-model/` cache. A missing dependency, offline first
load, or indexing failure produces an explicit Cloud error and keeps Table usable.
Retry occurs at most once a minute. Production may prewarm by calling
`TaskCloud(path).index(PastRuns(robot_id=None).page(metadata=True)['runs'])` in its
existing environment before serving traffic. The Cloud catalog never fetches episode detail or recording media; only
the hovered/focused point and full replay selection use the existing detail API.
Hover owns one muted recording and cancels stale detail/playback work. Table enriches only 12 visible recording blocks
with the incumbent preview metadata, independently of complete-data scoring.

Persist `YAM_ASSESSMENT_DATABASE` and `YAM_TASK_CLOUD_DATABASE` in the deployment's
state volume, shared by fleet runner instances. Defaults are runner `data/`.
SQLite serializes mutations and projection publication across processes. Back up
the assessment overlay independently of the public recording archive.

## Display and scores

Table pages contain the incumbent 12 recording blocks with video previews. Cloud draws up to the newest 10,000
filtered runs and explicitly discloses any limit and missing indexed coordinates.
Every drawn attempt is individually reachable with Previous/Next and keyboard
brackets, including exact duplicates. Small deterministic episode-ID offsets are
visual disambiguation only. Rotation/zoom never change cached task coordinates.
Scores always use the complete filtered dataset before either display limit.
Eligible Success/Failure runs are green/red filled dots. Unlabeled and excluded
runs are the same hollow, unscored visual group; details retain the original label
and exclusion reasons. Eligibility changes only the fill, never coordinates.
