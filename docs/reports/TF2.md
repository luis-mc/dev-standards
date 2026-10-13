# TF2 report: luismc-transcript-folds plugin

Branch `TF2-transcript-folds-plugin` (from `origin/DS64-integration`). Contract: `docs/plans/transcript-folds.md`.

## Plan

1. Check the API types, confirm `claude plugin validate` accepts a module importing `./fold/*.ts`.
2. Pure logic in `hooks/fold/*.ts` with node:test suites.
3. Glue in `hooks/transcript_folds.tsx`, manifest, state contract.
4. CI area `transcript-folds` (`tools/ci_areas.py`, `tools/test_ci_areas.py`, `spec-lint.yml`).
5. Validate, change-notes check, final report.

## Status

- [ ] 1 API check and import check
- [ ] 2 fold logic and tests
- [ ] 3 glue, manifest, state
- [ ] 4 CI area
- [ ] 5 validate and report
