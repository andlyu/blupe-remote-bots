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

The adapter intercepts just this verified Gram operand. Other linear solvers
and Schur paths call the original implementation. Overlapping columns preserve
the pinned to_dense overwrite contract. No optimizer source is rewritten or
evaluated, and no callbacks are added to the compiled graph.

Set YAM_DREAM_BLOCKWISE_IK=1 in the isolated worker environment to activate.
Unset/0 retains dense behavior. Installation validates the pinned JAX/JAXLIB
versions and all three source files before first client configuration/warmup.
Unknown versions fail preparation with a fixed error, not a guessed patch.
Prime/configure replies name the actual selected implementation. A worker must
restart when changing the switch; already compiled executables are not reused
under a different graph. Existing cache keys follow the changed computation.

This is an algebra optimization, not a change to coupling, obstacles, objective
weights, damping, convergence, SDK branch selection, native checks or motion
limits. Synthetic and saved-input validation do not establish physical task
readiness or a fix for an unrecorded historical timeout.

Broader offline validation exposed nonlinear sensitivity: a synthetic5cm
target shift changed one joint by0.211rad and increased the unchanged full
objective by5.21%, while predicted tool translation differed by5.5mm. Other
saved/shifted/shorter cases had much smaller differences. Compensated float32
reduction did not eliminate that regression and doubled local runtime, so it
was not selected. Activation needs acceptance of this larger observed behavior
or a numerical remedy; the original tiny-difference replay alone is insufficient.
