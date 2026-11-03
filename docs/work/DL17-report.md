# DL17: CIR10 step S1 (CI option names, any machine, add-a-runner guide)

Status: done, draft PR.

## What changed
1. Merged DL16's template change by cherry-picking its two commits (the ts template writes run times as the last step of `e2e`; its change notes come with it). DL16 was not on `main`.
2. `delivery_config.py`: `CI_OPTION_NUMBER`, `CI_OPTION_TEXT` ("own self-hosted runners on any machines you run"), `option_name()`, `runner_steps(os, labels)` (by-hand steps per OS), `add_runner_advice()`.
3. `delivery_ci.py`: `--option 1|2|3` (config names and old letters a|b|c still work; `4` is refused with "not built yet"); show and set print "Option N (name)"; JSON adds `number`; new `add-runner --os <os> [--labels]` prints the steps and the rule "a job that waits more than 10 min means add a runner with the same label on another machine".
4. `delivery_doctor.py` `ci` check: Option wording; for Option 1 it names the runners found per OS and the by-hand steps for a second machine (a note, not a failure); a missing runner fails with the steps for that OS.
5. `config-schema.json`: option text reworded; an empty `ci.fallback` block (answer 12). Config values unchanged.
6. README, `CONTRACT.md`, feature spec section 13 (table with Options 1 to 4, new R13.10; no ID or version moved).
7. Change notes: `docs/features/delivery/changes/DL17.md`, `docs/architecture/changes/DL17-ci-option-names.md` (names the delivery `plugin.json`).

## Checks run
- `ci_areas.py --branch-advice`: heavy area `delivery`, full run left to CI (`gh workflow run spec-lint.yml --ref DL17-ci-option-names -f areas=delivery`; not run, no Actions here).
- Plugin tests (`claude/plugins/delivery/tests`, includes `test_ci_options`): 366 passed. New cases: option numbers, empty `fallback` block validates, no "this PC", add-runner per OS, doctor names second-machine steps, missing-runner failure names steps.
- `tools/test_delivery_ci.py`: 77 passed.
- `docs_check`: one error, W1 (`docs/work/` files on an agent branch; expected, stripped before the join). Three warnings (M1, two T2).

## Shared files (other CIR10 steps may touch them)
`delivery_config.py`, `delivery_ci.py`, `delivery_doctor.py`, `config-schema.json`, `README.md`, `CONTRACT.md`, `docs/features/delivery/spec.md` (section 13 only; S11 rewrites it).

## Notes
- The other "this PC" hits in `docs/features/test-cost/spec.md` are a finished study, not runner text; left alone.
- The stored prompt says no Co-Authored-By or AI attribution; that wins over the session's default footer.
