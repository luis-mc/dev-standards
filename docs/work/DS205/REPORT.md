# DS205 report: Zig pin

## What changed
- `tools.json`: `zig` 0.17.1 from the `ziglang` PyPI wheels (sha256 from the PyPI JSON API): linux_x64 (manylinux_2_12 x86_64), linux_arm64 (manylinux_2_17 aarch64), windows_x64 (win_amd64), darwin_x64, darwin_arm64. Entry: `kind wheel`, `bin_dir ziglang`, `bin zig`.
- `ci_tool.py`: new `wheel` kind. A wheel is unpacked as a zip (path-escape refused) and the exec bit stored in the zip entry is restored. `archive` could not do this: it treats `.whl` as tar and drops the mode.
- `tools_pin.py`: `--kind wheel` accepted by `entry`.
- `rust_ci.py`: the Zig warning and the cc-not-found fix text now say the pin is missing (Zig optional only then), not that Zig is not pinned in general.
- Tests: `tests/test_ds205_zig_pin.py` (4: fake wheel, exec bit, windows .exe, bad sha, shipped pin shape).
- Notes: `docs/architecture/changes/DS205-zig-pin.md`, `docs/features/delivery-speed/changes/DS205.md`.

## Verified for real
- Downloaded the linux_x64 wheel: sha256 `ea6cc5d8...4524b54` matches PyPI. `ci_tool.py tool zig` fetched it, printed `.../unpacked-linux_x64/ziglang/zig`, and `zig version` prints 0.17.1.
- Other platforms' hashes come from PyPI, not downloaded.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_ds205_zig_pin test_ds199_tool_fetch test_ds200_rust_ci test_dl115_ci_tool`: 41 tests OK.
- `docs_check.py`: 1 error (W1, docs/work files, expected), 1 warning (T2 delivery-speed spec older than code). M1 passes.
- `gh workflow run spec-lint.yml --ref DS205-zig-pin -f areas=delivery` (run 42680459420): conclusion failure, from `docs check` only (W1 docs/work, expected). All 11 delivery jobs succeeded: train cleanup, branch gate and trust rule, CI scripts and workflow templates, area mapping, setup preflight, packaged-program smoke test, change notes enforced and folded, runner plan, plugin ledger/recorder/watcher/hooks, artifact pruning, scripts/CI templates/cleanup/prune/change notes. Other jobs skipped.

## Notes
- Zig messages in `rust_ci.py` keep the words "zig is not pinned" (the DS200 test checks them) but now only fire when the pin is missing.
- The DS202 doctor strings from the DS200 report should now use `python3 scripts/delivery/ci_tool.py tool zig`.

Branch head: see `git log -1` on origin/DS205-zig-pin.

READY
