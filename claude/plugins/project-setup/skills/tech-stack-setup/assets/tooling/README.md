# Tooling assets

Working implementations of `STACKSPEC §13.1`'s twelve required gates, one set
per track, plus what is genuinely language-agnostic.

Copy in Phase 7 step 1 — before any module exists, so the first commit is
already gated.

```
tooling/
├── shared/     copied for every product, whatever the track
│   ├── .gitleaks.toml
│   ├── .githooks/pre-commit
│   ├── .github/workflows/  artifact pruning, train cleanup
│   └── scripts/delivery/   branch gate, CI watch and skip, reach check, cleanup
├── ts/         TypeScript / Node
├── go/         Go
├── rust/       Rust
└── dotnet/     .NET
```

`shared/` is separate because gitleaks does not care what language the secret
was committed in. Duplicating it four times would mean four places to add an
allowlist entry and three of them going stale.

## The twelve gates, per track

| `§13.1` gate | ts | go | rust | dotnet |
|---|---|---|---|---|
| 1. Frozen install | `pnpm install --frozen-lockfile` | `go mod download` + `verify` + tidy-diff | `cargo fetch --locked` | `dotnet restore --locked-mode` |
| 2. Codegen drift | `turbo codegen` + `git diff` | `go generate` + `git diff` | codegen bin + `git diff` | codegen project + `git diff` |
| 3. Lint | ESLint | golangci-lint | clippy | Roslyn analyzers |
| 4. Format | Prettier | `gofmt -l` | `cargo fmt --check` | `dotnet format --verify-no-changes` |
| 5. Typecheck | `tsc` | `go build` | `cargo check` | `dotnet build` |
| 6. Unit tests | Vitest `unit` | `go test -short` | `cargo test --lib` | `Category=Unit` |
| 7. Integration | Vitest `integration` | `TestIntegration` | `--test integration` | `Category=Integration` |
| 8. Contract | Vitest `contract` | `TestContract` | `--test contract` | `Category=Contract` |
| 9. Route coverage | Vitest `authz` | `TestRouteCoverage` | `--test route_coverage` | `Category=RouteCoverage` |
| 10. Dependency scan | `pnpm audit --prod` | govulncheck | `cargo deny check advisories` | `dotnet list package --vulnerable` |
| 11. Secret scan | gitleaks step in `verify`, `fetch-depth: 0` | same | same | same |
| 12. Boundaries | dependency-cruiser | depguard in golangci-lint | `cargo deny check bans` | NetArchTest |

**The tool names are this generator's choice, not the spec's.** `§13.1` requires
the gates to run and fail the build; it names nothing. `§20` makes naming a
vendor in the spec a defect. Record the tools in `docs/specs/stack-profile.md`
section 2, and treat a product satisfying the same gates with different tools as
conforming.

## Gates that fail loudly by construction

Four places exist specifically so an absent check cannot masquerade as a passing
one. Preserve these when adapting any track:

- **`fetch-depth: 0` on the `verify` job's checkout.** The secret scan is a step
  there, and gitleaks scans history. At the
  default clone depth it silently examines one commit and reports clean.
- **Codegen drift regenerates, then diffs.** Checking only that generated files
  exist would let a stale committed artifact pass.
- **A suite finding zero tests fails** (`§11.3`). The TS config sets
  `passWithNoTests: false`; the other tracks fail on an empty filter by default,
  but verify it after changing any test filter.
- **The .NET dependency scan greps its own output.** `dotnet list package
  --vulnerable` exits 0 even when it finds vulnerabilities, so a bare invocation
  is a gate that can never fail — worse than no gate, because it reports success.

## Required status checks

GitHub names a check after the job's `name:`, not its job id, so require these
exact strings — requiring `verify` or `integration` waits on checks that never
report, and every pull request hangs.

| Track | Required checks |
|---|---|
| ts | `lint, types, boundaries, unit + contract tests` · `integration tests (ephemeral Postgres)` · `web E2E (§11.2)` |
| go | `lint, vet, boundaries, unit + contract tests` · `integration tests (ephemeral database)` |
| rust | `clippy, fmt, build, unit + contract tests` · `integration tests (ephemeral database)` |
| dotnet | `analyzers, format, build, unit + contract tests` · `integration tests (ephemeral database)` |

Renaming a job's `name:` renames its check; update branch protection in the same
change.

- **E2E gates.** The TS track's `web E2E (§11.2)` is required: `§11.2` makes
  end-to-end tests of the critical web journeys fail a ready pull request. A
  flaky spec is quarantined, not retried (see below).
- **`decide: skip a tree already tested` is not required.** It exists to skip
  work and gates nothing. Requiring it would also hang pull requests, where it
  never runs.
- **Drafts report as skipped.** Draft pull requests skip every job; drafts cannot
  merge, and marking the PR ready (`ready_for_review`) re-runs CI.
- **No `secret scan` check any more.** The secret scan is a step in the `verify`
  job. If `secret scan` is still a required check, remove it or the PR will wait
  on a check that never reports.

## CI cost

GitHub bills each job rounded up to a whole minute, so the templates cut minutes
without dropping a `§13.1` gate (`§13.1`'s CI-cost clause):

- **Fewer jobs.** The secret scan is a step in `verify`, run first so a leak
  fails fast. It installs the gitleaks release pinned in
  `scripts/delivery/tools.json` (checksum verified) rather than an unpinned
  action, so CI runs the scanner the agent setup script installed (`§13.5`).
- **Caching.** Go and Rust use their setup/cache actions; .NET caches NuGet on
  `packages.lock.json`; TS caches turbo's `.turbo` results (sound because `§2.2`
  requires every env var a task reads to be declared in `turbo.jsonc`).
