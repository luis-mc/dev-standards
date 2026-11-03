# DL26 report (CIR10 S11: CI docs)

Status: done, draft PR open. Docs check clean except W1 (this report; the join strips it).

## Plan

1. Rewrite spec section 13 (`docs/features/delivery/spec.md`) for four options and the owner answers (D30 to D41).
2. Update the feature pages that mention CI.
3. Add the guide `docs/guides/set-up-ci.md`.
4. Change notes.
5. Read the branches of DL17 to DL25 and align names. List mismatches below.
6. `docs_check`, `ci_areas.py --branch-advice`, draft PR.

## Done

- Spec section 13 rewritten (R13.1 to R13.9 kept, R13.10 to R13.19 added), `docs/features/delivery/spec.md`.
- Guide `docs/guides/set-up-ci.md`.
- Change note `docs/features/delivery/changes/DL26.md`. No plugin file changed, so no plugin note.
- `docs_index.py build` rerun for the generated index.
- `ci_areas.py --branch-advice`: light, docs only.

## Mismatches with the code branches

At the time of writing the other branches hold no code: DL17 only carries DL16's template change, DL19, DL20 and DL21 hold reports, DL18 and DL22 to DL25 are not pushed. Nothing could be compared. These names are taken from the contract and must be checked once the code lands:

1. Option values: the code today takes `--option a|b|c` (`delivery_ci.py`); the docs say `--option <name>` with `self-hosted`, `github-hosted`, `cloud`.
2. Option 4 is documented as `self-hosted` plus a `ci.fallback` block (contract answer 12). The flags `--fallback cloud --after-min 10` come from the contract.
3. Config keys named in the docs: `ci.fallback` (`after_min`, `after_min_if_offline`, `max_shards_per_day`, `max_minutes_per_month`, `only_for`), `ci.limits` (`browser_workers`, `integration_workers`, `memory_gib`), `ci.cloud.shard_timeout_min`.
4. Command `/delivery-ci-setup`; claim branch `ci-claim/<sha>/<shard>/<attempt>`; Windows table name `windows-real`; `cloud_status.py post` refusing without a claim.
5. Doctor wording for a `windows` shard with no option that can run Windows.

Rerun this step after S1 to S9 merge.
