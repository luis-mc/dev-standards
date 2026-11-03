# CIR10: proposal for the delivery plugin, from the CI speed work

Branch: `claude/CIR10-delivery-ci-proposal` (from origin/main). Date: 2026-11-03. Written proposal only; no code.

## Status
- Step 1 (reading): done. Sources read: the reference product's branch `claude/CIR1-ci-under-15` (pages 01 to 08), `ci.yml` and the DL16 report on `claude/DL16-ci-wait-fix`, `scripts/ci/cloud-shards.ts` and `cloud-passes.ts`, the pass record on `claude/ci-passes`; here the DL15 report, delivery spec section 13, the plugin README and the DL16 report.
- Step 2 (proposal text): done, `docs/proposals/CIR10-delivery-ci.md` (6 sections as briefed, 8 open questions, 8-step plan, 54 agent hours).
- Step 3 (docs check): `docs_check.py` reports W1 (this report, by design) and G1 (`docs/llms.txt` stale because a new doc exists; generated files are not committed on a task branch, the release regenerates them). Nothing else.
- Step 4: draft PR opened. Nothing marked ready, merged or commented.

## Could not read
- `ci-under-15/09-measured.html` and the CI `decisions.json` (D15 to D19, D28) are not on any branch that this sandbox can fetch. The proposal uses the numbers and decisions given in the task brief (cold run 38.9 min against 27.9 predicted, cloud shards about 12 min, run 41602331288) and says so.
- No CI run was started and nothing was measured here.