- **Cancel superseded runs, only on pull requests.** Runs on `main` always finish.
- **Skip drafts.** `types` includes `ready_for_review`; every job is guarded by a
  draft check.
- **Skip a tree already tested.** See the next section.

## The `decide` job

A push to `main` must not repeat a suite that already passed (`§13.1`). Each
`ci.yml` starts with `decide: skip a tree already tested`, which runs only on
`push`, runs `scripts/delivery/ci_skip_check.py`, and outputs `skip`. The script
finds the pull request merged as this commit and its head, and a successful
`pull_request` run of this same workflow file for that head. If the two commits
have the same git **tree**, `skip=true` and every other job is skipped; a merge
that changed anything, no pull request, a failed or all-skipped run, or any error
at all gives `skip=false` and the suite runs. It fails open, never closed.

Every other job has `needs: decide` and
`if: ${{ !cancelled() && needs.decide.outputs.skip != 'true' && (github.event_name != 'pull_request' || !github.event.pull_request.draft) }}`.
`!cancelled()` is what lets pull requests run: there `decide` is skipped, and a
skipped dependency would otherwise skip its dependents too. `decide` needs
`actions: read` and `pull-requests: read` besides `contents: read`, and a full
checkout so the pull-request head commit can be fetched.

## E2E and the quarantine list (TS)

`web E2E (§11.2)` runs on every ready pull request with no `continue-on-error`.
Specs listed in `e2e/quarantine.json` are the exception:

```json
[{"spec": "tests/checkout.spec.ts", "owner": "name", "since": "2026-10-10", "reason": "flaky on slow runners"}]
```

`playwright.config.ts` reads the list. By default it ignores the quarantined
specs, so everything else gates; with `E2E_QUARANTINE=only` it runs only them, in
a separate `continue-on-error` step, so they still run and report but cannot fail
the build. Retries stay at 0: `§11.3` says a flaky spec is quarantined and fixed,
never re-run until green. An entry without an owner, a date and a reason is
rejected by the config.

## Delivery scripts used by CI and agents

Copied to `scripts/delivery/` (see `shared/scripts/delivery/CONTRACT.md`):

- `ci_skip_check.py`: the `decide` job's script, above.
- `ci_watch.py SHA`: waits for the workflow runs of one commit and exits 0, 1 (it
  prints the failed jobs), or 4 (timeout). It reads workflow runs, never a pull
  request's check list, which can be read before the new run is listed
  (`§13.6`). Use it after pushing the ready pull request's head. It warns once for a
  job queued over 10 minutes with no online runner for its labels (warnings only).
- `train_freeze.py`: called by the `pre-push` hook. Refuses a push to a branch whose
  ready (non-draft) pull request has CI running; allows it when CI finished, the pull
  request closed, or GitHub is unreachable (a warning). `DELIVERY_FREEZE_OVERRIDE=1`
  pushes anyway and the running CI restarts. A late branch rides the next train.
- `runner_health.py`: warns when no online runner carries a label the workflows need
  (hosted labels count as available); used by `join.py` and `ci_watch.py`.
- `reach_check.py URL...`: GETs each URL from where it runs and prints status or
  error. Run it in an agent sandbox before relying on a registry, API or preview
  host being reachable.
- `artifact_prune.py`: keeps only the newest build artifact of each name and
  deletes the rest (`§13.1`). `shared/.github/workflows/artifact-prune.yml` runs
  it after every `CI` run and daily; add any other workflow that uploads an
  artifact (an installer, a bundle) to its `workflows:` list, and give each kind
  a stable name.
- `cleanup.py`: removes a merged train's branches, gate-result refs, local
  branches and worktrees, and keeps anything open, unmerged or dirty (`§13.6`).
  `shared/.github/workflows/train-cleanup.yml` does the remote part when the
  ready pull request merges; `join.py` does the local part before each join.
- `delivery_log.py`: `cleanup.py --pr N` calls it before deleting a branch; it appends
  a table of each change's time to live (waiting, testing, queueing) to the train's
  release notes (`§13.6`). The deploy job runs `delivery_log.py live --pr N` after
  its smoke test. Offline or without permission it warns and the cleanup goes on.
- `smoke_packaged.py`: starts the packaged program declared in
  `scripts/delivery/smoke.json` and waits for a readiness line from it and from
  every worker it starts (`§13.7`). Each track's `package.yml` runs it after the
  build; the workflow runs only when a path that feeds the artifact changes, never
  for docs-only merges, and can be started by hand.

## Adapting a track

Two things to change before first use:

1. **Module and project paths.** `go/.golangci.yml` has `<module>` placeholders;
   the .NET and Rust workflows assume `src/Db`, `tools/Codegen` and a `codegen`
   binary.
2. **The database service image**, if the engine is not Postgres. `§5.5` requires
   an ephemeral real instance of *whatever engine was chosen* — not a substitute,
   and not an in-memory stand-in for a different engine.

## What is not here

**E2E specs and other tracks' E2E.** The TS track gates on Playwright (above) but
ships no specs: the journeys are the product's. The other tracks have no web E2E
job; where mobile journeys are not automated, `§11.2` requires the release
checklist to name the manual journeys verified before each release.

**Mobile CI.** `§13.3` needs macOS runners for iOS and its own path filters.
Generated per-product, because signing material and store configuration are
product-specific.
