# DL342 / DL343 report

Branch: DL342-pool-cache-kvm (work in progress)

## Root cause (DL342)

Confirmed by reading `rust_ci.py`. `target_cache_env()` reads `RUST_TARGET_CAP_GB` (default 40) and calls
`prune_target_cache()`. That function skips the current key and the newest other key, and only removes whole
other keys. One key directory (incremental and deps leftovers) has no ceiling, so it grows without bound.
This is the cause of the 320 GB cache.

## Status

In progress.
