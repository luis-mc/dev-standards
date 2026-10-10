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
| `scripts/delivery/cleanup.py` | same | cleanup |
| `scripts/delivery/artifact_prune.py` | same | ci |
| `.github/workflows/train-cleanup.yml` | `tooling/shared/.github/workflows/train-cleanup.yml` | cleanup |
| `.github/workflows/artifact-prune.yml` | `tooling/shared/.github/workflows/artifact-prune.yml` | ci |
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

`.delivery/` (local results and step logs) is added to the generated `.gitignore`.

Repository setting, applied by tech-stack-setup with
`gh api -X PATCH repos/{owner}/{repo} -F delete_branch_on_merge=true`: the
platform deletes a merged pull request's head branch. `train-cleanup.yml` covers
the branches that setting cannot see (drafts merged into an integration branch).

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
  "timeout_minutes": 30,
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
- `setup`: commands that install dependencies from the lockfile in frozen mode
  (`pnpm install --frozen-lockfile`, `go mod download` with `-mod=readonly`
  builds, `cargo fetch --locked`, `dotnet restore --locked-mode`).
  `branch_gate.py` runs them, in order, as its first step, named `setup`; a
  stale lockfile fails there. `agent_setup.sh` and `join.py` run the same
  commands. Never a non-frozen install: a branch that changes dependencies
  commits the regenerated lockfile.
- `timeout_minutes` (optional, integer >= 1, default 30): the wall-clock limit
  for one `branch_gate.py` run, setup included.
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
    {"name": "setup", "outcome": "pass", "seconds": 6.0, "command": "pnpm install --frozen-lockfile",
     "reason": null, "exit_code": 0, "log": ".delivery/logs/setup.log"},
    {"name": "typecheck", "outcome": "pass", "seconds": 41.2, "command": "pnpm turbo ...",
     "reason": null, "exit_code": 0, "log": ".delivery/logs/typecheck.log"}
  ],
  "pass": true,
  "timed_out": false,
  "started_at": "2026-10-10T10:12:03Z",
  "finished_at": "2026-10-10T10:19:47Z",
  "tool": "branch_gate.py 1"
}
```

`outcome` is `pass`, `fail` or `skip`. `reason` says why a step was skipped or
failed; `exit_code` is the command's exit code; `command` is null for a skipped
step. `log` is the step's combined output, relative to the root (absent for a
skipped step). `pass` is true only when no step failed, the `setup` step passed,
at least one other step ran, and `timed_out` is false. `timed_out` is true when
the time limit stopped the gate.
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
branch_gate.py [--base-ref REF] [--full] [--only a,b] [--skip a,b] [--no-publish]
               [--keep-going] [--no-setup] [--timeout-minutes N]
```
`--base-ref` defaults to `origin/<default_branch>`; the base commit is
`git merge-base HEAD <base-ref>`.

- **Setup first.** Runs `gate.json`'s `setup` commands as the step `setup`
  before any other. When it fails, every other step is `skip` with reason
  `setup failed`, and the summary says a stale lockfile is the usual cause.
  `--no-setup` skips it and makes the run partial (never trusted), for repeated
  local runs.
- **Fail fast.** Stops at the first failed step; the steps after it are `skip`
  with reason `an earlier step failed`. `--keep-going` runs every selected step
  (a failed setup still stops the run). `--fail-fast` is still accepted and
  does nothing.
- **Time limit.** `--timeout-minutes` overrides `timeout_minutes` (default 30).
  When the limit is reached, the running step's whole process tree is killed
  (a new process group on POSIX; `taskkill /T /F` on Windows), that step is
  `fail` with reason `timed out after N min`, the rest are `skip` with reason
  `gate timed out`, `timed_out` is true, the result is written and published,
  and the exit code is 4.
- **Logs.** Each step's combined output goes to the terminal and to
  `.delivery/logs/<step>.log`. A failed step prints
  `FAIL <step>: <reason> (exit N, Ns) - log: <path>` and the last 40 lines of
  its output after the summary table.

`--only`/`--skip` select steps by name and make the run partial. Prints a
summary table, writes the result, publishes it unless `--no-publish` or
partial. Refuses (exit 2) on a dirty working tree. Exit 0 pass, 1 a step
failed, 2 usage, 4 timed out.

```
gate_verify.py BRANCH [--base-ref REF] [--remote origin] [--allow-older-base] [--json]
```
Fetches the branch, the base ref and `refs/gate-results/BRANCH`; prints why a
result is or is not trusted. Exit 0 trusted and passing, 1 otherwise, 2 no result.

```
fast_guards.py [--base-ref REF]
```
Runs the `pre_push: true` steps on the checked-out commit (it takes no ref),
continuing past a failure. Each step has a limit of 5 minutes (killed like a
gate step, outcome `fail`, reason `timed out after 5 min`). A failure is
reported the way the gate reports one (`FAIL <step>: ...`, the log path, the
last 40 lines), so a blocked push always says which check failed and why. The `pre-push` hook calls it once per pushed ref,
passing the remote sha as `--base-ref` on an update; it skips tags, deletions
and every ref outside `refs/heads/`. A first push with no `origin/<default>`
exits 2. Never publishes a result.

