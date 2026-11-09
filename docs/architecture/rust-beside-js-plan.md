# Rust beside a JS stack: plan

Owner decisions D138 to D145 (9 Nov 2026) settle the open choices:

- Scope: both the tech-stack-setup component role and a `rust` CI track in luismc-delivery, wizard first (D138).
- Parts offered first: CLI, host service or installer helper, napi or WASM library. Workers and media processing come later, when a project asks (D139).
- Linker: pinned, sha256-checked LLVM (`lld-link`, `clang-cl`) for the Windows cross-link, and a pinned Zig for the Linux host linker, both in the CI tool cache (D140).
- Toolchain: sha256-pinned `rustup-init` through `ci_tool.py`; the version comes from `rust-toolchain.toml` (D141).
- Advisory database: on a failed refresh, use the cached copy with a warning until it is 7 days old, then fail (D142).
- Agent gate: the Rust step always runs with system compilers removed from PATH (D143).
- Windows builds: cargo-xwin where the project accepts the Microsoft CRT/SDK licence once (recorded), else a Windows runner (D144).
- Reason: a written reason only, recorded in the Stack Profile; no measured number is required (D145). Where the text below asks for a number, read "a written reason".

Tasks: DS196 catalog, DS197 wizard text, DS198 tooling assets, DS199 tool fetcher, DS200 rust_ci helper, DS201 workflows, DS202 doctor, DS203 docs. They ride one release.

## 2. What exists today in dev-standards (facts the proposal builds on)

- STACKSPEC catalog already has `rust` in `tech/languages.yaml`, but only as an **API server language**: `requires_reason`, velocity lowest, derives cargo + `rust-toolchain.toml` + clippy deny warnings + rustfmt + cargo-nextest + cargo-deny, sqlx. Bundle `rust_perf` exists. Hosting: containers/VPS native, Lambda supported, Vercel none, Workers degraded.
- Asset tooling `assets/tooling/rust/` has a guards crate (`guard_*` tests). The tooling README maps the twelve STACKSPEC 13.1 gates to Rust commands.
- Delivery plugin has a `rust` template: `ci.yml` (dtolnay/rust-toolchain, Swatinem/rust-cache, `cargo install cargo-deny || true`, codegen drift, sqlx integration job), `package.yml`, `gate.json` (track rust, `cargo-workspace` packages, widen on `Cargo.toml`/`Cargo.lock`/`rust-toolchain.toml`/`deny.toml`), `smoke.json`.
- `tools.json` pins only gitleaks. `ci_tool.py` knows only gitleaks (`gitleaks(plat)`). `agent_setup.sh` installs only gitleaks. `delivery_doctor.py` has no Rust or linker check.
- STACKSPEC 2.2 (pin tool version, commit lockfile, frozen install) and 2.3 (polyglot: native project stays natively buildable, thin task shim) already fit Rust; no wording is Rust-specific.

Gaps this proposal closes: (a) Rust as a non-API component beside a JS stack; (b) cross-compiling and the host linker; (c) no pinned toolchain bootstrap in CI (the template uses `stable`, which contradicts its own comment about `rust-toolchain.toml`); (d) cargo-deny advisory DB handling; (e) no doctor check.

## 3. Where Rust fits in a STACKSPEC stack (generic)

For each: pick when, avoid when, how it connects, examples. The default for any row is "stay in the main language unless the reason is written down" (the catalog already demands a recorded reason).

### 3.1 Command-line tool or developer tool
- Pick when: a single static binary must run on machines without a runtime; startup time matters; the tool is distributed to users or CI.
- Avoid when: the tool is an internal script run only where Node/Python already exists.
- Connects: separate binary. Called by the task shim (`pnpm run codegen` shells out to `cargo run`). Output is files or JSON on stdout.
- Examples: codegen binary for the generated clients (4.1), a repo linter, a data migration tool, a log shipper.

### 3.2 Desktop helper, background service, installer helper
- Pick when: code runs on user machines with a memory or footprint budget; needs OS services (Windows service, systemd, launchd), pipes, file locks, signals; must behave the same on three OSes.
- Avoid when: the helper is a thin wrapper over one OS call that a script handles.
- Connects: separate binary talking to the main app over a local pipe/socket/HTTP on localhost. Keep the wire contract in one file and test it from both languages. Put OS code behind traits in a `platform` crate; `windows/` and `unix/` modules; Linux tests run in CI even when Windows ships first.
- Examples: auto-updater service, tray companion, file-watcher service, installer custom action.

