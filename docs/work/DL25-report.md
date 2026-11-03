# DL25 report: Windows learnings (CIR10 S9, W1 to W5)

Branch `DL25-windows-learnings`. Draft PR to main.

## What was built (all under `claude/plugins/delivery/templates/shared/`)

| Learning | File | Proof |
|---|---|---|
| W3 Windows-only table and guard | `scripts/delivery/windows_real.py`, `windows-real.example.json` | `tools/test_delivery_windows.py`: 10 broken tables or shards are refused (file gone, marker lost, over cap, over minutes, duplicate, no marker, Windows shard not the set, other command, unlisted file) |
| W5 hold installers until publish | `artifact_prune.py --hold NAME --hold-workflow FILE`; `package-windows.yml` | Prune test: installers kept after a failed, cancelled, running, unreadable or missing newest run; pruned again after success; other names still pruned |
| W5 token retry | `publish_token.py` | 503, 503, 200 gives the token after 1 s and 2 s; gives up after 1, 2, 4 s; a 4xx is not retried |
| W4 rollback item | `smoke_packaged.py`: `"installer": true` needs `"rollback_check"` | Missing check refused (exit 2); check runs after readiness; failing check fails (exit 1) |
| W1/W2 Linux MSI recipe, CI check only | `windows-msi-linux.sh`, `windows-build-tools.example.json`, `windows-msi-check.yml` | See "No Wine" below |
| Safe flaky re-run | `rerun_args.py` | Windows paths become relative with forward slashes; option values kept; outside-root refused; nothing ran + non-zero exit is `crash` |

Docs: `CONTRACT.md` section "DL25", spec R13.20 in `docs/features/delivery/spec.md`, change notes for `features/delivery`, `delivery-speed`, `test-cost` and the plugin (`docs/architecture/changes/DL25-windows-learnings.md`). `docs_check`: 0 errors, 0 warnings.

## No Wine in the sandbox

The sandbox has no Wine. The recipe test runs the real script with stub `wine` and `xvfb-run` on PATH and a sample tool pinned by SHA-256. It builds `app.msi`, checks `MSI_COMPRESSION=mszip`, that a wrong SHA-256 fails, and that `--dry-run` builds nothing. **A real MSI under Wine was not built.** The owner should run `windows-msi-check.yml` once on a project with real authoring.

## Not found: the test-report helper

The brief names a "test-report helper" with a flaky re-run. This repository has none (the tooling rules say a flaky test is quarantined, not retried). I did not edit a helper. I added `rerun_args.py` with the three rules, for the product's helper to import in S10.

## Tests run

- `python3 tools/test_delivery_windows.py`: all passed.
- `docs_check.py`: clean.
- NOT run: the full `test_artifact_prune.py`, `test_smoke_packaged.py` and `test_ci_areas.py`. The session guard refuses a full local run of these heavy suites (no local measurement). Run them in CI: `gh workflow run spec-lint.yml --ref DL25-windows-learnings -f areas=delivery`. The changes to `artifact_prune.py` and `smoke_packaged.py` only add options; default behaviour is unchanged.

## Shared files touched (merge care for the parallel steps)

- `claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md` (appended a section at the end)
- `claude/plugins/delivery/templates/shared/scripts/delivery/artifact_prune.py`, `smoke_packaged.py`
- `claude/plugins/delivery/templates/shared/.github/workflows/artifact-prune.yml` (comment only)
- `docs/features/delivery/spec.md` (R13.20, after R13.9)
- `.github/workflows/spec-lint.yml` (one step after the smoke-packaged step)

## Open points

- `package-windows.yml` has PRODUCT placeholders for the build and publish commands.
- `ci_areas.py` already maps `tools/test_delivery_*.py`, so the new suite needs no edit there.