After the guards pass, the `pre-push` hook runs `pre-push.local` from its own
directory when that file exists, with the same arguments and the same stdin (it
reads the ref lines once and feeds both); a non-zero exit fails the push.
`pre-push.local` is the project's own pre-push check, moved there at install so
the template never overwrites it.

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
with `--push`. Before the first fetch it runs `cleanup.py --local` (best effort:
its failure is printed and never stops the join), so worktrees of trains
already merged are gone before new ones are made.

```
cleanup.py [--pr N] [--remote NAME] [--local] [--remote-only] [--dry-run] [--json] [--repo OWNER/NAME]
```
Removes what a merged train leaves behind (STACKSPEC §13.6). A branch is
**finished** when it is not the default branch, has no open pull request, and
either (a) a pull request with it as head is merged, or (b) it is the head of a
draft whose base is a finished integration branch and whose commits are
contained in that branch. A branch whose pull requests were all closed without
merging is **kept** and listed. For each finished branch:

- remote (skipped with `--local`): delete the branch and
  `refs/gate-results/<branch>` (`git push --no-verify REMOTE --delete ...`; a
  ref already gone is not an error);
- local (skipped with `--remote-only`): remove every worktree checked out on it
  (`git worktree remove`, with `--force --force` for a locked one) unless the
  worktree has uncommitted changes or commits not on the remote, in which case
  it is kept and listed; then delete the local branch (`git branch -D`, since
  squash merges are not ancestors) unless a kept worktree still holds it;
  finally `git worktree prune`.

Never touches the default branch, a detached worktree (such as
`.claude/worktrees/artifacts-record`), the main working tree, or a branch it
cannot classify (an error from `gh` keeps the branch). With `--pr N` only the
train of that merged pull request is considered (its head branch and every
branch whose pull request had that head as base); without it, every branch on
the remote. `--local` treats only local branches and worktrees: after
`git fetch --prune`, a local branch is finished when its pull request is merged
(when `gh` works) or, without `gh`, when its upstream is gone from the remote.
Prints one row per branch: `deleted`, `kept: <reason>`, or `would delete` with
`--dry-run`. Exit 0 when it ran (kept branches are not a failure), 1 when a
deletion it attempted failed, 2 usage or no repository.

```
artifact_prune.py [--repo OWNER/NAME] [--keep 1] [--dry-run] [--json]
```
Lists the repository's build artifacts with
`gh api --paginate "repos/{repo}/actions/artifacts?per_page=100"`, ignores
expired ones, groups the rest by `name`, keeps the newest `--keep` of each name
(by `created_at`, then `id`, descending) and deletes the others with
`gh api --method DELETE repos/{repo}/actions/artifacts/{id}`. `--repo`
defaults to `GITHUB_REPOSITORY`, then `gh repo view --json nameWithOwner`.
Prints one row per name: kept id(s), deleted count, bytes freed. Exit 0 done,
1 a deletion failed, 2 `gh` failed to list, or usage.

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
- `artifact-prune.yml` (every track): `on: workflow_run` (`workflows:` lists
  every workflow of the repository that uploads an artifact: `CI` in the
  template; a product that adds a release workflow adds its name here),
  `types: [completed]`; plus a daily `schedule` and `workflow_dispatch`. One
  job, `permissions: actions: write`, `GH_TOKEN: ${{ github.token }}`, runs
  `python3 scripts/delivery/artifact_prune.py`. Artifact names are stable per
  kind (no version, run number or sha in the name), or pruning cannot group
  them.
- `train-cleanup.yml` (every track): `on: pull_request: types: [closed]`, job
  `if: github.event.pull_request.merged`, `permissions: contents: write,
  pull-requests: read`, checkout with `fetch-depth: 0`, then
  `python3 scripts/delivery/cleanup.py --remote-only --pr ${{ github.event.pull_request.number }}`
  with `GH_TOKEN: ${{ github.token }}`.

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
- `tools/test_delivery_cleanup.py` — cleanup.py against throwaway repositories
  with a local bare remote, linked worktrees and a stub `gh`: finished, kept,
  locked, dirty and detached cases, `--pr`, `--local`, `--remote-only`,
  `--dry-run`, join.py's best-effort call, and the structure of
  `train-cleanup.yml`.
- `tools/test_artifact_prune.py` — artifact_prune.py with a stub `gh` serving
  artifact pages: grouping, ties, expired, `--keep`, `--dry-run`, a failed
  deletion, pagination, and the structure of `artifact-prune.yml`.

Each test proves its check can fail, like `tools/test_spec_check.py`.
