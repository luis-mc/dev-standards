# Changelog

## 0.3.0

- DL-31: measured durations, savings, costs, lists of durations and bullets that already carry a clock time are not ETAs.
- DL-03: green only when every required CI workflow (`watcher.ci_workflows`) completed with success on the PR head; `ci_watch.py` passing no longer greens a train; green is revoked when a required run runs again.
- DL-76 (new): one CI per release; `pr_proven_jobs` jobs must not re-run on the default branch on the tree the release PR proved.

## 0.2.0

- Config schema and validator, `delivery_doctor.py`, watcher and enforcement settings.
