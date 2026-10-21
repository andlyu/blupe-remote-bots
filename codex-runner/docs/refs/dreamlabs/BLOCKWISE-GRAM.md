# Blockwise normal-equation integration

Read the installed SDK1.0.0/JAX0.7.1 sources before implementation, October20,2026.
The pinned wheel's jaxls/_solvers.py `NonlinearSolver.lm_inner_step` calls
`A_blocksparse.to_dense()` followed only by `A_dense.T @ A_dense` in the dense
Cholesky branch. jaxls/_sparse_matrices.py documents batched SparseBlockRow
blocks, their starting columns, and the later-block-overwrites-earlier behavior
of to_dense. jaxls/_problem.py constructs the row groups and variable layout.
Exact complete-file SHA256 contracts are retained in dream_ik_blockwise.py;
the SDK source is not copied into this repository.

The existing arithmetic needlessly multiplies structural zeros: a captured
48-tick/two-arm problem expands to53,136x576 floats. Gram assembly from each
small row block retains the objective and the original576x576 Cholesky solve.
Floating-point reduction order changes, so output is not promised bitwise equal.
The selected implementation is `blockwise_gram_f64_v2`: assembly and the
unchanged Cholesky solve retain float64 instead of rounding back to float32.

The adapter intercepts just this verified Gram operand. Other linear solvers
and Schur paths call the original implementation. Overlapping columns preserve
the pinned to_dense overwrite contract. No optimizer source is rewritten or
evaluated, and no callbacks are added to the compiled graph.

Set YAM_DREAM_BLOCKWISE_IK=1 in the isolated worker environment to activate.
Unset/0 retains dense behavior. The worker sets JAX_ENABLE_X64=1 before importing
the SDK or creating any JAX values. JAX0.7.1 documents this as a program-wide
startup setting (docs/default_dtypes.md at tag jax-v0.7.1); a scoped precision
context inside jit/grad is not used. This changes SDK numerical precision,
including its other IK kernels. Installation requires X64 and validates JAX/JAXLIB
versions and all three source files before first client configuration/warmup.
Unknown versions fail preparation with a fixed error, not a guessed patch.
Prime/configure replies name the actual selected implementation. A worker must
restart when changing the switch; already compiled executables are not reused
under a different graph. Existing cache keys follow the changed computation.

This is an algebra optimization, not a change to coupling, obstacles, objective
weights, damping, convergence, SDK branch selection, native checks or motion
limits. Synthetic and saved-input validation do not establish physical task
readiness or a fix for an unrecorded historical timeout.

Broader offline validation of the first float32 candidate exposed nonlinear sensitivity: a synthetic5cm
target shift changed one joint by0.211rad and increased the unchanged full
objective by5.21%, while predicted tool translation differed by5.5mm. Other
saved/shifted/shorter cases had much smaller differences. Compensated float32
reduction did not eliminate that regression and doubled local runtime, so it
was not selected. Whole-kernel recompile controls also changed numerical output;
holding the same analyzed problem layout fixed is necessary to isolate algebra.

The float64 remedy was compared against dense float64 on five fixed analyzed
problems (saved coupled input, independent branch,1cm/5cm target shifts,12ticks).
Maximum joint difference was2.8e-12rad. Against float32 reference solves, the
largest observed difference was0.00110rad (0.063degrees), predicted tool delta
0.056mm, and full-objective change0.006%. No iteration or factorization budget,
damping, stopping criterion, weights or collision terms changed. A fresh exact-SDK
synthetic startup prepared both48tick kernel forms, producing finite float64
arrays. These offline measurements do not establish physical task performance
or cloud latency; activation still requires its normal deployment verification.
