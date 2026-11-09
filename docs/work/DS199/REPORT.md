# DS199 report: tool fetcher

## What changed
- `ci_tool.py`: new `tool <name> [--platform P] [--exe NAME] [--dir]`. Reads `tools.json` (env `CI_TOOLS_JSON` overrides the file, for tests). Pin shape: `{"version", "platforms": {<plat>: {"kind", "url", "sha256", "file"?, "bin"?, "bin_dir"?}}}`.
  - `file`: one download, cached, made executable (rustup-init).
  - `archive`: tar.gz/tar.xz/zip, verified, unpacked once into `<tool>/<version>/unpacked-<plat>/` (path-escape, link-escape and device members are refused). Prints `bin_dir/<bin>`, or `bin_dir/<exe>` with `--exe`, or the bin folder with `--dir`.
  - `crate`: the `.crate` is verified, unpacked, built once with `cargo install --locked --path <src> --root <tool>/<version>/root-<plat>` (env `CI_TOOL_CARGO` names cargo). Bin is in `root-<plat>/root/bin`.
  - Unpack/build goes to a unique `.partial` folder and is renamed; a failure leaves nothing. Windows adds `.exe`.
  - `fetch` and `gitleaks` are unchanged; the gitleaks pin in `tools.json` is byte-identical in shape.
- `tools.json` new pins (sha256 from upstream checksum files or the crates index; rustup-init linux_x64, both crates and the LLVM linux_x64/arm64/windows_x64 archives were downloaded and hashed here):
  - `rustup-init` 1.29.3, five platforms.
  - `llvm` 20.1.8: linux_x64, linux_arm64 (`LLVM-20.1.8-Linux-*.tar.xz`), windows_x64 (`clang+llvm-20.1.8-x86_64-pc-windows-msvc.tar.xz`). Checked in the archive listing: `lld-link`, `clang-cl`, `llvm-lib` exist in `bin/`. linux_arm64 folder name `LLVM-20.1.8-Linux-ARM64/bin` follows the x64 naming and was not listed.
  - `cargo-deny` 0.20.2 and `cargo-xwin` 0.23.1 (crate sha256, all five platforms).
- `tools_pin.py`: new `rustup-init`, `crate` and `entry` commands; they merge into `tools.json`.
- Tests: `claude/plugins/delivery/tests/test_ds199_tool_fetch.py` (local file:// fake archives, fake cargo).
- Change note: `docs/architecture/changes/DS199-tool-fetcher.md`.

## Left out
- **Zig**: ziglang.org, its mirrors and codeberg returned 403 from this environment, and GitHub has no release assets for it. No Zig pin; add it with `tools_pin.py entry zig ...` once a URL can be hashed. Doctor/rust_ci tasks must treat `zig` as not pinned.
- LLVM darwin: not pinned (not needed for the Linux/Windows cross-link).
- Real `cargo install` of the pinned crates was not run (no Docker or long builds); only a fake cargo is tested.
- Linux LLVM extracts to several GB; a later task may want a `members` filter.

## Behaviour for the spec text
`python3 scripts/delivery/ci_tool.py tool llvm --exe lld-link` prints the absolute path of that file in the cache, fetching and unpacking on first use. Exit 0 path printed, 1 fetch/checksum/unpack/build failure or missing exe/pin, 2 usage.

## Tests
- `cd claude/plugins/delivery/tests && python3 -m unittest test_ds199_tool_fetch test_dl115_ci_tool test_dl116_fetch_check`: 37 tests OK.
- `python3 tools/ci_areas.py --branch-advice`: heavy area `delivery`.
- `gh workflow run spec-lint.yml --ref DS199-tool-fetcher -f areas=delivery` (run 42651070392): conclusion **cancelled**. The "docs check" job failed first (M1: feature specs delivery and delivery-speed map to the changed code; the spec text is a later docs task; W1: docs/work file, expected), which cancelled the two delivery test jobs. Area mapping, ledger/recorder/watcher, setup preflight and train cleanup jobs passed. The delivery CI-scripts job did not finish, so the heavy area is **not** confirmed green by CI.
- `docs_check.py`: 3 errors (M1 x2, W1 expected) and 1 warning (T2 spec older than code), all from the spec text still to be written.

Branch head: see the last commit on `DS199-tool-fetcher`.

NOT READY
