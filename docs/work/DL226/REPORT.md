# DL226 report

## Base check
Branch made from origin/main. agent_ci.py and ci_watch.py exist.

## What changed
- agent_ci.py: default report list is now `docs/work/{task}/REPORT.md`, then `docs/work/reports/{task}.md`, then the two older paths. The skip line names the first two paths. Help text updated.
- ci_watch.py, root cause: after the named runs finished, the other-workflow check counted every run without an OK conclusion as bad. A run still in progress has no conclusion, so it counted as failed and the watch decided early. Now only completed runs can be bad, and the watch decides only when no run is pending. `print_failed_jobs` skips jobs that are not completed, so an in-progress job is never labelled FAILED.
- Spec: R5.39 (ci_watch waits for all runs) and R13.77 (agent_ci report path) in docs/features/delivery/spec.md. Feature note docs/features/delivery/changes/DL226.md. Change note docs/architecture/changes/DL226-agent-ci-path-ci-watch.md (plugin patch).
- tools/test_ci_speedups.py: two assertions pinned the old skip message; updated.
- New tests: claude/plugins/delivery/tests/test_dl226_agent_ci_path_ci_watch.py (8 tests; 5 fail without the fix).

## Tests
- python3 claude/plugins/delivery/tests/test_dl226_agent_ci_path_ci_watch.py: 8 ok.
- Every delivery test that mentions agent_ci or ci_watch (14 files): ok.
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed.
- spec-lint.yml areas=delivery, final run 43065598384: all delivery jobs success (CI scripts and workflow templates, setup preflight, branch gate, ledger/watcher, artifact pruning, runner plan, smoke test, change notes, area mapping, train cleanup, rollup). which-areas success. docs check failure: only G1 (stale generated decisions.md) and W1 (docs/work report on branch), both expected.
- Earlier run 43064412021 failed on tools/test_ci_speedups.py skip-message assertions; fixed, then run 43065026282 failed on the second one; fixed in b9407a8.
- docs_check.py locally: only G1 and W1.

## Follow-ups
- claude/plugins/delivery/references/agent-brief-template.md line 27 still says the report is `docs/work/reports/<task-id>.md`. Not mine to edit; it should say `docs/work/<task-id>/REPORT.md`.
- DOCSPEC R10.1 example path (docs/docs plugin) uses docs/work/reports/; unchanged.

## Branch head
SHA: see the pushed branch head after the commit that carries this report.

READY