### 3.3 Performance-critical library inside a JS app
- Pick when: a measured hot loop (parsing, hashing, image or archive work, compression, search index) dominates and a JS or WASM-free version misses a stated target.
- Avoid when: the cost is I/O or the database; no profile exists.
- Connects, three options:
  - napi-rs native addon: fastest, Node only, needs a prebuilt binary per OS/arch (build matrix), version lock to Node ABI is handled by N-API.
  - WASM (wasm-bindgen / wasm-pack): runs in browser, Node and edge workers; no threads or file access by default; slower than native; one artifact.
  - Separate worker binary with stdin/stdout or a socket: crash isolation, simplest build, process start cost.
- Examples: markdown or diff engine, image resize, tokenizer, CRDT core, signature verification shared by client and server (one crate compiled native for the server and WASM for the web client, so the rule exists once).

### 3.4 Background worker or queue consumer
- Pick when: high-volume steady load, memory ceiling, or CPU-bound jobs; the worker is a separate deployable (already a STACKSPEC deployable kind).
- Avoid when: the jobs are glue calling vendor SDKs (the Rust SDK gap costs more than it saves).
- Connects: reads the same queue table or outbox as the main stack (5.x, queue substrate follows the DB engine). Shares the database via sqlx; shares types by generated contract, not by hand.
- Examples: thumbnailer, report generator, import/export processor.

### 3.5 File and media processing
- Pick when: large files, untrusted input (archives, PDFs, images) where memory safety and bounded memory matter.
- Avoid when: a maintained C library behind a JS binding already meets the budget and is not the bottleneck.
- Connects: a worker binary (3.4) or a napi/WASM module (3.3). Run untrusted-format parsing in a separate process.
- Examples: archive readers, image fingerprinting, ML inference host (ONNX via `ort`: same runtime, fewer duplicate processes).

### 3.6 Whole API server in Rust
- Already in the catalog. Keep as is. Add one line: if only parts of a product need Rust, prefer 3.1 to 3.5 over a Rust API (the catalog already says Rust costs velocity).

### 3.7 Not a fit
Admin UIs, CRUD APIs on a serverless host, glue to vendor SDKs, anything where the team has no Rust skill and no stated budget.

## 4. Changes to tech-stack-setup

### 4.1 New questions (Phase 1 profile and Phase 3 binding)
Add to Phase 1 (one new profile question, asked only when something other than "web plus API" is possible):
1. "Does any part of the product run on a user's or operator's machine (installer, service, tray, CLI)?" Yes opens the Rust components question.
2. "Is there a measured hot path or memory ceiling the main language misses?" Needs a number or a named profile. No number means no Rust.

New Phase 3 role `native_components` (multi-select, default none): none, cli, host-service, library (napi), library (WASM), worker, media processor. For each pick, the wizard asks:
- Target OSes (Windows, Linux, macOS) and which ship first.
- Where it is built: same runners, or cross-compile (for example Windows target built on Linux).
- How it connects: choose from section 3 (separate binary with local IPC, napi, WASM, worker).
- Reason, recorded in the Stack Profile (reuse `requires_reason` and `reason_prompt`).
- Signing and installer needs (if it ships to user machines): ask, then record as a provisioning ledger row (code-signing certificate: have / provision / defer).

### 4.2 Stack choices and pairings
- `languages.yaml`: add a `rust` **role** `component` next to the existing API role. A selection may now be `{api: typescript, components: [rust]}`. `check_stack.py` must accept Rust as a component beside any API language without the host elimination (that rule applies to the API only).
- Compatible pairings to add to the catalog:
  - TypeScript API + Rust CLI/worker/napi/WASM: allowed on every host. Vercel/Cloudflare keep working, because the Rust part is built in CI and shipped as an npm package, a WASM file or a separate artifact, not run on the host. (Exception: a Rust worker deployable still needs a container host.)
  - Rust component + Windows desktop: requires the Windows build option (cross-compile on Linux, or a Windows runner). Warn on the licence of any SDK downloaded by the cross-build tool.
  - WASM component + edge worker: supported; no threads, no filesystem.
  - napi component + Vercel: needs a prebuilt binary for the Vercel Linux arch; warn.
- Add warnings to `check_stack.py` (STACKSPEC 18 item 14 style): "Rust component without a recorded reason", "napi addon without a build matrix", "cross-compile target without a licence note".

### 4.3 Generated repo layout
Keep the JS packages as they are and add next to them:

