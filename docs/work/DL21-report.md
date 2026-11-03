# DL21 report (CIR10 S5: speed probe, `ci.limits`, database per worker)

Status: started. Updated after each step.

## Plan

1. `speed_probe.py`: fixed workload, median of 5 runs, `scaled(ms)`, refuse above 3 (owner answer 8).
2. `ci.limits` in the config schema and `delivery_config.ci_limits()`.
3. `db_per_worker.py`: database per test worker, made from a template (Postgres).
4. Tests, CONTRACT.md section, change notes, docs check.

## Shared files (other steps may also touch them)

To be filled in.
