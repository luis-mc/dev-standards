# Delivery scripts: contract

The scripts that implement STACKSPEC §11.2, §13.1 (default-branch skip), §13.5
and §13.6 in a generated repository. Every script is Python 3.11+, standard
library only, and runs the same on Linux, macOS and Windows (Git Bash or
PowerShell). This file is the contract the scripts, their tests and the skills
are built against; change it first, then the code.

## Where things land in a generated repository

| Repository path | Source in this plugin | Owner |
|---|---|---|
| `scripts/delivery/branch_gate.py` | `tooling/shared/scripts/delivery/` | gate |
| `scripts/delivery/gate_verify.py` | same | gate |
| `scripts/delivery/fast_guards.py` | same | gate |
| `scripts/delivery/join.py` | same | gate |
| `scripts/delivery/agent_setup.sh` | same | gate |
| `scripts/delivery/delivery_common.py` | same (shared helpers: git, JSON, gate.json loading) | gate |
| `scripts/delivery/ci_watch.py` | same | ci |
| `scripts/delivery/ci_skip_check.py` | same | ci |
| `scripts/delivery/reach_check.py` | same | ci |
| `scripts/delivery/tools.json` | same | gate |
| `scripts/delivery/gate.json` | `tooling/<track>/scripts/delivery/gate.json` | gate |
| `.githooks/pre-push` | `tooling/shared/.githooks/pre-push` | gate |
| `.gitattributes` | `tooling/shared/.gitattributes` (LF for scripts and hooks) | gate |
| guard starter, TS | `tooling/ts/guards/*.guard.test.ts`, run by the Vitest `guard` project in `vitest.config.ts` | gate |
| guard starter, Go | `tooling/go/guards/` | gate |
| guard starter, Rust | `tooling/rust/crates/guards/`, a member crate; add `crates/guards` to the workspace `members` | gate |
| guard starter, .NET | `tooling/dotnet/tests/Guards/`; add the project to the solution | gate |
| `e2e/quarantine.json` (ts only) | `tooling/ts/e2e/quarantine.json` | ci |
| `.github/workflows/ci.yml` | `tooling/<track>/.github/workflows/ci.yml` | ci |

`.delivery/` (local results) is added to the generated `.gitignore`.

Exit codes are shared by every script: `0` pass, `1` checks failed or result not
trusted, `2` usage or configuration error, `3` join stopped at a conflict, `4`
timed out. A script never exits 0 when it could not decide.

## `gate.json` (per track)

```json
{
  "schema": 1,
  "track": "ts",
  "default_branch": "main",
  "setup": ["pnpm install --frozen-lockfile"],
  "packages": {"kind": "pnpm-workspace"},
  "widen_on": ["pnpm-lock.yaml", "package.json", "turbo.jsonc", ".github/", "scripts/delivery/"],
  "ui_paths": ["apps/web/", "apps/admin/", "packages/ui/"],
  "steps": [
    {"name": "typecheck", "scope": "changed+dependents",
     "run": "pnpm turbo run typecheck --continue --filter=...[{base}]",
     "run_full": "pnpm turbo run typecheck --continue"},
    {"name": "lint", "scope": "changed+dependents",
     "run": "pnpm turbo run lint --continue --filter=...[{base}]",
     "run_full": "pnpm turbo run lint --continue"},
    {"name": "unit", "scope": "changed+dependents",
     "run": "pnpm vitest run --project unit --passWithNoTests {affected_dirs}",
     "run_full": "pnpm vitest run --project unit"},
    {"name": "guards", "scope": "always", "pre_push": true,
     "run": "pnpm vitest run --project guard"},
    {"name": "secret-scan", "scope": "always", "pre_push": true,
     "run": "gitleaks git --log-opts={base}..HEAD --redact --no-banner"},
    {"name": "e2e", "scope": "ui-changed",
     "run": "pnpm exec playwright install chromium && pnpm exec playwright test"}
  ]
}
```

- `scope`: `always` runs every time; `changed` and `changed+dependents` run
  `run` with placeholders filled, or `run_full` when the gate is widened (or
  `--full`), and are skipped (outcome `skip`) when no package changed;
  `ui-changed` runs only when a changed file is under a `ui_paths` prefix or the
  gate is widened.
- `widen_on` entries: one ending in `/` is a path prefix; one containing `*` is a
  glob over the full path; anything else is a root-level file only (a nested
  `package.json` does not widen). Per-package lockfiles use globs (`*go.sum`,
  `*packages.lock.json`).
- `env` (optional, per step): an object of names to string values added to the
  environment of that step's command, e.g. `"env": {"CI": "true"}` for a test
  runner whose timeouts depend on it. Inline `VAR=x cmd` does not work in
  `cmd.exe`; this does everywhere.
