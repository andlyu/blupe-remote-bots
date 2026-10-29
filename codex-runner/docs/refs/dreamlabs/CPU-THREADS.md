# Local IK BLAS thread control reference

Read2026-10-29 before the YAM1 offline benchmark. Existing SDK1.0.0/JAX0.7.1
uses NumPy/SciPy OpenBLAS libraries; no solver/dependency change is proposed.

Primary OpenBLAS reference:
https://www.openmathlib.org/OpenBLAS/docs/runtime_variables/
(runtime-variable documentation dated2026-02-09, accessed2026-10-29).
`OPENBLAS_NUM_THREADS` selects the startup thread count for pthread builds;
OpenMP builds use `OMP_NUM_THREADS`. `OPENBLAS_DEFAULT_NUM_THREADS` covers both.
Set the selected variable before importing/initializing the library. A setting
in a dedicated Dream SDK subprocess does not reconfigure the controller process.

Primary SciPy reference:
https://docs.scipy.org/doc/scipy/tutorial/parallel_execution.html
(SciPy1.18 documentation, accessed2026-10-29; general threading contract, not an
assertion that the installed runtime is1.18).
SciPy's BLAS/LAPACK-backed calls can use library-managed native thread pools.
Its thread behavior differs from ordinary Python execution. Measure the complete
unchanged IK solve and numerical output before selecting a worker-only setting.

These references explain the control; they do not establish that a thread limit
is faster on YAM1. Recorded-action/synthetic offline measurements must do that.

## October29 YAM1 measured result

The exact SDK1.0.0, JAX0.7.1, float64 blockwise solver was replayed on five
48-row/two-arm FK target paths derived locally from the recorded command samples
of ep_bbcb5898d231470d, three repetitions each. Both variants fully prepared
independent/coupled kernels first. Six-thread BLAS median2.304s; one-thread
median0.1166s. All15 joint outputs matched within1.27e-13rad. No weights,
convergence rule, speed, acceleration, collision or workspace constraint changed.
These are offline solver timings, not a measured post-fix physical pause.

The SDK child now defaults OPENBLAS_NUM_THREADS to1 before SDK/NumPy imports.
An explicit inherited value is retained. The controller process, camera workers
and other adapters are not reconfigured. The serial controller still completes
and settles the previous chunk before predicting the next; provider latency,
fresh-input waiting and validation/dispatch can therefore still produce holds.
