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
