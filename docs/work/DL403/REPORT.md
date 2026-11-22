# DL403 report: stack and tool assumptions in the delivery plugin

Read-only study. No code changed. Paths are under `claude/plugins/delivery/` ("P/"). `S/` is `P/templates/shared/scripts/delivery/`. Line numbers are from `origin/main` at the time of the run (b0d8a24).

**Decision: OPEN.** The owner has not chosen. The recommendation below is advice only.

## 1. Short answer

The plugin does assume stacks. Most of it is soft: a project can override it. The danger is the "silent" rows. A tool the plugin does not know gets no check, and nothing says so. No doctor check reads gate.json, e2e or the guardrails today (the doctor's check ids are only `ci.fail_fast`, `ci.scripts-current`, `machine.*`, `pool`, `rust.*`, `workflows`).

Checked with a throw-away repo (scratchpad, not in the tree):

- A Cypress project (`cypress/e2e/a.cy.ts` with `cy.wait(5000)`, `package.json` script `cypress run`): `test_guardrails.py` printed no G1 and no G4 line for it. Cypress files are not "test files" to it. Silent.
- A pytest e2e file `tests/e2e/test_a.py`: G1 and G4 do see it (so the evidence "pytest is not checked" is out of date on `main`; pytest, Go and Rust have G1 code at S/test_guardrails.py:306, :333, :348). But the e2e spec path default still misses it (row 1).
- The Go template `gate.json` fails the plugin's own G1: `go test` without `-timeout` at gate.json:36 (guards) and :53 (unit). In warn mode this prints, in block mode it blocks. This is the "Go step with no timeout" the owner saw. I could not reproduce a *replace* of a project's step: the installer does a 3-way merge when it has a base (P/scripts/delivery_ci_install.py:380-398) and keeps the project file with a `.new` when it has none. The template step itself lacks `-timeout`, so a project that adopts it loses the timeout.

## 2. Table of assumptions

Columns: where, the assumption, what a non-matching project gets, can the project override it (key), does the doctor say so.
Result codes: **works**, **silent** (skipped with no message), **wrong** (a wrong answer), **blocks** (stops the project).

### 2a. E2E and test tools

| # | file:line | Assumption | Mismatch result | Override | Doctor |
|---|---|---|---|---|---|
| 1 | S/delivery_common.py:61, :340, :902 | E2E specs are `e2e/*.spec.*` or `*/e2e/*.spec.*` (Playwright naming) | **silent**: a changed `cypress/e2e/x.cy.ts` or `tests/e2e/test_x.py` is not an e2e spec; `e2e_push_check.py` allows the push; gate_verify wants no e2e record | gate.json `e2e_spec_paths` | no |
| 2 | S/delivery_common.py:863-897 | Without `e2e_map`, a UI package keeps specs in `<pkg>/e2e` or `e2e/<name>` | **wrong**: other layouts give "no specs", so a UI change may run no e2e, or the whole suite | gate.json `e2e_map` | no |
| 3 | S/delivery_common.py:880 | Derived e2e selection only works for `pnpm-workspace` | **wrong**: any other kind falls to "whole suite" (slow, not unsafe) | `e2e_map` | no |
| 4 | S/delivery_common.py:970-972 | The e2e step is the first step with scope `ui-changed` | **silent**: no such step means `--e2e-only` raises "no ui-changed step" (branch_gate.py:236); gate_verify then reports a missing e2e record only if `ui_paths` matched | gate.json steps | no |
| 5 | P/templates/ts/scripts/delivery/gate.json (e2e step) | e2e command is `pnpm exec playwright test {e2e_specs}`; Chromium via `E2E_CHROMIUM_PATH` or `playwright install` | **wrong** for Cypress/pytest: the step runs the wrong tool, or fails | step `run` / `run_full` | no |
| 6 | S/test_guardrails.py:97-98 | Test files are `*.test.*`, `*.spec.*`, `test_*.py`, `*_test.py`, `*_test.go`, `conftest.py`, Rust `#[test]` | **silent**: `*.cy.*`, `*Test.java`, `*Tests.cs`, `*_spec.rb`, `*Test.php` are not scanned by G1, G3-per-file, G4, G5 | none | no |
| 7 | S/test_guardrails.py:185 (`kind_of`) | A path with "e2e" or "playwright" is e2e; "integration" is integration; else unit | **wrong**: limits (10/60/120 s) picked from the folder name | `ci.jobs.<id>.test_timeout_s` (lower only) | no |
| 8 | S/test_guardrails.py:261-296 (G1) | Timeouts are read from vitest, jest, playwright, vite configs and `package.json` jest key | **silent** for Cypress (`defaultCommandTimeout`), Mocha, Karma, Jasmine, Selenium, JUnit, xUnit/NUnit, RSpec, PHPUnit | `ci.test_guardrails.off` + reason | no |
| 9 | S/test_guardrails.py:306-325 (G1) | pytest needs `pytest-timeout` in pytest.ini, tox.ini, setup.cfg or pyproject | works for pytest; a project using another python runner is silent | same | no |
| 10 | S/test_guardrails.py:333-345 (G1) | Go: every `go test` command needs `-timeout` | works; **the Go template fails it** (gate.json:36, :53) | same | no |
| 11 | S/test_guardrails.py:348-380 (G1) | Rust: needs nextest with slow-timeout; plain `cargo test` is a break | works | same | no |
| 12 | S/test_guardrails.py:106-122 | Test commands live in workflows, Makefile, justfile, package.json, gate.json, `scripts/*.sh` | **silent**: a command in `tox.ini`, `noxfile.py`, `build.gradle`, `pom.xml`, `*.ps1`, `taskfile` is not found; Go G1 then says "no go test command found" | none | no |
| 13 | S/test_guardrails.py:442-470 (G3) | Retry patterns: Playwright config, pytest rerun plugins, jest.retryTimes, nextest | **silent** for Cypress `retries` in `cypress.config.*`, Mocha `--retries` partly, JUnit rerun, Gradle `retry` | off + reason | no |
| 14 | S/test_guardrails.py:470-500 (G4), :500-554 (G5) | Sleep patterns and case counts for JS, Python, Go, Rust | **silent** for Java, C#, Ruby, PHP | off + reason | no |
| 15 | S/test_guardrails.py:51-52 | Skip dirs are node/python/rust build dirs (`node_modules`, `target`, `.venv`, `dist`, `.next` ...) | **wrong** for `bin`, `obj`, `.gradle`, `Pods` (scanned as code) | none | no |
| 16 | S/test_guardrails.py:554 (G6) | Mutation tools are stryker, mutmut, cargo-mutants, go-mutesting | **silent** for PIT, Stryker.NET (named "stryker" so caught), Infection | off + reason | no |
| 17 | S/test_guardrails.py:636-724 (G7) | Some workflow uploads test times (ci-run-times, JUnit, timing JSON) | works for any tool that emits JUnit | off + reason | no |
| 18 | S/rerun_tests.py:49, :60-63, :418 | Rerun narrowing knows pytest, vitest/jest, playwright, go, cargo, nextest; `--runner` is a fixed choice | **blocks** the narrowing for Cypress, dotnet, JUnit, RSpec (argparse error); the caller must rerun the whole job | none (code) | no |
| 19 | S/shard_balance.py:247, :131-171 | Timing reports are vitest/jest or Playwright JSON | **blocks** `update` for pytest/JUnit/Cypress reports | none | no |
| 20 | S/run_suite.py:14 | Docs example `pnpm vitest run` (example only) | works | its own JSON | no |
| 21 | S/area_select.py:11-17, :13 | `run_everything` lists `package.json`, `pnpm-lock.yaml`; examples use `apps/` and `*.test.ts` | works (map is project config) | ci-areas.json | no |

### 2b. Package manager, build tool, language

| # | file:line | Assumption | Mismatch result | Override | Doctor |
|---|---|---|---|---|---|
| 22 | S/delivery_common.py:53, :343 | `packages.kind` is one of pnpm-workspace, go-modules, cargo-workspace, dotnet-sln | **blocks** with a clear error for npm, yarn, bun, Maven, Gradle, uv, poetry, Bundler, Composer | none (closed list) | no (the gate refuses) |
| 23 | S/delivery_common.py:470-545 | Package finders: `pnpm-workspace.yaml`, cargo, go, dotnet | **blocks** (raise "pnpm-workspace.yaml is missing") for an npm-workspace repo that picks the ts track | none | no |
| 24 | S/delivery_common.py:607-640 | Only pnpm-workspace has a dependency graph; others get "changed packages only", no dependents | **wrong**: `changed+dependents` for go, rust, dotnet is really `changed`; a dependent that breaks is not run | none | no |
| 25 | S/delivery_common.py:62, :711-730 | `pnpm-lock.yaml` importers scope | works for pnpm; other locks use `widen` or `per-package` | `lockfile_scope`, `widen_on` | no |
| 26 | S/delivery_common.py:73-83 | Lockfiles join.py may resolve: pnpm, npm, yarn, go.sum, Cargo.lock, packages.lock.json | **blocks** the auto-resolve for `uv.lock`, `poetry.lock`, `Gemfile.lock`, `bun.lock`, `gradle.lockfile` (a human merges) | gate.json `lockfiles` | no |
| 27 | S/join.py:54-55, :339-380 | Cargo.lock conflict resolved with `cargo`; other lock conflicts re-run `setup` | works for cargo; others need `setup` to regenerate | `setup` | no |
| 28 | S/delivery_common.py:81 (`_SKIP_DIRS`) | Skipped dirs: node_modules, vendor, target, bin, obj, testdata | works for the four tracks | none | no |
| 29 | S/branch_gate.py:93-143, :284-297 | Any changed `.cs` file triggers `dotnet build` of its `.csproj`; if `dotnet` is missing it is a warning | runs on any track when a `.cs` file changes, and a failed build fails the run whatever gate.json says; n/a without `.cs` | none | no |
| 30 | S/fast_guards.py:50 | Dependency dir linked into worktrees is `node_modules` only | **wrong**: Python `.venv`, Go `vendor`, Rust `target` are copied or rebuilt in each worktree (slow, not wrong) | none | no |
| 31 | S/ci_scope.py:80-83, :92 | A root `package.json` change counts only for listed keys (`name`, `main`, `scripts` ...) | n/a for non-Node (rule is not used) | `package_json.keys` | no |
| 32 | P/scripts/hook_pre_tool.py:152-159 (DL-23) | Unfrozen-install deny knows npm, pnpm, yarn, bun only | **silent** for `pip install`, `poetry install`, `uv sync` without lock, `bundle install`, `composer install` | `gate_markers` (hooklib.py:49) narrows only | no |
| 33 | P/scripts/hook_pre_tool.py:27-28, :353-359 | The branch gate is `check:branch` (npm script) or `branch_gate.py` | works: `branch_gate.py` is the plugin's own | none | no |
| 34 | P/scripts/delivery_ci_install.py:221-226, P/scripts/delivery_ci_setup.py:557-561 | Track detection: `package.json`=ts, `go.mod`=go, `Cargo.toml`=rust, `*.sln`/`*.csproj`=dotnet | **wrong**: a Python, Java, Ruby or PHP repo detects no track (empty); a repo with a `package.json` only for tooling is called ts | `track` in config.json / state / gate.json | `facts` prints it; no doctor line |
| 35 | P/scripts/delivery_ci_install.py:119, :451-455; P/scripts/delivery_doctor.py:1090 | The track list is closed: ts, go, rust, dotnet | **blocks** `install --track python` (no template folder) | none | no |
| 36 | P/scripts/delivery_ci_install.py:451-455 (`FALLBACK_PATHS`) | Path patterns per track, e.g. ts = `packages/**`, `apps/**`, `**/*.ts`, `tsconfig*.json`, `eslint.config.mjs` | **wrong**: a Node repo with `src/` and `lib/` gets a CI path filter that skips its code (the run is not started) | edit ci.yml / ci-scope.json by hand | no |
| 37 | P/templates/ts/.github/workflows/ci.yml:259-349 | pnpm via corepack, `.nvmrc`, turbo, prettier, depcruise, vitest projects `unit` and `contract`, `pnpm audit` | **wrong** for a non-pnpm or non-vitest project (the job fails at install) | edit ci.yml | no |
| 38 | P/templates/ts/scripts/delivery/gate.json | The ts gate: `pnpm turbo run lint`, `pnpm vitest run --project guard`, `{affected_dirs}`, `depcruise` | **wrong** for npm, yarn, jest, Cypress | edit gate.json | no |
| 39 | P/templates/ts/scripts/delivery/ci-scope.json | `full_files` list: package.json, pnpm-lock, turbo.jsonc, vitest.config.ts, playwright.config.ts, `.nvmrc` | **wrong**: a Cypress or jest config change does not widen the scope | edit ci-scope.json | no |
| 40 | P/templates/{go,dotnet,rust}/scripts/delivery/gate.json | Fixed steps: `go test -short`, `golangci-lint`, `go vet`; `dotnet test --filter Category=Unit` or `Category=Guard`; cargo via `rust_ci.py` | **wrong**: a Go project that runs tests with its own flags, a .NET project that uses no `Category` traits (the filter runs **zero tests and passes**: silent) | edit gate.json | no |
| 41 | P/templates/*/scripts/delivery/gate.json (secret-scan step) and S/*.py | `gitleaks`, and `python3 ... \|\| python ...` for helper scripts | **blocks** where gitleaks or Python is absent | step `run` | partly (tool pins in tools.json) |
| 42 | P/templates/*/.github/workflows/*.yml (`runs-on`) | `ubuntu-latest` through `vars.CI_RUNS_ON` | works | repo variable `CI_RUNS_ON` | `machine.runs_on` |

### 2c. File layout and branch names

| # | file:line | Assumption | Mismatch result | Override | Doctor |
|---|---|---|---|---|---|
| 43 | P/scripts/hook_design_edit.py:108, :66 | UI code is under `apps/`, shared UI under `packages/ui/`; test files are `*.test.*`, `*.spec.*` or under `__tests__`/`tests` | **silent** for a repo that keeps UI in `src/` (not judged); only active when `docs/design-system/` exists | `design_system.app_paths`, `.shared_paths` | no |
| 44 | P/templates/ts/scripts/delivery/gate.json (`ui_paths`) | `ui_paths` default in the ts template: `apps/web/`, `apps/admin/`, `packages/ui/` | **silent**: other UI folders never require e2e | gate.json `ui_paths` | no |
| 45 | S/delivery_common.py:51 (`DEFAULT_INERT_PATHS`) | `docs/**` is inert (no code step) | works | `inert_paths` | no |
| 46 | S/delivery_common.py:311, :816 | Default branch `main` | works; `master` repos must set it | gate.json `default_branch` | no |
| 47 | P/templates/shared/.delivery/config.json (`base`), P/scripts/delivery_watch.py:299, :913, :930 | `base` defaults to `main` | **wrong** for `master`: the PR is opened against `main` and fails | config `base` | no |
| 48 | S/agent_ci.py:35, :63 | `agent_ci` base is **`origin/master`**, while all the other code defaults to `main` | **wrong**: on a `main` repo the agent-CI join merges onto a ref that does not exist, unless `base` is set | `agent_ci.base` | no |
| 49 | S/cloud_shard.py:244, S/cleanup.py:526, S/ci_scope.py:31, :121, S/change_notes.py:116, S/test_guardrails.py:55 | `main` or `main`/`master` fallbacks, five separate defaults | works with `main`; `master` is handled in some, not all | per-file keys | no |
| 50 | S/ci_watch.py:499 | Default branch by config, then `origin/HEAD`, then main/master | works (the best of the group) | `default_branch` | no |
| 51 | S/delivery_common.py:331-333; P/templates/shared/.delivery/config.json | Release branches are `release/*` or `*-integration`; train label `^release/\d+[a-z]?$` | **wrong** for `develop` / `rc-*` flows | `release_branches`, `release_branch_re`, `train_branch_re`, `join_branch_re` | no |
| 52 | S/agent_ci.py:63 | Agent branch prefix `claude/`, CI prefix `ci/` | works | `agent_ci.branch_prefix` | no |
| 53 | S/delivery_common.py:331 | Specs live at `docs/specs/*.md` | **silent**: `change_notes.py` checks no spec if the project keeps them elsewhere | gate.json `specs` | no |
| 54 | P/scripts/hook_pre_tool.py:468-472 (DL-75) | Every new doc goes under `docs/` | works for any stack | none | no |
| 55 | P/scripts/hooklib.py:127-133, P/scripts/delivery_ledger.py:971 | Record folder is `docs/project` | works | `record_dir` | no |
| 56 | S/delivery_common.py:60-84, S/e2e_push_check.py:1-12 | Result refs under `refs/gate-results/`, files under `.delivery/`, gate at `scripts/delivery/gate.json` | works (plugin-owned) | none | no |

## 3. What the table says

1. Closed lists in code: `PACKAGE_KINDS`, `TRACKS`, `RUNNERS`, track detection, `FALLBACK_PATHS`. An unknown tool gets an error (rows 18, 19, 22, 23, 35) or nothing (rows 1, 6, 8, 12-16, 32, 34, 36).
2. Defaults that name one tool: e2e spec paths (row 1), test-file names (row 6), the install deny (row 32), the design-system folders (row 43), `ui_paths` (row 44).
3. Silent rows are the problem the owner named. Of 56 rows, 17 are silent, 14 give a wrong result, 8 block and the rest work. Rows 1, 6, 8, 12, 13, 32, 34, 36, 40, 43, 44 matter most.
4. The doctor reads none of this. It has no check for gate.json, e2e, guardrails, track or test tools.
5. A config key exists for most defaults (rows 1, 2, 4, 25, 43, 44, 46-53). The problem is that the project must know to set it.
6. Inconsistent branch defaults: `master` in agent_ci.py, `main` elsewhere (row 48).
7. The Go template breaks its own guardrail G1 (row 10).

## 4. Options

All options keep requirement IDs, section numbers and spec versions as they are (AGENTS.md).

### Option A: no assumed tool; projects declare it

The plugin never picks a tool for a project. `.delivery/config.json` (or `gate.json`) gets a `stack` block: language, package manager, test runners, e2e tool, spec globs, test-file globs, test commands. Every check either runs the declared command or the doctor prints `not checked for <tool>`. A check that cannot run never passes in silence.

- **What breaks today that this fixes:** rows 1, 6, 8, 12-14, 16, 32, 34, 36, 43, 44 all become either declared or loudly "not checked".
- **What changes for existing projects:** the four templates stay as starter files but their values are copied into `stack` on the next `update`. A project that does nothing keeps today's values (read as the `ts`, `go`, `rust` or `dotnet` preset), so no behaviour changes. New doctor lines appear as warnings for anything that is not declared.
- **Migration cost:** high. Every closed list (`PACKAGE_KINDS`, `RUNNERS`, `TRACKS`) becomes data. G1, G3, G4, G5 lose their built-in per-tool code and read declared globs and commands, or each tool becomes a small adapter anyway. Needs a spec section, a schema change in `references/config-schema.json`, about 8 scripts and their tests. Estimate: 10 to 15 tasks.
- **Risk:** a project that declares wrongly gets false confidence. The plugin cannot judge a command it does not know.

### Option B: keep defaults for the common stacks, add per-tool adapters, loud doctor for the rest

Keep today's four tracks. Add small adapters for the tools that already matter in practice: Cypress, pytest/Selenium e2e, Mocha, JUnit/xUnit, npm and yarn. An adapter holds: spec globs, test-file globs, G1 timeout reader, G3 retry reader, rerun runner name. Any tool that has no adapter gets a doctor line `not checked for <tool>` and the guardrail report prints `G1 not checked: no adapter for <tool>`. A `stack.adapters` key lets a project name its own.

- **What breaks today that this fixes:** rows 1, 6, 8, 13, 18, 19, 22, 23, 32 for the listed tools. The silent rows become loud for all others.
- **What changes for existing projects:** nothing breaks; new warnings appear for any tool detected (by config files such as `cypress.config.*`, `pytest.ini`, `jest.config.*`) that has no adapter. Warn only, never block, in the first release.
- **Migration cost:** medium. One new `detect_tools()` function, one adapter table, one doctor check, then one adapter per tool. Estimate: 1 task for the frame and the doctor line, 1 task per adapter (about 5), 1 for the Go template fix. Can ship in steps.
- **Risk:** the adapter list grows forever, and each one is code the plugin must keep right.

### Option C: hybrid. Declare first, adapters for defaults, doctor always

Do B's doctor line and detection first (cheap, removes the silence now). Then let a project override any adapter field in config (Option A's `stack` block, but optional). Defaults stay the four tracks. Add adapters only when a project needs one. Close the small gaps at once: widen the default `e2e_spec_paths`, fix the Go template timeout, make `agent_ci` base follow `default_branch`.

- **What breaks today that this fixes:** same as B, plus the project can fix any row itself without waiting for the plugin.
- **What changes for existing projects:** as B. Optional `stack` block is the only new config.
- **Migration cost:** medium-low to start (3 tasks), then grows only on demand.
- **Risk:** two mechanisms (adapters and declarations) to explain. Needs a clear rule for which wins (the declaration).

### Comparison

| | A: declare only | B: adapters + loud doctor | C: B first, then optional declare |
|---|---|---|---|
| Silent rows removed | all | all (by the doctor line) | all (by the doctor line) |
| Tools that really work | any the project declares | only those with an adapter | adapter ones, plus any declared |
| Existing projects | preset keeps behaviour, new warnings | new warnings only | new warnings only |
| First delivery | 10-15 tasks | 3-4 tasks | 3 tasks |
| Plugin code kept | least in the end | grows per tool | grows slowly |
| Wrong-confidence risk | highest | lowest | medium |

## 5. Recommendation (advice only; the choice is OPEN)

Option C, in this order:

1. **Stop the silence first.** One doctor check, `stack.tools`: detect tools from files (`cypress.config.*`, `pytest.ini`/`pyproject`, `jest.config.*`, `build.gradle`, `pom.xml`, `*.csproj`, `Gemfile`, `composer.json`) and print `ok`, or `warn: not checked for <tool>: <which checks skip it>`. The guardrail report prints the same for G1, G3, G4, G5 when a detected tool has no reader. This needs no change to any default and is the part that answers the owner's complaint.
2. **Fix the three small bugs now:** the Go template `-timeout` (rows 10, 40), the `agent_ci` base `origin/master` default (row 48), and the e2e spec default (row 1: add `**/*.cy.*`, `tests/e2e/test_*.py`, `**/e2e/**/*.spec.*`) so the common e2e layouts are seen.
3. **Adapters on demand,** Cypress first, then pytest/Selenium e2e, then npm/yarn package kinds, then JUnit/xUnit.
4. **Optional `stack` declaration** (Option A's data) only after step 3 shows the same fields keep being needed.

Why not A first: it is the largest change and the plugin cannot check a command it does not know. Why not B alone: it leaves a project with an odd tool to wait for the plugin; C lets the project set the field itself.

Not recommended: making the plugin refuse unknown tools (it would block projects that are doing nothing wrong).

## 6. Open questions for the owner

1. Pick A, B, C or another option. **OPEN.**
2. Should an undetected or unadapted tool be a `warn` in the doctor or a `fail` once `enforcement.mode` is `block`? Suggest `warn` for one release.
3. Is the list in step 3 the right order for tools?

## 7. Method and limits

- Read: `P/scripts/*.py`, `P/templates/*/scripts/delivery/*`, `S/*.py`, the four `gate.json` and `ci.yml` templates, `P/references/config-schema.json`, `P/hooks`, the DELIVERYSPEC headings.
- Two small runs in the scratchpad with `test_guardrails.py`: a Go repo with the template `gate.json` (G1 breaks at lines 36 and 53) and a Cypress/pytest repo (Cypress silent). No file in the tree changed besides this report.
- Not read in full: `delivery_runner_pool.py`, `machine_slots.py`, `vm_check.py`, the lifecycle templates and the Windows/MSI scripts. They concern runners and OS, not language or test tool.
- Row counts in section 3 are my count of the table, not a tool output.
- `docs_check.py` is run before the last push; its result is in the commit message.

Branch head SHA with the full report: `c8d51f9925afa068af810e9e84ed003a4be953b0`. The next commit only adds this SHA and the last line. `docs_check.py` reports only W1 (a work file on the branch), which is expected.

READY
