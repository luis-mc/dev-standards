# DL20 report: CIR10 S4, inputs key and pass records

Task DL20, branch `DL20-pass-records`, 3 Nov 2026. Contract: CIR10 proposal sections 2.1 (L4, L5) and 8.

## What was built

- `pass_records.py` (new, shared scripts): the inputs key, the records branch, lookup, write, cleanup, a CLI (`key`, `check`, `write`, `cleanup`).
- `cloud_shard.py`: new flags `--records --base --branch --ready --all --records-branch`. Without `--records` nothing changes.
- `cleanup.py`: drops a deleted branch's records; protects the records branch from deletion.
- `ci-shards.example.json`, `CONTRACT.md`, spec requirements R13.10 and R13.11, two change notes.
- `tools/test_delivery_records.py`: 23 tests on a fake (bare local) remote.

## How it works

- **Key.** SHA-256 of shard id, OS, expanded commands and the git blob ids under the shard's `inputs` and the table's `root_files`. No `inputs`, a path that matches nothing, or uncommitted changes under those paths give no key; the shard then always runs.
- **Records.** Orphan branch `ci-pass-records`, file `<branch>/<shard>/<key>.json`. A lost push race is fetched and retried.
- **Skip.** Only a `success` record with the same key and shard. A failed record never skips. `error` is never recorded. `--all` ignores records.
- **Read rule (L5).** A ready PR to the base (`--ready`) reads only the base's records. Other runs read their own and the base's. Writes go only under the run's own branch.
- **Cleanup.** Records of branches gone from the remote are removed; the newest 20 per branch and shard stay; nothing is removed if the branch list cannot be read.

## Proof

- `python3 tools/test_delivery_records.py`: 23 tests OK.
  - A second run of one shard is skipped in under 5 s with the command not run (measured in the test: well under 1 s; the 336 s case needs a real product).
  - A changed input file, new file, root file or command changes the key; an unrelated file does not.
  - A failed record never skips (two runs, two executions). `--all` runs. An unreachable remote runs.
  - A ready PR ignores its own branch's record and uses the base's.
  - Two writers both land; cleanup drops dead branches, keeps the newest N, never the default branch.
- Three hand mutants (success check removed, ready rule removed, files dropped from the key) each fail the suite.
- Also run: `test_delivery_cloud.ShardTests` (6 OK), `test_delivery_cleanup.py --no-mutants -k remote` (4 checks OK), `change_notes.py check` OK.
- `docs_check`: the only error is W1 (this report; it is stripped before the join). Two T2 warnings on the specs I edited.
- Not run: full `delivery-cloud` and cleanup suites with mutants (the session guard refuses a full local run; CI runs them), `ci_areas.py --branch-advice` said heavy: `gh workflow run spec-lint.yml --ref DL20-pass-records -f areas=...`. I did not start that run.

## Interpretation I made

"Records read only from the base branch's history" is read as the L5 rule above (a ready PR to the base reads the base's records only). The records hold no commit ancestry check; a record is trusted by its key.

## Gaps

- `cleanup.py`'s new hook has no scenario in `test_delivery_cleanup.py` (its harness is large); `drop_branch` itself is tested.
- The wiring into a project's `ci.yml` (calling `pass_records.py check|write` per job) is not done; that is the template steps S2 and S10.
- A failure record can overwrite a success record for the same key (a forced `--all` rerun that fails). The next pass restores it.

## Shared files touched (other steps may also edit)

- `cloud_shard.py` (S3 also edits it: sizing and memory limit). My edits are the `records` parameter of `run_shard`, the flags and a block in `main`.
- `cleanup.py`, `CONTRACT.md`, `ci-shards.example.json`, `docs/features/delivery/spec.md` (S11 rewrites section 13; my R13.10 and R13.11 are appended after R13.9).
- `tools/ci_areas.py` is not touched; `tools/test_delivery_records.py` is not yet mapped to a suite there.