```
Cargo.toml              workspace, resolver 2, [workspace.package], [workspace.dependencies], release profile
Cargo.lock              committed
rust-toolchain.toml     exact version (not "stable"), minimal profile, rustfmt + clippy, needed targets
rustfmt.toml  deny.toml
crates/
  app1-core/            pure logic, no I/O (also built to WASM when chosen)
  app1-platform/        OS traits + windows/ and unix/ modules (only if a host service is chosen)
  app1-cli/  app1-worker/  app1-napi/  (only the chosen ones)
  guards/               the existing guard_* starter crate
packages/native-app1/   JS wrapper that loads the napi or WASM build (thin task shim per STACKSPEC 2.3)
```

Rules for the layout:
- One workspace, one lockfile (do not leave a second `Cargo.lock` in a sub-package).
- Task shim: root `pnpm run lint|test|typecheck|build` calls `cargo` for the Rust part; a developer who only touches Rust uses plain `cargo`.
- `scripts/delivery/rust_ci.py` (standard library only) holds the Rust steps so CI, the pre-push hook and the agent gate run the same commands (see section 5).
- Use `xtask` only if needed; the catalog already names it.

### 4.4 STACKSPEC invariants needing Rust wording
These are wording additions, no new requirement IDs renumbered. They go in the Rust row of the tooling README and in the catalog `derives`, not in the technology-neutral spec text (invariants.md 20 forbids naming technology).

| Invariant | Rust wording |
|---|---|
| 2.2 pinned tool | `rust-toolchain.toml` with an exact version; CI installs that version, never `stable`. |
| 2.2 frozen install | `--locked` on every cargo command; `Cargo.lock` committed. |
| 13.1 lint | `cargo clippy --locked --workspace --all-targets -- -D warnings`. |
| 13.1 format | `cargo fmt --all --check`. |
| 13.1 test | `cargo test --locked --workspace`; nextest allowed in CI. |
| 12 supply chain | `cargo deny check` (advisories, bans, licenses, sources), see 5.4 for the database. |
| 3.2/3.3 boundaries | crate boundaries plus `deny.toml` `bans`. |
| Reproducible builds | pinned toolchain, `--locked`, pinned cross tools by sha256, release profile fixed in `Cargo.toml`, `SOURCE_DATE_EPOCH` and `--remap-path-prefix` for byte-identical output where the product needs it. |
| 2.3 polyglot | Rust crates stay natively buildable; thin shim from the root task runner. |
| Contract tests | A wire protocol between Rust and another language has one source file per side and a test in the other language that reads it. |

### 4.5 What not to change
- No technology names in STACKSPEC itself (invariants.md section 20). Rust specifics go in the catalog, tooling and this skill.
- Do not make Rust a default, a bundle recommendation, or remove `requires_reason`.
- Do not change the API-language host elimination for Rust as API.
- Do not renumber sections or requirement IDs.
- Do not add auth or mobile logic for Rust components; those stay in their own skills.
- Do not generate Rust code beyond the empty skeleton and the guards crate; the product writes its own crates.

## 5. Changes to luismc-delivery (the `rust` CI track)

The `rust` template exists and is aimed at a Rust API. Changes below make it work for a mixed repo and on pool runners with no compiler.

### 5.1 Pinned toolchain
- Replace `dtolnay/rust-toolchain@... stable` with a step that reads `rust-toolchain.toml` (or a `rust_ci.py toolchain` step that installs the exact channel through a sha256-pinned rustup-init). Keep Swatinem/rust-cache only if the runner is hosted; on pool runners use the tool cache.

### 5.2 Pinned LLVM (clang + lld) in the tool cache
- Add `llvm` to `tools.json`: version plus per-platform archive URL and sha256 (the official LLVM release archive). `ci_tool.py` gains a generic `tool(name, platform)` (today it only knows gitleaks) that fetches, verifies and unpacks into the cache.
- `rust_ci.py` (new shared helper in the rust template) sets, when no system `cc` is found or when the gate asks for isolation:
  - `CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER`, `CC_x86_64_unknown_linux_gnu`, `CXX_...`, `AR_...` to the cached clang, clang++ and llvm-ar;
  - for the Windows MSVC target: `CARGO_TARGET_X86_64_PC_WINDOWS_MSVC_LINKER` to `lld-link`, `CC_x86_64_pc_windows_msvc` to `clang-cl`, `AR_...` to `llvm-lib`;
  - `PATH` with the cached `bin/` first.
- Linux hosts still need glibc and libc dev files for the host linker. LLVM does not carry them. A bundled-libc compiler (Zig) covers the host linker (D140).
- cargo-xwin and cargo-deny: pin version plus `.crate` sha256 in `tools.json`, build once with `cargo install --locked` into the cache.

