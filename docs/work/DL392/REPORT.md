# DL392 report

All five fixes done on branch `DL392-tooling-papercuts`.

| Fix | Change | Files | Test |
|---|---|---|---|
| (a) | `agent-check --note TEXT` stored on the agent row | `delivery_ledger.py` | `test_dl392_agent_note_closed.py` |
| (b) | `agent-done` and `agent-check` on a closed row print "already closed", exit 0; unknown still exits 1; stale flag already skips closed rows (tested) | `delivery_ledger.py`, `test_ledger.py` (old expectation updated) | same file |
| (c) | `--phase` accepts numbered repeats (`ci2`, `fix2`), stored and drawn in time order, bar uses the base colour, label "PR CI 2" | `project_artifacts.py`, `render_artifacts.py` | `test_dl392_numbered_phases.py` |
| (d) | `decisions-migrate --feature X [--fill-from-title] [--dry-run]`; options of decisions asked before 2026-11-14 with an empty summary no longer fail validation; `task-add` warns and names the command; newer decisions still refused | `project_artifacts.py`, `render_artifacts.py` | `test_dl392_decisions_migrate.py` |
| (e) | pre-push hook skips node checks with one note when node_modules is missing and the push changes no JS file; JS or unknown range still blocks | `claude/plugins/delivery/templates/shared/.githooks/pre-push` | `test_dl392_prepush_nonode.py` |

The 2026-11-14 cutoff is the date of the commit that added the summary check (RELEASE-143). Change it in `LEGACY_SUMMARY_BEFORE` if the owner wants another date.

Docs: R5.36 and new R5.36b in `docs/features/delivery/spec.md`; R5.40 and R5.14 text in `artifactspec.md`; two rows in `docs/features/artifacts/spec.md`. Change notes: `docs/architecture/changes/DL392-*.md` (both plugins, minor), feature notes via `docs_fold.py note` for delivery and artifacts.

## Tests (all OK)
- `cd claude/plugins/delivery/tests && python3 -m unittest test_dl392_agent_note_closed test_dl392_prepush_nonode test_ledger test_dl127_ci_watch_ledger test_dl151_stale_agents test_dl303_liveness_owns test_dl154_prepush_ignore test_dl172_setup_bounds test_dl308_template_adopt`
- `cd claude/plugins/docs/tests && python3 -m unittest test_dl392_numbered_phases test_dl392_decisions_migrate test_dl228_record_messages test_dl305_fix_phase test_ar74_phase_dates test_dl359_phase_gap_midnight`
- `change_notes.py check --config tools/change-notes.json`: ok.

## docs_check
`python3 claude/plugins/docs/scripts/docs_check.py`: one error, W1, the work file `docs/work/DL392/REPORT.md` itself. That is expected on an agent branch; strip it before the join (`docs_work.py strip`). No other findings. The T2 date check was skipped (shallow clone).

Branch head SHA: see the final commit on origin/DL392-tooling-papercuts (`git rev-parse HEAD`).

READY