- Placeholders: `{base}` (base commit sha), `{changed_dirs}` (space-separated
  package directories that changed, POSIX paths relative to the root),
  `{affected_dirs}` (the changed directories plus every workspace package that
  depends on one of them, directly or not; computed from each `package.json` in a
  `pnpm-workspace`, equal to `{changed_dirs}` for the other kinds). Use
  `{affected_dirs}` for a test command that must also run the tests of the
  packages that import the change; a tool with its own dependency filter
  (`turbo --filter=...[{base}]`) does not need it. When the gate is widened both
  placeholders are every package.
- `packages.kind`: `pnpm-workspace` (globs under `packages:` in
  `pnpm-workspace.yaml`), `go-modules` (dirs holding `go.mod`), `cargo-workspace`
  (`[workspace] members` in `Cargo.toml`), `dotnet-sln` (project dirs of the
  `.sln`). Tracks without per-package filtering use the same command for `run`
  and `run_full`; the changed set still decides `changed` scopes and e2e.
- A guard test is selected by convention, per track: TS a Vitest project named
  `guard`; Go tests named `TestGuard*`; Rust tests named `guard_*`; .NET
  `Category=Guard`.
- `pre_push: true` marks the steps `fast_guards.py` runs.
- .NET has one `typecheck` step (build with warnings as errors, analyzers
  included) and no separate `lint` step.
- Lockfiles `join.py` recognises: `pnpm-lock.yaml`, `package-lock.json`,
  `yarn.lock`, `go.sum`, `go.work.sum`, `Cargo.lock`, `packages.lock.json`, plus
  an optional `lockfiles` array in `gate.json`.

## `tools.json`

`{"gitleaks": "8.30.1"}` — the exact scanner versions CI installs (8.19 or newer,
for `gitleaks git`). `ci.yml` and `agent_setup.sh` read the same file, so the
gate and CI run the same scanner.

## Result: `gate-result.json`

```json
{
  "schema": 1,
  "kind": "branch-gate",
  "branch": "AR5-artifactspec",
  "head": "<40-hex sha>",
  "base": "<40-hex sha>",
  "base_ref": "origin/DS6-agent-delivery",
  "widened": false,
  "partial": false,
  "changed_dirs": ["apps/web"],
  "steps": [
    {"name": "typecheck", "outcome": "pass", "seconds": 41.2, "command": "pnpm turbo ...",
     "reason": null, "exit_code": 0}
  ],
  "pass": true,
  "started_at": "2026-10-10T10:12:03Z",
  "finished_at": "2026-10-10T10:19:47Z",
  "tool": "branch_gate.py 1"
}
```

`outcome` is `pass`, `fail` or `skip`. `reason` says why a step was skipped or
failed; `exit_code` is the command's exit code; `command` is null for a skipped
step. `pass` is true only when no step failed and at least one step ran.
`widened` is true when a `widen_on` entry changed or `--full` was given. A run
with `--only` or `--skip` is `"partial": true`: it is written to
`.delivery/gate-result.json`, never published, and never trusted by
`gate_verify.py`. Written to `.delivery/gate-result.json`.

**Publishing.** The result travels as a ref, never as a commit on the branch and
never as a pull-request comment: a parentless commit whose tree holds only
`gate-result.json`, at `refs/gate-results/<branch>`, force-pushed to the remote.
One ref per branch, so parallel agents never contend.

**Trust rule** (`gate_verify.py`): a result is trusted when `head` equals the
branch's current head on the remote, `base` equals the current head of the branch
it joins, `pass` is true and `partial` is not. `--allow-older-base` relaxes the second condition
to "`base` is an ancestor of the current head" (used by `join.py`, which re-gates
the joined head anyway).

## Command lines

```
branch_gate.py [--base-ref REF] [--full] [--only a,b] [--skip a,b] [--no-publish] [--fail-fast]
```
`--base-ref` defaults to `origin/<default_branch>`; the base commit is
`git merge-base HEAD <base-ref>`. Runs every selected step even after a failure
unless `--fail-fast`. `--only`/`--skip` select steps by name and make the run
partial. Prints a summary table, writes the result, publishes it unless
`--no-publish` or partial. Refuses (exit 2) on a dirty working tree.

```
gate_verify.py BRANCH [--base-ref REF] [--remote origin] [--allow-older-base] [--json]
```
Fetches the branch, the base ref and `refs/gate-results/BRANCH`; prints why a
result is or is not trusted. Exit 0 trusted and passing, 1 otherwise, 2 no result.

