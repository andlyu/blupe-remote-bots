# JAX 0.7.1 persistent compilation cache

Source: official JAX repository at `jax-v0.7.1`, matching the installed JAX/jaxlib0.7.1. Fetched2026-10-19; Apache-2.0 (`LICENSE`).

- Configure before first compilation, using `JAX_COMPILATION_CACHE_DIR`: [upstream guide](persistent_compilation_cache.upstream.md), Setting cache directory.
- Cache thresholds: same guide, Caching thresholds. Dream IK1.0.0 sets the minimum compile time to0.5s.
- Cross-process reuse/invalidation: How it works and Caching on multiple nodes. Keys include computation HLO, jaxlib version, relevant XLA flags, device topology and compression.
- Limitations: Pitfalls. Tracing/setup still happens in each new process; this is not a saved live model session.

Integration: retain fresh per-visitor workers and work directories; honor an explicit trusted service cache path instead of unconditionally overriding it with visitor-local `/tmp`. The hosted cache is service-owned0700, with0600 entries. No images, measured observations, commands, episode IDs or SDK sessions are cached here. Upgrade the deployment namespace with SDK/runtime/robot-solver configuration changes; JAX additionally keys compiled computations and runtime details internally. The local IK target remains YAM/EEF/traj at20Hz.


Attribution-only probes may time `jax._src.compiler.compile_or_get_cached`, `backend_compile_and_load`, and persistent-cache hit/miss callbacks in the verified JAX0.7.1 runtime. These private functions are instrumentation, not production reuse APIs. Installed `jax/_src/compiler.py` SHA-256: `6e4a2a4942274752c2baaf5d4233587807494b09636d092b4ae77a58eb291c55`; authoritative source: https://github.com/jax-ml/jax/blob/jax-v0.7.1/jax/_src/compiler.py (checked2026-10-19). Disk-cache hits still permit graph tracing/Python setup. Resident supported SDK policies avoid reconstructing that state for every visitor.
