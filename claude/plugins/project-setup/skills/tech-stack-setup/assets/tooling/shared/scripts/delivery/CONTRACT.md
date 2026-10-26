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
| `scripts/delivery/runner_health.py` | same (runner labels against online runners; used by `join.py` and `ci_watch.py`) | gate |
| `scripts/delivery/runner_plan.py` | same (heavy-job wrapper: waits for train CI, one heavy job at a time, memory floor, pauses and always resumes the local runner; `runners` subcommand reports offline CI runners, repairs them with the project's `runners[].repair` commands every 5 minutes and re-runs the CI they cancelled; DELIVERYSPEC DL-50, D6, D6a) | gate |
| `scripts/delivery/train_freeze.py` | same (called by the `pre-push` hook) | gate |
| `scripts/delivery/ci_skip_check.py` | same | ci |
| `scripts/delivery/reach_check.py` | same | ci |
| `scripts/delivery/cleanup.py` | same | cleanup |
| `scripts/delivery/artifact_prune.py` | same | ci |
| `scripts/delivery/shard_balance.py` | same (balanced test shards from a timings file; `update` refreshes it from a runner's JSON report; DS9) | ci |
| `scripts/delivery/area_select.py` | same (changed paths + the project's area map -> the jobs and test areas a change needs; DS9) | ci |
| `scripts/delivery/ci-areas.json`, `scripts/delivery/ci-timings.json` | `tooling/ts/scripts/delivery/` (the area map and the shard timings; the project edits them) | ci |
| `.github/workflows/nightly-full.yml` (ts only) | `tooling/ts/.github/workflows/nightly-full.yml` | ci |
| `scripts/delivery/delivery_log.py` | same | cleanup |
| `scripts/delivery/smoke_packaged.py` | same | ci |
| `scripts/delivery/run_suite.py` | same (declared suites, named cases, per-machine times in `.delivery/suite-times.json`; STACKSPEC 13.8) | gate |
| `scripts/delivery/session_guard.py` | same (Claude Code PreToolUse hook for Bash: test guard and ready-PR guard; exit 2 refuses; STACKSPEC 13.8) | gate |
| `scripts/delivery/suites.json` | per product (`suites`: name, `full`, `cases` with `{cases}`, `full_args`, `ci_step`, `measure`); or `.claude/suites.json`, or `$SUITES_JSON` | gate |
| `scripts/delivery/smoke.json` | `tooling/<track>/scripts/delivery/smoke.json` | ci |
| `.github/workflows/package.yml` | `tooling/<track>/.github/workflows/package.yml` | ci |
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
  "widen_on": ["package.json", "turbo.jsonc", ".github/", "scripts/delivery/"],
  "lockfile_scope": "pnpm-importers",
  "inert_paths": ["docs/**"],
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
- `lockfile_scope` (optional, default `widen`): how a lockfile change is scoped.
  `widen`: the lockfile is whatever `widen_on` says (an entry there widens the gate
  to every package; a gate.json written before this key keeps working, and a
  lockfile still listed in `widen_on` widens whatever the scope says).
  `pnpm-importers`: `pnpm-lock.yaml` is compared with its version at the base; each
  entry of its `importers:` section whose text differs is a package whose
  dependencies changed, and that package counts as changed (its steps run scoped,
  its dependents are affected, a ui package triggers `ui-changed`). The gate
  widens instead when the change cannot be pinned to a package: the root importer
  (`.`) changed, the lockfile differs only outside `importers:` (a transitive
  resolution), or the lockfile was added or removed. `per-package`: the lockfiles
  live next to their package (`go.mod`/`go.sum` per Go module, `packages.lock.json`
  per .NET project), so they are not `widen_on` entries and a change makes just
  that package changed; a root-level file such as `go.work` or `go.work.sum`
  still widens. Per track: `ts` pnpm-importers; `go` and `dotnet` per-package;
  `rust` widen, because `Cargo.lock` is one file for the workspace and mapping
  its changed entries to the crates that depend on them needs a dependency graph
  the gate does not build, so any change to it widens. (The older `lockfiles`
  array is unrelated: it only lists extra files `join.py` may resolve.)
- `inert_paths` (optional, default `["docs/**"]`): globs (same rules as
  `widen_on`) for paths whose change cannot affect what a gate result tested.
  `gate_verify.py` keeps a result valid across a move of the base that touches only
  these paths. tech-stack-setup writes the key into each track's `gate.json`; when
  luismc-artifacts is enabled it adds `docs/artifacts/**` only if `docs/**` is not
  already listed, and the default already covers it.
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
- `join_guards` (optional, boolean, default `true`): whether `join.py`'s light check also runs
  the `pre_push` steps (`fast_guards.py`). A step's optional `"join": true|false` adds it to,
  or drops it from, that check (default: `typecheck` and `lint` are in, the rest out).
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
to "`base` is an ancestor of the current head" (used by `join.py`, which runs its light check
on the joined head unless its tree equals a trusted joined branch's tree).

**Inert moves of the base.** Without `--allow-older-base`, a `base` that is not the
current head still passes when it is an ancestor of the current head and the
difference between them (`git diff --name-only base current`) touches only
`inert_paths`. The net difference decides, so a merge commit counts by its diff
and a change made and reverted inside the range counts as nothing. The verdict
gets `"inert_commits": N` (the commits in `base..current`; `null` otherwise) and
the output says `base moved only by inert commits: N`. A base that is not an
ancestor (a rewound branch) is stale as before. `--strict-base` turns the
exception off. The exception is safe because the ready pull request's CI still
tests the real merge, and it SHOULD be used, not required.

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
gate_verify.py BRANCH [--base-ref REF] [--remote origin] [--allow-older-base] [--strict-base] [--json]
```
Fetches the branch, the base ref and `refs/gate-results/BRANCH`; prints why a
result is or is not trusted. Exit 0 trusted and passing, 1 otherwise, 2 no result.

```
fast_guards.py [--base-ref REF] [--commit SHA]
```
Runs the `pre_push: true` steps, continuing past a failure. With `--commit SHA`
different from `HEAD`, it checks that commit out in a temporary detached
worktree under `.delivery/push-check/` (shared object store, no install: the
main checkout's dependency directories, such as every `node_modules`, are
linked into it with a symlink or a Windows junction, and Rust builds share the
main checkout's target directory through `CARGO_TARGET_DIR`), runs the steps
there, and always
removes the worktree afterwards, also on failure or interruption. Without
`--commit`, or when it equals `HEAD`, it runs in place as before.

**Known limit (accepted).** The temporary worktree borrows the checkout's
dependency directories instead of installing. A workspace package imported by a
guard therefore resolves to the checked-out version of that package, not the
pushed one. Guards scan files and rarely import workspace code; a guard that
does must not rely on the pushed version of that package at pre-push time (the
branch gate, which installs, checks it properly). Each step has a limit of 5 minutes (killed like a
gate step, outcome `fail`, reason `timed out after 5 min`). A failure is
reported the way the gate reports one (`FAIL <step>: ...`, the log path, the
last 40 lines), so a blocked push always says which check failed and why. The `pre-push` hook calls it once per pushed ref,
passing the pushed sha as `--commit` and the remote sha as `--base-ref` on an
update; it skips tags, deletions
and every ref outside `refs/heads/`. A first push with no `origin/<default>`
exits 2. Never publishes a result.

After the guards pass, the `pre-push` hook runs `pre-push.local` from its own
directory when that file exists, with the same arguments and the same stdin (it
reads the ref lines once and feeds both); a non-zero exit fails the push.

**Train freeze** (`train_freeze.py --branch NAME`, called by the hook for every pushed
`refs/heads/*` ref before the guards). A branch is *frozen* when an open, non-draft pull
request has it as head (an integration branch, `*-integration`, or whatever head the ready
pull request has) and a workflow run of that pull request's head commit has not completed.
A frozen branch refuses the push (exit 1), naming the pull request and the run. Allowed:
CI finished, passed or failed (fix forward works); the ready pull request closed unmerged
(the train is abandoned); a draft pull request; no pull request; no run listed yet. When
GitHub cannot say (offline, `gh` missing, an API error, no answer within 8 s) the push is
allowed with a warning (D4): the ready pull request's CI still decides the merge.
`DELIVERY_FREEZE_OVERRIDE=1` allows the push and prints that the running CI will restart
(D9). A branch that is late rides the next train. The hook stays fast: one `gh pr list
--head NAME --state open` call, and a second, `gh run list --commit SHA`, only when a ready
pull request exists. Tags, deletions and refs outside `refs/heads/` are not checked.
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
failure. After the last merge it runs a **light check** on the joined head (unless `--no-gate`): the
`setup` commands, then the steps of `gate.json` named `typecheck` and `lint` (a step's own
`"join": true` or `false` overrides the name, so a project may add or drop one), each with its own
scope against `origin/<default_branch>` (`delivery_common.build_context`), so `{changed_dirs}` is the
set of packages the merges touched (a widened join runs the `run_full` commands); then the fast
guards (`fast_guards.py`, the `pre_push` steps), unless `gate.json` sets `"join_guards": false`
(default `true`). It is never the branch gate: no test, build, scan beyond the guards or
end-to-end step, no result is written to `refs/gate-results/`, no sandbox gate is awaited before
the ready pull request, and a fix made after a failed check is not re-gated. The ready pull
request's CI is the one full suite. Each step's time is printed and written to
`join-result.json` as `quick_check` (`pass`, `seconds`, `changed_dirs`, `affected_dirs`, and `steps` with
`name`, `outcome`, `seconds`, the guards as `fast-guards`); a package-less join (only docs changed)
passes after the install and the guards. A failed check exits 1 (4 on timeout) and pushes nothing.
`--push` pushes INTEGRATION. **The check is skipped, and the output says so,
when the joined tree equals the tree of a joined branch's head whose gate result
`gate_verify.py` trusts for that head and for the same base the join would use
(`origin/<default_branch>`, without `--allow-older-base`)**: those files were
already gated against that base. Neither publishes a result for INTEGRATION.
Last, before the join says it is done, **runner health** (`runner_health.py`, D5) prints a
warning for every job whose `runs-on` labels no online runner carries, and never stops the
join; it is recorded as `runner_health` in `join-result.json` (`status` `ok`, `warn` or
`skipped`, with `warnings` and `reason`). It reads every `.github/workflows/*.yml|yaml`,
resolves `${{ fromJSON(vars.NAME || '"default"') }}` through the repository variable (`gh
variable get`; the default is used, with a note, when it cannot be read), counts
`ubuntu-*`, `windows-*` and `macos-*` label sets as available, and for a `self-hosted` set
needs one online runner (`gh api repos/{owner}/{repo}/actions/runners`) carrying every label.
Listing runners needs admin rights; without them the check prints that it was skipped, and
why. Hosted-only workflows make no runner call. Before the first fetch it runs `cleanup.py --local` (best effort:
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

**Scaffolding branches.** A local branch with no pull request is finished
when it has no commits outside the default branch on the remote
(`git rev-list --count <remote>/<default>..<branch>` is 0) and no worktree
holds it, or the only worktree holding it is clean; agent tools leave such
branches behind (e.g. `worktree-agent-<id>`). It is removed locally only (it was
never pushed); a scaffolding branch whose name exists on the remote is
classified like any other branch. Every mode that touches local branches
(default, `--local`) removes them, also without `gh`, since the rule needs no
pull-request state.

**Stale push-check folders.** `cleanup.py` (default and `--local`) also sweeps
`.delivery/push-check/*` left by a pre-push check that was killed: for each
entry whose owning process (the `<pid>` suffix) is not running, it removes the
dependency links first (never their targets), then the worktree
(`git worktree remove --force`, or the folder plus `git worktree prune` when git
no longer knows it). Rows: `push-check <name>  deleted` or `kept: <reason>`.

Never touches the default branch, a detached worktree (such as
`.claude/worktrees/artifacts-record`), the main working tree, or a branch it
cannot classify (an error from `gh` keeps the branch). With `--pr N` only the
train of that pull request is considered (exit 2 unless N is merged into the
default branch) (its head branch and every
branch whose pull request had that head as base, and every **joined** branch:
a remote or local branch whose tip is an ancestor of the merged pull request's
head commit, `headRefOid`, which is not the default branch, not an ancestor of
`<remote>/<default>` (a branch with no work of its own), and has no open pull
request; a branch with any commit outside that head, on the remote or locally, is
not touched, and a `gh` error keeps it. A squash merge leaves the integration
branch's joined branches behind otherwise. They are then removed like any
finished branch, worktree rules included); without it, every branch on
the remote. `--local` treats only local branches and worktrees: after
`git fetch --prune`, a local branch is finished when its pull request is merged.
Without a working `gh`, `--local` deletes nothing: it lists each branch whose
upstream is gone as `would delete (needs gh to confirm)` and exits 0.
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
A run that executed no job (conclusion `skipped`, or a push run whose jobs were all skipped, "already
tested on the pull request") is not a pass when SHA is the head of an open pull request
(`gh api repos/{owner}/{repo}/commits/SHA/pulls`, read only when such a run is the whole answer): it keeps
waiting ("no real run yet", exit 4 on timeout) until a run that executed jobs, the pull_request run,
has completed. Green needs every executed run to succeed and at least one to have executed; without an
open pull request `skipped` still counts as success.
While it waits (`--queue-warn-seconds`, default 600) it reads the jobs of each unfinished run
(`gh api repos/{owner}/{repo}/actions/runs/ID/jobs`) and warns **once per job** that has been
queued longer, when no online runner carries the job's labels, or, when the runners cannot
be listed, that the job has been queued 10+ min. GitHub-hosted label sets are not checked.
A warning never changes the exit code (D5).
Slowest job (TC8): once every run is complete, whether it passed or not, it prints one summary
after the verdict: per run, the wall time (first job start to last job end), the slowest job with
its share of the wall time, and that job's two slowest steps, from `gh run view ID --json jobs`.
It is information for §13.1's split-the-dominant-job advice; it never changes the exit code,
and when the jobs cannot be read or lack times it prints nothing extra.

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
  every workflow of the repository that uploads an artifact: `CI` and `Package` in the
  template; a product that adds a release workflow adds its name here),
  `types: [completed]`; plus a daily `schedule` and `workflow_dispatch`. One
  job, `permissions: actions: write`, `GH_TOKEN: ${{ github.token }}`, runs
  `python3 scripts/delivery/artifact_prune.py`. Artifact names are stable per
  kind (no version, run number or sha in the name), or pruning cannot group
  them.
- `train-cleanup.yml` (every track): `on: pull_request: types: [closed]`, job
  `if: github.event.pull_request.merged && github.event.pull_request.base.ref == github.event.repository.default_branch`
  (a draft into an integration branch also closes as merged when `join.py`
  pushes; the train goes only when the ready pull request merges),
  `permissions: contents: write,
  pull-requests: read, actions: read`, checkout with `fetch-depth: 0`, then
  `python3 scripts/delivery/cleanup.py --remote-only --pr ${{ github.event.pull_request.number }}`
  with `GH_TOKEN: ${{ github.token }}`.

### DS9 — generic CI speed-ups (`shard_balance.py`, `area_select.py`, `nightly-full.yml`)

- `shard_balance.py --shard K/N [--timings FILE] [--glob PATTERN]... [--files-from FILE|-] [FILE...] [--join SEP]`
  prints the test files of shard K, longest first onto the lightest shard, sorted, deterministic. The
  timings file (default `scripts/delivery/ci-timings.json`, `{"seconds": {"path": s}}` or a flat map)
  is committed; a file without a figure gets the median of the measured files in the list (the whole
  file's median, then 1 s), a missing file weighs every file the same. `shard_balance.py update --report
  FILE... [--timings FILE] [--format auto|vitest|playwright] [--root DIR] [--prune-missing]` folds a
  vitest/jest or Playwright JSON report in (a file in several reports is averaged, an unmeasured file keeps
  its figure). Exit 0, 2 usage or unreadable file, 3 nothing to split.
- `area_select.py [--map FILE] [--base REF | --changed-file FILE|- | PATH...] [--all] [--github-output] [--json]`
  reads the changed paths and the committed map (default `scripts/delivery/ci-areas.json`: `jobs`,
  `always_jobs`, `run_everything`, `docs`, `areas` -> `paths`, `jobs`, `tests`). Per path: `run_everything`
  -> mode `all`; `docs` -> nothing; an area's `paths` -> that area; no match -> `all` (an unknown path is never
  skipped). No path at all is `all`; only documentation is `none`; `--all` forces `all`. Output `mode`,
  `areas`, `tests`, `<job>=true|false`, `reason`; `--github-output` appends them to `$GITHUB_OUTPUT`. Exit 0, 2.
- ts `ci.yml`: a `plan` job (`runner plan: which jobs this change needs`) runs `area_select.py --base <PR base>`
  on pull requests and `--all` otherwise. `integration` and `e2e-shard` add `needs.plan.outputs.<job> != 'false'`
  to the decide-aware condition (so a failed or empty plan runs them); the `e2e` summary accepts a planned skip
  and still fails when a shard that ran failed. `verify` is never planned away. The e2e shards run the files
  `shard_balance.py` assigns (fallback: Playwright's `--shard`).
- ts `nightly-full.yml`: `schedule` + `workflow_dispatch`; runners from `NIGHTLY_RUNS_ON`, else `CI_RUNS_ON`,
  else `ubuntu-latest`; job `changed` (default branch only) compares the default branch head with the
  `head_sha` of the last successful run of this workflow and outputs `run=false` when equal; the integration
  and browser jobs (every file, every spec) need `run == 'true'` and test the compared commit. go, rust and
  dotnet get none: their `ci.yml` has no area selection to catch up on.

## Tests (in `tools/` of this repository)

- `tools/test_delivery_gate.py` — branch_gate, gate_verify, fast_guards, join (light check,
  train freeze, runner health)
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
- `tools/test_smoke_packaged.py` — smoke_packaged.py against a fake packaged program
  that starts workers: all up, one missing, the program exiting, health probes,
  the declaration's errors, the process tree stopped on every path, and the
  structure of the tracks' `package.yml` and `smoke.json`.
- `tools/test_artifact_prune.py` — artifact_prune.py with a stub `gh` serving
  artifact pages: grouping, ties, expired, `--keep`, `--dry-run`, a failed
  deletion, pagination, and the structure of `artifact-prune.yml`.

- `tools/test_ci_speedups.py` — shard_balance.py (greedy split, median for unknown files, glob and
  stdin input, `update` from vitest and Playwright reports), area_select.py (areas, shared, unknown,
  docs-only, `--base` on a throwaway git repository, `$GITHUB_OUTPUT`), the starter files, the structure
  of `nightly-full.yml` and its compare step run with bash against a stub `gh`; scripts with one rule
  broken must each fail a scenario.

Each test proves its check can fail, like `tools/test_spec_check.py`.

## STACKSPEC 7.1.0 additions

### U1 — affected end-to-end specs (`gate.json` `e2e_map`, optional)

```json
"e2e_map": {
  "specs": [{"spec": "e2e/checkout.spec.ts", "paths": ["apps/web/src/checkout/", "packages/cart/"]}],
  "full_on": ["playwright.config.ts", "packages/contract/", "apps/web/app.config.ts"]
}
```
When the e2e step runs at the gate (scope `ui-changed`) and `e2e_map` exists:
every changed file under a `ui_paths` prefix must match some spec's `paths`
(same prefix/glob rules as `widen_on`), and no changed file may match
`full_on`; then the step's command gets `{e2e_specs}` = the matched specs,
space-separated, sorted. Otherwise (no map, an unmapped UI file, a `full_on`
hit, a widened gate) `{e2e_specs}` is empty and the step runs `run_full` (the
whole suite). The result entry for e2e adds `"selection": "affected"|"full"` and
`"specs": [...]`. The ready PR's CI is untouched: it always runs every spec.
Template TS `gate.json`: `"run": "pnpm exec playwright install chromium && pnpm exec playwright test {e2e_specs}"`,
`"run_full"` without the placeholder, and an example `e2e_map` commented in the
README (not in gate.json; a product writes its own).

**Without an `e2e_map` (DL4), `pnpm-workspace` only.** When the e2e step has the
`{e2e_specs}` placeholder and the gate is not widened, the specs come from the
workspace dependency graph. The ui packages the change affects are the changed
packages under `ui_paths` (a file there that is in no package, or a lockfile
change that touches a ui package, counts) and every ui package that depends on
one of them. Each affected ui package contributes its spec directory:
`<package>/e2e` or, failing that, `e2e/<last segment of the package path>`, when it
exists. The placeholder becomes those directories (sorted, space-separated,
Playwright takes them as path filters), and the result records
`"selection": "affected"`. It is the whole suite instead (placeholder empty) when
any changed ui package neither has a spec directory nor is imported by an affected
ui package that has one, when a ui file is in no package, or for any other kind of
workspace. A present `e2e_map` wins and is applied exactly as above.

### U2 — the gate fetches its base

`build_context` runs `git fetch --quiet --no-tags <remote> <branch>` for the
base ref (`origin/<x>` → remote `origin`, branch `x`) before the merge base.
On failure (offline, no remote) it warns `base not fetched: <reason>; using the
local ref` and continues. The result adds `"base_fetched": true|false`.
`gate_verify` is unchanged (it already compares with the remote head).
`fast_guards.py` fetches the same way.

### U3 — pre-push base by fork point

For a ref the remote does not have yet (remote sha all zeros), the hook passes
`--base-ref auto`. `fast_guards.py --base-ref auto` picks, among the remote's
branches (`refs/remotes/<remote>/*`, excluding `HEAD` and the pushed branch
itself), the one whose merge base with the pushed commit is nearest to it
(fewest commits in `<merge-base>..<commit>`; ties → the default branch, then
name order), and prints `base: <ref> (fork point)`. No candidates → the default
branch.

### U4 — pinned scanner checksums (`tools.json`)

```json
{"gitleaks": {"version": "8.30.1",
  "sha256": {"linux_x64": "...", "linux_arm64": "...", "darwin_x64": "...", "darwin_arm64": "...", "windows_x64": "..."}}}
```
`agent_setup.sh` and every `ci.yml` read version and the platform's SHA-256
from here and verify the downloaded archive against it; they no longer download
the release's checksums file. The old form `{"gitleaks": "8.30.1"}` is still
read, with a warning, and then falls back to the checksums file.
`scripts/delivery/tools_pin.py gitleaks <version>` (maintainer use) downloads
the release's checksums once and rewrites `tools.json` with the five SHA-256
values. The shipped `tools.json` carries real values for 8.30.1.

### U5 / U6 — runners as a setting

Every workflow template's `runs-on` reads a repository variable:
`runs-on: ${{ fromJSON(vars.CI_RUNS_ON || '"ubuntu-latest"') }}` (a JSON string
or array of labels, e.g. `["self-hosted","linux"]`). Jobs that need a specific
OS keep their own label. tech-stack-setup asks hosted or self-hosted and sets
it with `gh variable set CI_RUNS_ON --body '<json>'` (asks before changing an
existing repository).

### U8 — one ready-PR CI at a time

Every track's `ci.yml` concurrency becomes:
```yaml
concurrency:
  group: ${{ vars.CI_SERIAL == 'true' && github.event_name == 'pull_request' && 'ci-ready-serial' || format('ci-{0}', github.ref) }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' && vars.CI_SERIAL != 'true' }}
```
With `CI_SERIAL=true` (set by tech-stack-setup for self-hosted or shared
runners) ready PRs' runs queue one at a time and are never cancelled; drafts
still skip. Default-branch runs keep their own group.

### U9 — Windows-safe guard starters

Every guard starter normalises paths to `/` before matching (TS
`replaceAll('\\', '/')`, Go `filepath.ToSlash`, Rust `.replace('\\', "/")`,
.NET `.Replace('\\', '/')`). `template-build.yml` runs its Go, Rust and .NET jobs
on `windows-latest` as well as `ubuntu-latest`.

### U7 — change notes (`scripts/delivery/change_notes.py`)

A change note is `docs/specs/changes/<task-id>-<slug>.md`:
```markdown
---
spec: docs/specs/stack-profile.md      # the spec file it changes
change: minor                          # patch | minor | major
---
One or two sentences for the change log.
```
- `change_notes.py check [--base-ref REF]` (a `gate.json` step `change-notes`,
  scope `always`, `pre_push: true`): on a branch that is not a release branch,
  fails when the diff against the base changes a spec's `**Version:**` line or
  its change-log section, or any `CHANGELOG*` file, and names the files and the
  fix ("add a change note instead"). A spec is any file listed in `gate.json`
  `specs` (default: `docs/specs/*.md`); its change-log section is the heading
  named in `gate.json` `changelog_heading` (default: a heading starting
  `What changed`). Release branches: `gate.json` `release_branches` (globs;
  default `["*-integration", "release/*"]`).
- `change_notes.py check --staged`: the same check on the staged changes (index
  against HEAD), run by the pre-commit hook so the edit is refused at commit time
  (STACKSPEC §13.8); a repository with no commit yet or no change-note settings
  passes.
- `change_notes.py fold` (run on a release branch before the ready PR): for
  each spec with notes, bumps `**Version:**` by the highest change kind, writes
  one change-log entry under the change-log heading (new version, date, one
  bullet per note), deletes the folded notes, prints a summary. Idempotent; no
  notes → nothing to do.
- `--config PATH` (both commands) reads the settings from that JSON file
  (relative to the repository root; no `schema` or `steps`) instead of
  `gate.json`. It takes the same keys and two more, both also valid in
  `gate.json`: `changelog_headings` (spec path → heading, overriding
  `changelog_heading` for that spec; `""` = the spec has no change log, so only
  its version is guarded and bumped) and `plugins` (globs of plugin manifests).
  A note may also carry `plugin: <path of plugin.json>` (with or without
  `spec:`); `check` refuses a `"version"` edit in a listed manifest off release
  branches, and `fold` bumps that `"version"` by the highest kind of the notes
  naming it (no change-log entry).
- Template `gate.json`s get the step; the README documents notes and fold.

### DS39 — skip a merge that differs only in ignored paths

`ci_skip_check.py` today skips a default-branch run only when the pushed tree
equals a passed PR head's tree. Commits that land on the default branch between
the PR's last run and its merge (docs, the luismc-artifacts record, Markdown,
mobile apps with their own workflows) make the trees differ, so the full suite
ran again for nothing. New rule: skip when `git diff --name-only <head> <sha>`
is empty **or every changed path matches the workflow's own push
`paths-ignore` list** (read from the workflow file at `GITHUB_WORKFLOW_REF`; a
minimal parser for that one list, no YAML library), so "safe to skip" means
exactly "CI would not have run for these files". An optional `gate.json`
`ci_skip_paths` list replaces it when present. Glob semantics follow GitHub's
filter patterns (`**`, `*`, trailing `/**`). The reason line names the PR, the
head and the ignored paths that differed. Anything else, a parse failure, or no
`paths-ignore` list → `skip=false` (fail open, as now). Every track's `ci.yml`
lists at least `docs/**` and `**/*.md` under push `paths-ignore` (plus the
mobile app folders when those have their own workflows), so docs-only pushes,
such as the record commits, start no run at all.

## STACKSPEC 8.0.0 additions

### DL5 — build-artifact workflows run only when their inputs change

A workflow that builds a shipped artifact (installer, bundle, package, image) is
its own workflow, not a job of `ci.yml`, so the paths that feed it can filter it.
`tooling/<track>/.github/workflows/package.yml` (workflow name `Package`) is the
template: `on: pull_request` (types as `ci.yml`, drafts skipped by the job-level
`if`) and `push` to the default branch, both with a `paths:` list of the
directories and manifests that feed the packaged program, the workflow itself and
`scripts/delivery/smoke.json`, followed by the exclusions `'!docs/**'` and
`'!**/*.md'` (a documentation-only or record-only merge never builds); and
`workflow_dispatch:` so a build can always be started by hand. The runner is
`vars.CI_RUNS_ON` like every workflow. Its artifact has one stable name
(`packaged-program`) and `artifact-prune.yml` lists `Package`. A product adjusts
the `paths:` list to its own layout; a product with no packaged program deletes
`package.yml` and its `artifact-prune.yml` entry.

### DL9 — `smoke_packaged.py` and `smoke.json`

```
smoke_packaged.py [--config scripts/delivery/smoke.json] [--start CMD] [--expect TEXT ...]
                  [--health URL ...] [--timeout SECONDS] [--cwd DIR]
```

`scripts/delivery/smoke.json` declares the check:
`{"smoke": {"start": "./dist/app", "expect": ["api ready", "worker-queue ready"], "health": ["http://127.0.0.1:8080/healthz"], "timeout_s": 60, "cwd": "."}}`.
`start` runs the PACKAGED program (executable, installed bundle, `docker run` of
the image). `expect` holds one readiness line per process the program starts,
itself included; each must appear in its combined output, in any order. `health`
URLs must answer 2xx. The script exits 0 when everything was seen, 1 when the
program exited first or a line never came (naming each one missing and showing
the last output), 4 on the time limit, 2 for a declaration it cannot use: no
file, invalid, or a `start` with nothing in `expect` and `health`. An empty
`start` means "this product ships no packaged program" and exits 0 with a
notice; it is the template's default until the product fills it. The whole
process tree is stopped at the end on every path; only processes the script
started are touched. `package.yml` runs it after the build.

### DL8 — `delivery_log.py`, the delivery log in the release notes

```
delivery_log.py publish --pr N [--remote origin] [--repo OWNER/NAME] [--dry-run]
delivery_log.py live    --pr N [--at ISO] [--remote origin] [--repo OWNER/NAME] [--dry-run]
```

`cleanup.py --pr N` collects, before it deletes anything, one row per change of
the train (the ready pull request's branch and every branch joined into it):
finished (the branch's last commit), joined (the merge commit that brought it into
the integration branch), CI start (the earliest start among the runs on the ready pull
request's branch created at or after the pull request was created, from
`gh run list --branch` and `gh pr view --json createdAt`, so an earlier fix-forward
round counts; the final head's runs when that listing fails), CI end (the latest
end of the runs on the final head, from `gh run list --commit`), queued (the
longest created-to-started wait among the runs of CI start) and merged (`mergedAt`).
Every time in the table is UTC and its headers say so.
After the deletions it writes the table into the train's GitHub release notes
(`--no-delivery-log` skips it; `--dry-run` writes nothing). The deploy job calls
`delivery_log.py live --pr N` after its smoke test; it sets `live` on every row
that has none. Time to live is live minus finished and is split into testing (CI
end minus CI start), queueing, and waiting (the rest: before CI, in the train,
the merge and the deploy). The release is the one whose tag points at the merge
commit; without one, `train-<merge date>-<N>` is created for the merge commit.
The table sits between `<!-- delivery-log:start -->` and `<!-- delivery-log:end -->`
with its rows as JSON in a comment, so a second call replaces the table, keeps
every value already recorded, and leaves the rest of the notes alone. Nothing is
committed to the default branch. A missing timestamp is `unknown` and so is every
figure that needs it; offline, without `gh`, without permission, or on any error
the script warns on stderr and exits 0, because the log must never fail a cleanup
or a deploy.

### Guards for agent sessions (STACKSPEC 13.8)

`suites.json` declares the suites; `run_suite.py NAME [CASE ...]`, `--measure NAME`,
`--list` and `--record-ci NAME --seconds S` run and time them. Local times go to
`.delivery/suite-times.json` (git-ignored with `.delivery/`), CI times apart from them;
`ci_watch.py` stores the step named by a suite's `ci_step` when it prints its summary.
Heavy: last full local run over 180 s, no local measurement, or `"measure": false`.
`session_guard.py` is the Claude Code `PreToolUse` hook for `Bash`
(`python scripts/delivery/session_guard.py`; `--check "CMD"` tests a command by hand).
It exits 2 with the reason on stderr to refuse: a full local run of a heavy suite or of
a suite that passed on the same tree (local or CI record), `--measure` under 30 days
after a measurement, `gh pr create` without `--draft` and `gh pr ready` from a branch
not matching `release_branches` of `tools/change-notes.json` (default `*-integration`).
Named-case runs are always allowed. `join.py` works without `gate.json`: it says the gate
is not configured and writes `"gate": "not configured"` to `join-result.json`.