```
fast_guards.py [--base-ref REF]
```
Runs the `pre_push: true` steps on the checked-out commit (it takes no ref),
continuing past a failure. The `pre-push` hook calls it once per pushed ref,
passing the remote sha as `--base-ref` on an update; it skips tags, deletions
and every ref outside `refs/heads/`. A first push with no `origin/<default>`
exits 2. Never publishes a result.

```
join.py --into INTEGRATION BRANCH [BRANCH ...] [--no-gate] [--push]
```
Fetches, checks out INTEGRATION at its remote head, and for each BRANCH in order:
requires a trusted, passing result (`--allow-older-base`), then
`git merge --no-ff -m "Join BRANCH"`. For an untrusted branch it exits with
`gate_verify.py`'s code (1, or 2 for no result). A conflict touching only the
lockfile is resolved by taking INTEGRATION's version and re-running `setup`; if
`setup` fails, or the conflict touches anything else, the merge is aborted and
join exits 3 (the conflict goes to one agent). `.delivery/join-result.json`
(`{"joined": [...], "stopped_at": BRANCH|null, "conflicts": [paths]}`, plus a
`reason` when a branch is refused or a step fails) is written on success and on
failure. After the last merge it runs `branch_gate.py --base-ref origin/<default_branch>`
on the joined head (unless `--no-gate`) and pushes INTEGRATION and its result
with `--push`.

```
ci_watch.py SHA [--workflow ci.yml] [--timeout 3600] [--interval 30] [--repo OWNER/NAME]
```
Polls `gh run list --workflow WORKFLOW --commit SHA --json databaseId,workflowName,status,conclusion,event,headSha`.
Waits until at least one run of the workflow exists for SHA and every run of it
for SHA is completed. Exit 0 all `success` (or `skipped`), 1 any other
conclusion (prints the failed jobs from `gh run view --json jobs`), 2 after 5
consecutive `gh` failures, 4 timeout. It never reads a pull request's check list.

```
ci_skip_check.py
```
For the `decide` job on a default-branch push. Reads `GITHUB_SHA`,
`GITHUB_REPOSITORY`, `GITHUB_WORKFLOW_REF`; uses `gh api` to find the pull
request(s) merged as this commit, their head sha, and a successful
`pull_request` run of the same workflow file for that head, with at least one
passed job and no failed job (a draft's all-skipped run reports `success`).
Query parameters go as `gh api --method GET -f key=value` fields. If
`tree(GITHUB_SHA) == tree(head)`, writes `skip=true` and the reason to
`$GITHUB_OUTPUT`; otherwise, or on any error, `skip=false`. Always exits 0
(failing open means running the suite).

```
reach_check.py URL [URL ...] [--timeout 10]
```
GETs each URL from wherever it runs (an agent sandbox) and prints a table of
status or error. Exit 0 when all answered with a status below 500 (a 4xx means
the host answered), 1 otherwise.

```
agent_setup.sh
```
Installs Python 3.11+ if missing (apt, brew or a clear message), the scanners
pinned in `tools.json` (gitleaks from its release archive, checksum verified),
then runs `gate.json`'s `setup` commands. Idempotent.

## CI (`ci.yml`, every track)

- New first job `decide` (name: `decide: skip a tree already tested`), only on
  `push` to the default branch: checkout with `fetch-depth: 0`, run
  `python3 scripts/delivery/ci_skip_check.py`, output `skip`.
- Every other job: `needs: decide` and
  `if: ${{ !cancelled() && needs.decide.outputs.skip != 'true' && (github.event_name != 'pull_request' || !github.event.pull_request.draft) }}`.
  A skipped or failed `decide` therefore runs the suite.
- Concurrency unchanged: cancel superseded pull-request runs, never
  default-branch runs.
- TS `e2e` job: name `web E2E (§11.2)`, no `continue-on-error`; runs on ready
  pull requests; specs in `e2e/quarantine.json`
  (`[{"spec": "path", "owner": "name", "since": "YYYY-MM-DD", "reason": "..."}]`,
  `spec` relative to the repository root) run in a separate non-blocking step.
  It becomes a required check.
- Gitleaks in CI installs the version in `tools.json` (checksum verified).

## Tests (in `tools/` of this repository)

- `tools/test_delivery_gate.py` — branch_gate, gate_verify, fast_guards, join
  against throwaway git repositories with a local bare remote and a `gate.json`
  whose steps are small Python commands. Every trust-rule branch and every exit
  code is exercised.
- `tools/test_delivery_ci.py` — ci_watch and ci_skip_check with a stub `gh` on
  `PATH`, reach_check against a local HTTP server, and a structural check of the
  four `ci.yml` files (decide job, job conditions, e2e not advisory).
- `tools/test_model_profiles.py` — every SKILL.md's `model` and `effort` match
  the profile table.

Each test proves its check can fail, like `tools/test_spec_check.py`.
