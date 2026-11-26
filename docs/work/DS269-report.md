# DS269 report: affected targets

Built (spec rows DL-125, R1.4, R5.29, R5.82; DL-112 text edited, ID kept):

- `inputs` on each target and `no_target` in the lifecycle template and its schema (docs plugin).
- `affected_targets.py`: `affected`, `lane`, `unmapped`, `scaffold`. Shared paths and unknown paths select every target. A target with no `inputs` is always affected.
- `lifecycle-lanes.yml`: each lane asks `affected_targets.py lane` first. An unaffected lane takes its result from `pass_records.py to-result` and runs no steps. A miss runs the lane. The release check gets `--base`.
- `lifecycle_release_check.py --base|--changed-file`: an unaffected target with no result names the missing pass record.
- Doctor row `affected-targets` (warn only), one session-start line, and `scaffold` plus a guide section for existing projects.

Not built yet: a Full Progress badge fragment for the affected set.

Not done: the shipped ts `ci.yml` is untouched (no job graph, permission or job change). No test run in Docker, no mutation pass.

Unverified: the lane template ran in no real workflow. The project must add the `lifecycle-<lane>` shards to its shard table and write a pass record on main for each lane, or an unaffected lane runs anyway.
