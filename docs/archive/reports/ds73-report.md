# DS73 report: machine load limits

Status: done, draft PR #86 open (not ready, not merged). Branch `DS73-load-limits`. No plugin or spec version is bumped; the change note `docs/specs/changes/DS73-load-limits.md` (minor) carries it.

Owner rule (23 Oct 2026): no memory above 85%, no CPU above 60%; run as many jobs as fit inside that. Enforced by luismc-delivery, not by a memory note.

## Design choices
- **Measurement** (`scripts/load.py`, stdlib only): Windows ctypes `GlobalMemoryStatusEx` + `GetSystemTimes` (kernel time includes idle); Linux `/proc/meminfo` (MemTotal - MemAvailable) + `/proc/stat` over ~1 s; macOS `vm_stat` + `sysctl hw.memsize` + `top -l 2`, load-average fallback. Parsers are pure functions with fixtures.
- **Cache**: temp-folder file, TTL 10 s, last 3 samples. CPU decided = mean of the samples within 30 s, so one spike does not decide (memory is the latest sample). An unwritable cache only costs a fresh sample.
- **Limits**: project `.delivery/config.json` `load_limits` over machine file `~/.claude/luismc-delivery-machine.json` over 85/60, per key; invalid values (outside 1..100) fall through to the next layer. Schema updated.
- **On in every project** with the plugin enabled, with or without `.delivery/`: the load check runs in `hook_pre_tool.py` before the "no .delivery/" early return; Stop/SessionStart notices likewise (via `load_guard.with_notice`, which merges the notice into each hook's single JSON output). hooks.json description and README say so.
- **Refusal** = exit 2 + stderr text (numbers, limits, top processes by CPU and memory, names only, what to do). `enforcement.mode: warn` turns it into a `systemMessage`; `checks_off: ["DL-77"]`/`["DL-78"]` switch off per project. Fail open (stderr warning) if measurement fails.
- **Never kills or reprioritises** anything; only holds new work.
- **Installs**: `pnpm|npm|yarn|bun install|add|ci` are HEAVY unless `--offline` (unpacking thousands of files is the crash pattern; an offline install is still extraction, but the owner can add it to light by using `--offline`). Decision documented in README/spec.
- **Runner gate**: on timeout it exits 1 by default (job fails with a clear log, can be re-run) rather than starting the job over the limit; `--on-timeout run` is the alternative. Fails open if unmeasurable. Wrappers `.sh`, `.cmd`, `.ps1` (the `.ps1` is the safer Windows choice; check the runner version accepts the extension).
- **Doctor `runner` check**: ok if no runner folder is found on the machine; FAIL only when a runner folder (`actions-runner*` under home, drive root, /opt, /srv, `DELIVERY_RUNNER_DIRS`, or `runner_dirs` in the machine file) has no hook in its `.env` or the env var points elsewhere. Reports only; changes nothing.
- Limitation: the Stop notice is a `systemMessage` (non-blocking, shown to the user); the model sees the notice at SessionStart (`additionalContext`) and through the refusal text when it tries heavy work.
- `heavy_commands` already existed in the schema/asset config as plain strings (e.g. `pnpm test:full`); entries are now treated as case-insensitive regexes and fall back to substring match when they are not valid regexes.

## The heavy list
Test runners (vitest, jest, pytest, py.test, playwright, mocha, cypress, tox, nox, `python -m pytest|unittest|tox|nox`); package-manager scripts `test`, `e2e`, `check*`, `build*` (also via `run`/`exec`/`dlx`/`npx`), `rtk`-wrapped too; turbo, nx; `tsc -b`; next/vite/webpack/rollup/esbuild/nuxt/astro builds; cargo build|test|check|clippy|bench|run; dotnet build|test|publish|pack; go build|test; mvn compile|package|verify|install|test; gradle; msbuild; xcodebuild; docker build|buildx|compose up|build and docker-compose; ffmpeg; installs without `--offline`; background jobs (`run_in_background`, trailing `&`, nohup, Start-Process) that are not plainly light; local Agent (no remote/cloud isolation); Workflow; `heavy_commands`. Light: git, gh, ls, cat, grep, rg, rtk reads, python one-liners, lint, echo, sed, jq... RemoteTrigger and Agent with isolation remote/cloud are never refused.

## Files
New: `scripts/load.py`, `scripts/load_guard.py`, `scripts/runner_load_gate.py` (+ `.sh`, `.cmd`, `.ps1`), `tests/test_load.py`, `docs/specs/changes/DS73-load-limits.md`.
Changed: `scripts/hook_pre_tool.py`, `hook_stop.py`, `hook_session_start.py`, `hooklib.py` (defaults, `LAST_INPUT`), `delivery_doctor.py`, `hooks/hooks.json` (matcher `Bash|PowerShell|Agent|Workflow|RemoteTrigger|AskUserQuestion|Write`, description), `references/config-schema.json`, `README.md`, `DELIVERYSPEC.md` (DL-77, DL-78, DL-79 rows, config section 6 note, count), `tests/test_doctor.py` (new check name), `tools/test_delivery_hooks.py` (matcher assertion only).

## Tests (affected gate only)
- `python3 -I -m unittest discover` in `claude/plugins/delivery/tests`: 188 tests OK (new `test_load.py`: parsers Linux/macOS/Windows/process lists, cache TTL and smoothing, precedence project>machine>default, heavy/light/cloud table, configured heavy_commands, refusal message, fail-open, notices, hooks end to end with and without `.delivery/`, warn mode, runner gate wait/pass/timeout/run-mode/fail-open/settings/end-to-end, doctor runner check, schema).
- `tools/test_delivery_hooks.py`: 46 passed. `tools/test_rule_tags.py`: passed (spec ids still resolve).
- Spec lint `tools/spec_check.py docs/specs/delivery/DELIVERYSPEC.md`: 5 errors, the same 5 before and after my change (heading-depth style of the existing spec; DELIVERYSPEC is not in the lint's default set).
- `change_notes.py check --config tools/change-notes.json`: ok. `tools/test_change_notes.py` not run (change-note tooling untouched).
- gitleaks: not installed in this environment, not run. No mutation pass, no Docker.
- Not exercised here: the Windows and macOS measurement calls themselves (only their parsers, on fixtures); this runner is Linux. Run `python scripts/load.py` once on the Windows PC to confirm.

## Branch, head, PR
Branch `DS73-load-limits`; PR #86 (draft) https://github.com/luis-mc/dev-standards/pull/86. Head SHA: see the PR (last commit "DS73: report ...").
