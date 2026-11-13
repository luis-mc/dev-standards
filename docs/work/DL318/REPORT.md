# DL318 report

## Files
- `claude/plugins/delivery/scripts/delivery_doctor.py`
  - `_windows_services` / `service_rows`: runner services from Win32_Service (Name like `actions.runner.*`; PathName gives the folder, StartName the account).
  - `_folder_locked`: PermissionError on the folder means locked.
  - `windows_runner_items` merges folders and services. A locked runner is found, its account check comes from StartName, and `.env` hooks, `CI_TOOLS_DIR`, `RUSTUP_HOME`, `CARGO_HOME` are warnings "needs an administrator shell".
  - `_check_runner_hook` and `machine_items` never say "no runner found" when a runner service exists.
  - `workflow_items` (DL317 doctor part), run inside the machine check (id `workflows.*`): fail when a literal `runs-on` label set is carried by no online runner (names file and line); warn on a literal self-hosted label instead of `fromJSON(vars.CI_RUNS_ON[_WINDOWS])`; warn when `CI_RUNS_ON_WINDOWS` is unset and the repo has a Windows runner. GitHub-hosted labels (ubuntu-, windows-, macos-) are skipped. Expression `runs-on` values are skipped. Repositories come from the config key `repos` (strings or `{repo, path}`; workflows are read only when `path` is given), else the current repository.
- `claude/plugins/delivery/tests/test_dl318_doctor_locked_runner.py` (8 tests)
- `docs/architecture/changes/DL318-doctor-locked-runner.md` (plugin delivery, minor)

## Tests
- `python -m unittest test_dl318_doctor_locked_runner` (in `claude/plugins/delivery/tests`): 8 tests, OK.
- `python -m unittest test_doctor test_dl184_pool_doctor_agree test_dl188_doctor_tools test_dl199_doctor_layer_exec test_dl212_doctor_same_content test_ds202_rust_doctor`: 69 tests, OK.
- `python3 tools/ci_areas.py --branch-advice`: light, test locally only.
- `docs_check.py`: two errors. G1 (decisions.md stale) exists on `main` too. W1 is this report, which is stripped before the join. No docs file was edited, `spec.md` untouched.

## Spec text
Add to `docs/features/runner-pool/spec.md` after R5.34:

**R5.35** — **The doctor finds a runner it cannot read** (DL318). A Windows runner is found from the service list (`Win32_Service`, name `actions.runner.*`; the path gives the folder, `StartName` the account) as well as from folders. When this account cannot read the folder, the runner is still reported: the account check uses `StartName`, and the `.env` hooks, `CI_TOOLS_DIR`, `RUSTUP_HOME` and `CARGO_HOME` checks are warnings that say "needs an administrator shell". The doctor never says "no runner found" while a runner service exists.

**R5.36** — **The doctor checks `runs-on` labels** (DL317, DL318, D275, D278). For each repository in the config, the doctor reads its workflows and fails when a literal `runs-on` label set is carried by no online runner of the repository (the finding names file and line). It warns when a self-hosted job uses a literal label instead of `fromJSON(vars.CI_RUNS_ON)` or `fromJSON(vars.CI_RUNS_ON_WINDOWS)`, and when `CI_RUNS_ON_WINDOWS` is unset while the repository has a Windows self-hosted runner. Ids: `workflows.labels|generic|windows_var:<repo>`.

Test table: change the row `R5.31 to R5.34` to `R5.31 to R5.36` and append `claude/plugins/delivery/tests/test_dl318_doctor_locked_runner.py` to its files.

## Branch head SHA
b74036127e354927ff7f0dafe9ffdfe810fe754f (code and tests); the report commit follows it.

READY
