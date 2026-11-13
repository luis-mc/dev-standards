# DL295 Rust CI speed

## Base check

`git fetch origin main && git checkout -B DL295-rust-ci-speed origin/main`.
`claude/plugins/delivery/templates/rust/scripts/delivery/rust_ci.py` has `def build_env` (line 162) and
`def cmd_env` (line 188). Base is ready.

## What changed

- **New** `claude/plugins/delivery/templates/rust/scripts/delivery/rust_scope.py` (standard library only).
  `--event E --head-ref R [--diff-base REF] [--config FILE] [--github-output]`, writes `run=`, `full=`,
  `crates=`, `why=`. `run=false` only for a pull request whose diff touches no Rust path. A push, a release
  pull request (`release_pr.head_re` from `ci-scope.json`, default `^release/.+`), an unreadable diff, a
  workspace-wide input, a crate folder that is not a member, or no crate placed gives `full=true`. Otherwise
  `crates` is the touched members plus every member that depends on them, transitively. The graph comes from
  the root `[workspace] members` (globs allowed, so `apps/` works as well as `crates/`), each member's
  `[package] name`, its dependency keys, `path = "..."` entries and `[dependencies.foo]` /
  `[target.'cfg'.dependencies.foo]` headers. Diff: `git diff --name-only <diff-base> HEAD`, default `HEAD^1`.
- **`rust_ci.py`**: new subcommands `fmt`, `check`, `clippy`, `test`. With `RUST_CRATES` set they use
  `-p a -p b`; empty or unset keeps the whole workspace. New persistent target cache: unless
  `CARGO_TARGET_DIR` is set or `DELIVERY_NO_TARGET_CACHE=1`, `build_env` sets `CARGO_TARGET_DIR` to
  `<cache_dir()>/cargo-target/<RUNNER_NAME or local, sanitised>/<channel>-<16 hex of sha256(Cargo.lock) or
  nolock>`, touches it and prunes the runner's keys oldest first while their total size is over
  `RUST_TARGET_CAP_GB` (default 40). The current key, the newest other key and any key whose
  `*/.cargo-lock` a `flock` try-lock cannot take are kept; without `fcntl` (Windows) nothing is deleted.
  Any `OSError`/`ValueError` prints one line and falls back to `target/`. The value is exported with the
  other job env keys, so later steps and the smoke binary path use it.
- **`templates/rust/.github/workflows/ci.yml`**: each Rust job starts with a `scope` step running
  `rust_scope.py --github-output`; every later step carries `if: steps.scope.outputs.run != 'false'`; the
  cargo steps get `RUST_CRATES: ${{ steps.scope.outputs.crates }}` (empty on a full run); `rust_ci.py deny`
  runs only when `full == 'true'`. The paths filter adds `scripts/delivery/rust_scope.py`. The hosted and
  pool integration jobs keep identical steps after their setup (DL190).
- **Install list**: none needed. `delivery_ci_install.py` walks the template folder (`os.walk`), so
  `rust_scope.py` is copied with the rest; no script lists the rust template files by name.
- Tests: new `claude/plugins/delivery/tests/test_dl295_rust_scope.py` (20 tests: graph with a path dep and a
  workspace dep key, touched crate plus transitive dependents, workspace-wide input, push and release PR,
  unreadable diff, no Rust file, unknown member folder, members under `apps/`, config `head_re`, CLI
  outputs; cache key per `Cargo.lock`, runner-name sanitising, opt-out and preset env, failure fallback,
  prune keeps the current and newest other key, prune skips a key held under a real `flock` (POSIX only),
  cap not reached, package args with and without `RUST_CRATES`).
  `test_ds200_rust_ci.py` sets `DELIVERY_NO_TARGET_CACHE=1` in `setUp`, so its pinned linker-env assertions
  keep their clean stderr; no pinned behaviour changed.
- Docs: `docs/features/delivery/spec.md` R5.50 gains the crate-scoping and target-cache text (no version
  line or change log touched). Notes: `docs/features/delivery/changes/DL295.md`,
  `docs/features/delivery-speed/changes/DL295.md`, `docs/architecture/changes/DL295-rust-ci-speed.md`
  (`plugin: claude/plugins/delivery/.claude-plugin/plugin.json`, `change: minor`).

## Test commands and results

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s claude/plugins/delivery/tests -t claude/plugins/delivery/tests` | OK, 1612 tests, 4 skipped |
| `python3 tools/test_delivery_ci.py --no-mutants` | 78 passed, 0 failed |
| `python3 claude/plugins/docs/scripts/docs_check.py` | 2 errors: W1 on `docs/work/DL295/` (expected on a branch) and G1 `docs/architecture/decisions.md` stale, which is already stale on `origin/main` (checked with the branch stashed) |
| `python3 tools/ci_areas.py --branch-advice` | `light: test locally only` |
| `gh workflow run spec-lint.yml --ref DL295-rust-ci-speed -f areas=delivery` | run 800 on `cebbfd9`: every delivery job passed, including the aggregator; only `docs check` failed, with the two expected errors (W1 on `docs/work/DL295/REPORT.md`, G1 `docs/architecture/decisions.md` stale on `main`) |

Run 1 (commit `6ddeb5e`) failed on two template tests that run only in CI
(`test_dl190_pool_integration_job`, `test_dl187_ci_templates_pool`): the scope step had moved the pool job's
database step and the `&& '' ||` form was banned. Both are fixed in `cebbfd9` and the whole delivery suite
passes locally.

No mutation passes, no Docker, no cargo builds.

## Follow-ups

- The scope step fetches the diff base with `git fetch --depth=2`; on a clone that cannot reach it the scope
  falls back to a full run, which is safe but slower. A project that keeps a deeper checkout avoids it.
- `smoke.json` still shows `./target/release/app` as an example string; `rust_ci.py smoke` itself now reads
  `CARGO_TARGET_DIR`. The example is not mine to edit under this task's ownership.
- `docs/architecture/decisions.md` is stale on `main` (G1); the release fold or a docs task should rebuild it.

## Branch

`DL295-rust-ci-speed`, head `cebbfd9db8b745d36d1469793cfeef68dba3eacb` plus this report commit.

READY