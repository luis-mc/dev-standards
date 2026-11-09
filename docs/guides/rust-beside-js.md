---
title: Rust beside a JS stack
type: how-to
---
# Rust beside a JS stack

Use this guide to decide whether a part of a JS product should be written in Rust, and to see what `luismc-project-setup` and `luismc-delivery` give you when it should. The rules are in the [project setup spec](../features/project-setup/spec.md) and the [delivery spec](../features/delivery/spec.md). The plan with the owner decisions is in [rust-beside-js-plan](../architecture/rust-beside-js-plan.md).

The default is to stay in the main language. Rust needs a written reason. The wizard records it in the Stack Profile. No measured number is required.

## When Rust fits

| Part | Pick it when | Avoid it when | How it connects |
|---|---|---|---|
| Command-line tool | One static binary must run where no runtime exists, or startup time matters. | The script runs only where Node or Python already exists. | A separate binary. The task shim calls `cargo`. |
| Host service or installer helper | Code runs on user machines, needs OS services, pipes or file locks, and must behave the same on three OSes. | The helper wraps one OS call that a script handles. | A separate binary. A local pipe, socket or localhost HTTP. |
| Library in a JS app (napi or WASM) | A measured hot loop misses a stated target. | The cost is I/O or the database, or no profile exists. | napi addon, WASM file or a worker binary. |

Workers and media processing are not offered yet. They come when a project asks. Rust does not fit admin UIs, CRUD APIs on a serverless host, glue to vendor SDKs, or a team with no Rust skill.

## What the wizard asks

`tech-stack-setup` asks in Phase 1 whether any part of the product runs on a user's or operator's machine. A yes opens the role `native_components` in Phase 3. It is multi-select and the default is none. For each part it asks:

- The reason, in writing.
- The target OSes, and which ships first.
- Where it is built: the same runners, or a cross-build.
- For a napi addon: the build matrix.
- For a cross-build: a note that you accept the Microsoft CRT and SDK licence once. The wizard records it.
- For Windows: a cross-build with cargo-xwin on Linux, or a Windows runner.
- For a part that ships to user machines: a code-signing row (have, provision or defer).

`check_stack.py` then warns on a missing reason, a napi addon without a build matrix, a cross target without a licence note, a Windows host service without a build option, and a napi component on Vercel.

## The generated layout

The JS packages stay as they are. The wizard adds beside them:

```
Cargo.toml              workspace, resolver 2, fixed release profile
Cargo.lock              committed
rust-toolchain.toml     exact version, minimal profile, rustfmt and clippy
rustfmt.toml
deny.toml
crates/
  app1-core/            pure logic, no I/O
  app1-platform/        OS traits, windows/ and unix/ modules (host service only)
  app1-cli/  app1-worker/  app1-napi/   (only the chosen parts)
  guards/               the starter guard_* tests
packages/native-app1/   JS wrapper for the napi or WASM build
```

There is one workspace and one lockfile. Every cargo command uses `--locked`. The root task runner calls `cargo` through a thin shim. A developer who touches only Rust uses plain `cargo`.

## The rust CI track

The track lives in `luismc-delivery`. `scripts/delivery/rust_ci.py` holds the steps, so CI, the pre-push hook and the agent gate run the same commands.

- **Toolchain.** `rust_ci.py toolchain` installs the exact version in `rust-toolchain.toml` with a pinned `rustup-init`. A channel such as `stable` fails.
- **LLVM.** The pinned LLVM (`lld-link`, `clang-cl`, `llvm-lib`) sits in the tool cache. `ci_tool.py tool llvm --exe lld-link` prints the path. The Windows MSVC cross-link uses it.
- **Linux linker.** The runner pool image carries `build-essential` and `pkg-config`, so `rust_ci.py env` uses the system `cc` first. Zig 0.17.1 is pinned from the `ziglang` wheels on PyPI and is used only when no system C compiler exists, or when you choose it (for an older glibc or a static musl build). With neither it fails with `linker cc not found`.
- **cargo-deny.** `rust_ci.py deny` keeps the RustSec database in the tool cache and fetches it each run. If the fetch fails, a cached copy up to 7 days old gives a warning and the run goes on. An older copy, or none, fails. The committed `deny.toml` is never edited. A generated copy carries the `db-path`.
- **Gate isolation.** Off by default. With `toolchain-isolated` set to true in `gate.json`, `rust_ci.py run` removes the folders that hold `cc`, `gcc`, `clang` and `ld` from `PATH`, so only the pinned tools are tested.
- **Steps.** The gate adds `deny` (when `Cargo.lock` or `deny.toml` changed) and `xwin` (only with a cross target). `smoke.json` lists `binaries`; each is built in debug and run with `--version`.
- **Workflows.** `ci.yml` and `package.yml` use these steps. `Swatinem/rust-cache` runs on GitHub-hosted runners only. `package.yml` builds a Windows exe with cargo-xwin as `packaged-program-windows`.

## The doctor checks

`delivery_doctor.py` runs the `rust` check only when `track` is `rust` or `rust_ci.py` exists. It changes nothing and prints the fix command.

| Item | Result | What it checks |
|---|---|---|
| `rust.toolchain` | fail | The file exists and the channel is `X.Y.Z`. |
| `rust.linker` | fail | A `cc` or `zig` is on PATH or in the tool cache. |
| `rust.windows` | fail | `clang-cl` and `lld-link` exist when a target names `windows`. |
| `rust.pins` | fail | `rustup-init`, `llvm`, `zig` and `cargo-deny` have a sha256 in `tools.json`. |
| `rust.advisory` | warn | The advisory cache exists and is under 7 days old. |
| `rust.disk` | warn | At least 10 GB is free. |

## Known gaps

- **`scope_map` is only partly in use.** The gate reads `scope_map` and step `paths` through `plan_step`. The shipped Rust `gate.json` has the key `rust` only. A mixed repo adds a `js` key and marks its JS steps `paths: "js"`.
- **The workflows have not run on a real Rust project.** Check the first run.
- **Rust apps under `apps/`** are ignored by the push filter of the Rust workflow.
- **The LLVM Linux archive is large** (several GB unpacked).
