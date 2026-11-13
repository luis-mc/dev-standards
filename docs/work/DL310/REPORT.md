# DL310 report: shared Windows machine runner

Branch `DL310-windows-machine-runner`. Code head before this report: `876264344a7e4ed9b8312844ddcf0b2ecb72fba2` (the report commit follows it).

## What was built

| Item | Where |
|---|---|
| 1 Account `ci-<slug>` (max 20, hash on clash), group, rights, random password made inside PowerShell and passed only to `config.cmd` | `delivery_runner_pool.py`: `windows_account`, `ps_account`, `ps_register` |
| 2 Rights: runner folder, machine folder, hooks (RX), `C:/ci-tools` | `ps_machine`, `ps_files` |
| 3 Per-runner `.env` (both hooks, `CI_TOOLS_DIR`, `RUSTUP_HOME`, `CARGO_HOME`), rewritten every run | `windows_env_text`, `ps_register` |
| 4 Runner download through `ci_tool` with a pin | `tools.json` pin `actions-runner` / `windows_x64`; `runner_pin_problem` |
| 5 Everything in one run (elevated: steps `win-machine`, `win-account`, `win-files`, `winsvc`; not elevated: `win-script` writes `<machine_dir>/setup/windows-runner-<slug>.ps1` and one line is printed) | `plan`, `Executor.do_windows_*`, `windows_runner_script`, `delivery_ci_setup.py` (guard, plan text) |
| 6 Replacement of an old Windows runner after the new one is online, with the named delete yes, guard for a running job | `plan` (old_win), `migration_guard`, `run(guard=...)` |
| 7 Skill step | `claude/plugins/delivery/commands/delivery-ci-setup.md` (section 3a, step 4) |
| 8 Doctor per Windows runner | `delivery_doctor.py`: `windows_runner_items` |
| 9 Spec R5.31 to R5.34, test rows, change notes | `docs/features/runner-pool/spec.md`, `docs/features/runner-pool/changes/DL310.md`, `docs/architecture/changes/DL310-windows-machine-runner.md` |
| 10 Tests | `claude/plugins/delivery/tests/test_dl310_windows_runner.py` (42 tests) |

Files touched: delivery_runner_pool.py, delivery_ci_setup.py, delivery_doctor.py, tools.json, delivery-ci-setup.md, the spec, two change notes, one test file, this report.

## Tests run

| Command (from `claude/plugins/delivery/tests`) | Result |
|---|---|
| `python -m unittest test_dl310_windows_runner` | OK, 42 tests |
| `python -m unittest test_runner_pool test_ci_setup test_doctor test_load` | OK |
| `python -m unittest test_dl188_doctor_tools test_dl115_ci_tool test_ds205_zig_pin test_ds199_tool_fetch` | OK |
| `python tools/ci_areas.py --branch-advice` | `heavy: delivery -> gh workflow run spec-lint.yml --ref DL310-windows-machine-runner -f areas=delivery` (not run: it needs the remote) |
| `change_notes.py check --config tools/change-notes.json` | ok |
| `docs_check.py` | one error, W1: the report under `docs/work/` is on this branch. Expected; strip it before the join. |

No Docker, no mutation pass.

## Needs the owner

1. **The runner pin has no real SHA-256.** github.com and its API answered 403 from this sandbox, so the hash of `actions-runner-win-x64-2.338.2.zip` could not be read. `tools.json` holds 64 zeros and a note. The download step and the script step refuse with a plain message until the published hash is put in. Version 2.338.2 is the pool's own pinned version.
2. The skill file is `commands/delivery-ci-setup.md`; there is no `skills/delivery-ci-setup/` folder. I edited the command file.
3. The feature change note was written by `docs_fold.py` to `docs/features/runner-pool/changes/DL310.md` (the AGENTS rule). The plugin note is in `docs/architecture/changes/`, as asked.
4. `win-script` marks a rerun as todo when `.env` cannot be read (a non-admin shell cannot read a locked runner folder), so a non-admin rerun may write the script again. It is safe to run twice.
5. The runner account must be able to run the Python named in the hook wrappers. A Python inside one user's profile folder will not work for `ci-*`; install it for all users.

## Not verified off Windows

- Real account creation, group membership, the three logon rights (`secedit`), and the account's password rotation.
- ACLs from `icacls` (inheritance removal, group rights), and that the runner account can read `machine.json`, write the queue and use `C:/ci-tools`.
- `config.cmd --runasservice --windowslogonaccount`, service start and restart, `config.cmd remove` on a rerun.
- The PowerShell text was read, not run. Tests check its content and that PowerShell is only fed through stdin.
- The real download and SHA-256 check (blocked by item 1).
- `Win32_Service.StartName` in detect (the account of a kept runner).

READY
