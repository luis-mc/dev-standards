# DL21 report (CIR10 S5: speed probe, `ci.limits`, database per worker)

Status: done, draft PR open.

## What was built

| Part | File | Notes |
|---|---|---|
| Speed probe, `scaled(ms)` | `templates/shared/scripts/delivery/speed_probe.py` | Median of 5 runs of a fixed workload. Scale = median / reference, never below 1. Above 3: exit 2, result state `error`. `calibrate` writes the reference. |
| `scaled(ms)` for JavaScript | `templates/shared/scripts/delivery/scaled.mjs` | Same rules, reads `DELIVERY_SPEED_SCALE`. |
| `ci.limits` | `references/config-schema.json`, `scripts/delivery_config.py` (`ci_limits()`) | Per option: `browser_workers`, `integration_workers`, `memory_gib`. Defaults 2 and 8.5 GiB (measured, CIR10 L8). |
| Database per worker | `templates/shared/scripts/delivery/db_per_worker.py` | Template `<base>_tpl`, copy `<base>_w<K>` per worker. Names are checked. |
| Tests | `tools/test_delivery_speed.py` (11 scenarios, 5 mutants) | |
| Docs | `docs/features/delivery-speed/spec.md` R5.10 to R5.12; CONTRACT.md section; change notes (see below) | |

## Proof (the step's stated proof)

- A probe above 3 refuses: `scale_above_three_refuses`, `cli_refuses_with_error_state` (exit 2, state `error`, not `success`).
- A budget at scale 1 equals the unscaled one: `budget_at_scale_one_equals_unscaled` (same value and type), and the same in `scaled.mjs`.
- A bad or non-positive `DELIVERY_SPEED_SCALE` refuses; it is never read as 1.
- Mutants (limit 30, refusal reported ok, scale below 1, scale 1 changes budget, bad env gives 1) each fail a scenario.

## Run

- `python3 tools/test_delivery_speed.py`: 11/11.
- Plugin unit tests (`unittest discover` in `claude/plugins/delivery/tests`): 360 OK.
- `change_notes.py check`: ok.
- `docs_check.py`: only W1 (this report, expected; briefs never reach `main`).
- `ci_areas.py --branch-advice`: "light: test locally only". Heavy suites not run.

## Decisions and limits

- The reference time is not known: the proof run had no reference runner. The built-in value (50 ms) is a placeholder. The project runs `speed_probe.py calibrate` once on the machine its budgets were set on. Until then the output says "built-in reference".
- The memory guard ("a shard whose peak is above its limit fails") is S3's work in `cloud_shard.py`. S5 supplies only `ci.limits` and `ci_limits()`.
- Wiring the probe into a workflow job ("budgets run alone") belongs to S2 (templates). `--export-env` prints the line for `$GITHUB_ENV`.
- The naming rule `*.budget.test.*` is stated in CONTRACT.md only; no guard test yet (project-owned files).
- `db_per_worker.py` was proven with a fake `psql` runner, not a real Postgres.
- The doctor does not yet check `ci.limits`. S6 owns the doctor.

## Shared files (other steps may also touch these; expect merge conflicts here)

- `claude/plugins/delivery/references/config-schema.json` (inside `ci`, new `limits` key before `shard_table`; S6/S7/S8 add keys nearby)
- `claude/plugins/delivery/scripts/delivery_config.py` (`ci_limits()` added before `ci_cloud`)
- `claude/plugins/delivery/templates/shared/scripts/delivery/CONTRACT.md` (two table rows after the `ci-shards.json` row; a new section at the end)
- `docs/features/delivery-speed/spec.md` (R5.10 to R5.12, one proof row)
- Change notes: `docs/architecture/changes/DL21-speed-probe.md`, `docs/features/delivery-speed/changes/DL21.md`, `docs/features/delivery/changes/DL21.md`