### 5.3 Agent gate without system compilers
- The agent gate (`gate.json` runner via `branch_gate.py`) for the rust track runs the Rust steps with system compilers removed from PATH (filter out the directories that hold `cc`, `gcc`, `clang`, `ld`), so the pinned toolchain is what is tested. A job that passes only because a machine happens to have `gcc` is a hidden dependency.
- Add a `toolchain-isolated` field in the rust `gate.json` (default true). Steps stay: secret-scan, change-notes, guards, lint, typecheck, unit; add `deny` (changed+dependents when `Cargo.lock` or `deny.toml` changed) and `xwin` (only when a cross target is declared).
- `widen_on` keeps `Cargo.lock`. Add a `scope` mapping so Rust paths select Rust steps only (the lesson from the e2e timeout): a mixed repo's root check planner must not treat `crates/**` as "root config".

### 5.4 cargo-deny advisory database
- Cache the RustSec clone in the tool cache (`db-path` in a generated copy of `deny.toml`, never edit the committed file).
- Each run: `cargo deny fetch` (git fetch into the cached clone), then `cargo deny check --disable-fetch`.
- If the fetch fails: use the cached copy, print a warning (and write it to the CI summary), keep the exit code green. If no copy exists: fail with a clear message.
- Replace `cargo install --locked cargo-deny || true` in the template (it hides failures) with the pinned install.

### 5.5 Doctor checks (`delivery_doctor.py`, only when `track` is rust or `rust_ci.py` exists)
- A host linker is available: pinned LLVM in the tool cache (or a system `cc`), with a clear message `linker cc not found` and the fix command.
- `clang-cl` and `lld-link` present when a Windows cross target is in `rust-toolchain.toml` `targets`.
- `rust-toolchain.toml` exists, names an exact version, and is not `stable`.
- `tools.json` pins every Rust tool with a sha256 (reuse the existing gitleaks pin check).
- The advisory DB cache exists and is younger than N days (warning only); network failure is a warning, never a failure.
- Runner free disk for `target/` and the cache (warning).
- Doctor changes nothing; it prints the command.

### 5.6 Other template fixes
- `smoke.json`: add a smoke that builds each declared binary in debug and runs `--version`.
- `package.yml`: keep artifacts under one stable name per kind (rule DL-22); add the Windows exe artifact example.
- Cross-workflow rule: a workflow that needs a built binary builds or downloads it in the same run.
- `cancel-in-progress` expression must be copied from the main workflow, not rewritten.
- Path filter: list `crates/**`, `Cargo.*`, `rust-toolchain.toml`, `rustfmt.toml`, `deny.toml`, the CI scripts and `tools.json`, so a Rust-only change does not run the JS suite and the reverse.

## 6. Suggested split into small, file-disjoint tasks

Owners are paths under `claude/plugins/` (dev-standards). Each task is one branch; none edits a spec `**Version:**` line or a plugin `"version"`; each adds a change note.

| # | Task | Owner files | Depends on |
|---|---|---|---|
| T1 | Catalog: Rust as component role, pairings, warnings | `project-setup/skills/tech-stack-setup/assets/catalog/tech/languages.yaml`, `.../catalog/roles.yaml`, `.../catalog/bundles.yaml`, `.../assets/check_stack.py`, its tests | none |
| T2 | Wizard text: new questions, layout, reason prompts | `project-setup/skills/tech-stack-setup/SKILL.md` | T1 (names) |
| T3 | Tooling assets: workspace skeleton, toolchain file, rustfmt, deny.toml, README Rust column and wording | `project-setup/skills/tech-stack-setup/assets/tooling/rust/**`, `.../assets/tooling/README.md` | none |
| T4 | Generic tool fetcher and pins | `delivery/templates/shared/scripts/delivery/ci_tool.py`, `tools.json`, `tools_pin.py`, tests | none |
| T5 | Rust CI helper (toolchain, LLVM env, isolation, cargo-deny cache) | `delivery/templates/rust/scripts/delivery/rust_ci.py` (new), `delivery/templates/rust/scripts/delivery/gate.json`, `smoke.json`, tests | T4 |
| T6 | Rust workflows | `delivery/templates/rust/.github/workflows/ci.yml`, `package.yml` | T5 |
| T7 | Doctor | `delivery/scripts/delivery_doctor.py`, `delivery/tests/test_doctor.py` | T4 |
| T8 | Docs: feature spec update, guide "Rust beside JS", change notes | `docs/features/**` for the two plugins, `docs/guides/**` | T1 to T7 (fold last) |

T1/T3/T4/T7 can run in parallel (disjoint). T2 follows T1. T5 follows T4. T6 follows T5. Tests per `python tools/ci_areas.py --branch-advice`; no mutation passes, no Docker.

