# DOC2 report: luismc-docs plugin, DOCSPEC, two luismc-delivery fixes

Branch `claude/DOC2-luismc-docs` (dev-standards). One draft PR, not merged.

Status: READY

## What was built

### Plugin `luismc-docs` (`claude/plugins/docs/`, generic, stdlib-only Python)
- `references/docspec.md`: DOCSPEC 1.0.0, 71 numbered requirements, a decision record D1-D15. `tools/spec_check.py` is clean (0 errors, 0 warnings). Registered in `tools/change-notes.json`.
- `scripts/docs_setup.py`: `init`, `migrate` (dry run by default; prints the plan, marks guesses; `--apply` uses `git mv`, rewrites relative links in docs, root README/AGENTS/CLAUDE, adds front matter stubs, creates the layout; never deletes; collisions are kept and exit 2; second run is a no-op), `move-record` (artifacts record to `docs/project`, sets `record_dir` in `.claude/artifacts.json`).
- `scripts/docs_index.py`: `build` writes `docs/index.html` (offline, search, feature index by app and topic, gaps), `docs/_site/` (one page per doc, Mermaid, vendored copy if present), `features/index.md`, `architecture/decisions.md`, `docs-map.json`, `llms.txt`; `check` fails stale generated files; `fetch-mermaid`.
- `scripts/docs_fold.py`: `note`, `pending`, `fold` (one version per release, highest note wins, one row per doc at the top of `## Versions`, notes consumed).
- `scripts/docs_check.py`: L1 F1 K1 K2 S1 S2 V1 G1 G2 M1 W1 U1 (errors) and T1 T2 D1 (warnings), `map`, `drift`, `--strict`, `--json`.
- `scripts/docs_work.py`: `guard`, `summaries`, `strip` (D9).
- `scripts/hook_stop.py`, `scripts/hook_session_start.py`, `hooks/hooks.json` (warn only, opt-in by `docs/docs.json`, fail open).
- Skills: `docs-setup`, `feature-spec-new`, `docs-index`, `docs-check`, `docs-note` (model profiles added to `model-profiles.json`).
- Templates: docs README, AGENTS.md, five overview pages, feature spec (why/what/how, FR/NFR, visuals, both audiences), MADR, change note.
- Marketplace entry, root README section, `tools/ci_areas.py` area `docs` + `spec-lint.yml` job `docs` + nightly areas list (`tools/test_ci_areas.py` updated).

### luismc-delivery fixes (from the two owner prompts)
- **Runner re-run filter** (`runner_plan.py`, the copy `tech-stack-setup` ships): re-runs only when head = branch's current head, newest run of its workflow for that head, nothing of the branch queued/running, conclusion failure/timed_out/startup_failure (`cancelled` only with `runner_plan.rerun_cancelled`, default false). `runner.rerun` and `runner.rerun_skipped` events and `.delivery/report.log` lines. Side finding fixed: in a project repo the ledger module was never found (it only looked in the project tree and next to the script), so every runner event was dropped silently; it now also looks in `~/.claude/plugins/cache/*/luismc-delivery/<newest>/scripts/` and the marketplace checkout and says once on stderr when it finds none. DELIVERYSPEC text and `config-schema.json` updated.
- **Hook misses** (`hooklib.py`, `hook_post_tool.py`, `delivery_watch.py`, `delivery_ledger.py`): tokenizer `hooklib.split_shell` (quotes, backslashes, heredocs, redirections; cd tracking kept) used by both split functions; backgrounded push/PR recorded as one `bash.backgrounded` event, not as done; the watcher adopts the open PR of planned/joining/joined/pushed/ci/red trains (cause of PR 847: only pushed/ci trains were adopted and the train was still `planned`) and re-points a planned/joined train whose PR head moved; `plan` adopts an open PR at once; the post-tool lock is retried once with the longer wait; any failure appends a `post-tool` line to `.delivery/blocks.log`; `runner.guard_started` is logged once per watcher. Cases (b) and (d) are kept as regression tests (they passed before the fix, as the prompt said).
- Version bumps: not edited by hand (repo rule). Change notes: `DOC2-luismc-docs` (minor, 0.0.0 -> 0.1.0), `DOC2-delivery-hook-misses` (patch, 0.10.2 -> 0.10.3), `DOC2-runner-rerun-filter` and `DOC2-model-profiles-docs-skills` (project-setup patch).

## Decision -> requirement map (DOCSPEC 1.0.0)
| D | Chosen | Requirements | Built in |
|---|---|---|---|
| D1 | B by reader question, Diataxis as a page type | R2.1-R2.3, R4.2 | docs_setup layout, docs_check F1 |
| D2 | A plugin script renders a static site, no server | R6.1-R6.7, R2.6 | docs_index |
| D3 | B five fixed overview pages | R3.1-R3.3, R2.1 | templates/overview, docs_check L1 |
| D4 | B one folder per feature, front matter drives the index | R4.1-R4.10, R6.3, R6.4 | feature-spec template, docs_index |
| D5 | B change notes folded at release, one version per release | R7.1-R7.6 | docs_fold, docs_check V1 |
| D6 | C map plus executable checks | R8.1-R8.4, R5.3 | docs_check (K1 K2 S1 S2 V1 G1 G2 M1 W1 U1 T1 T2 D1) |
| D7 | A agent writes, hooks remind, gate enforces | R8.5-R8.8 | hook_stop, hook_session_start, docs_check M1 |
| D8 | B decisions.json per feature, MADR for cross-cutting | R11.1 | templates/madr.md, generated decisions.md |
| D9 | B branch-only, never on the default branch | R10.1-R10.5, R9.4 | docs_work (guard, strip, summaries) |
| D10 | A design system holds rules, screens in feature specs | R11.2, R11.3, R5.4 | docs_check U1 |
| D11 | A Mermaid in Markdown, images as files | R11.4, R4.8, R6.5 | docs_index, docs_check D1/K2 |
| D12 | A new plugin luismc-docs with DOCSPEC | R12.1-R12.4 | the plugin |
| D13 | A one scripted move, then content as touched | R9.1-R9.3, R9.5, R9.7, R9.8 | docs_setup migrate/init |
| D14 | `docs/project/` | R2.4, R9.6 | docs_setup move-record |
| D15 | plan a full rewrite (C) as a follow-up | R9.5 | not built; the gaps list tracks content |

## Tests run (only what was touched; no full suite, no Docker)
- `python3 -I -m unittest discover -s claude/plugins/docs/tests -t claude/plugins/docs/tests`: 79 tests OK (test_lib, test_setup, test_index, test_fold, test_check, test_work, test_hooks).
- `python3 tools/spec_check.py claude/plugins/docs/references/docspec.md`: clean.
- `claude/plugins/delivery/tests` (unittest discover): 259 tests OK (new: Co688Tests in test_post_tool.py, ReconcileTests in test_watch.py, PlanAdoptsOpenPrTests in test_ledger.py). New cases failed before the fix (checked).
- `python3 tools/test_delivery_runner.py`: all passed (runner_plan scenarios, 9 new/rewritten). `python3 tools/test_delivery_hooks.py`: 53 passed.
- Guards: `tools/test_ci_areas.py`, `tools/test_model_profiles.py`, `tools/test_change_notes.py --no-mutants` (131 checks), `change_notes.py check --config tools/change-notes.json`, `claude plugin validate` on the marketplace and the plugin: all pass.
- Not run: CI on GitHub (draft PR; the ready PR runs it), mutation passes.

## Open questions for the owner
1. **Mermaid is not committed.** D11 says the index vendors mermaid.js. The plugin does not ship the 3 MB file: `docs_index.py fetch-mermaid` downloads pinned 11.4.1 (not exercised here; no network test) or `--mermaid PATH`. Without it diagrams show as readable source with a note. Commit a copy in `plugins/docs/vendor/`?
2. **Phase 3 pieces outside the new plugin were not touched** (not in this task's ownership): `join.py` calling `docs_work.py strip --apply` and putting `summaries` in the PR body; the brief template `docs:` line (D7); STACKSPEC section 16 and `spec-new` path fixes (D12 "others point to it"); an artifacts promote-to-spec step. DOCSPEC R10.3 and R8.5 state them as requirements.
3. **Plugin starts at 0.0.0** so the pending `minor` note folds it to 0.1.0 on main. Say if you want 1.0.0.
4. **Migration guesses** are by file name (`docs/specs/<x>.md` -> `features/<x>/spec.md` unless the name says stack/auth/security/...). An image next to a moved spec lands in `architecture/`; `--map` fixes it, but it is crude. App design specs go to `archive/design-specs/` (D10 retires them).
5. **U1 (UX rule text outside the design system) is an error**, as D10 says "a guard fails". It is regex-based and can false-positive; `<!-- ux-ok -->` is the escape. Make it a warning first?
6. **CI wiring was added** (new `docs` area in `tools/ci_areas.py`, a `docs` job in `spec-lint.yml`, nightly list). Not run on GitHub yet.
7. **Tokenizer on Windows paths** is tested with forward slashes and quoted arguments; backslash paths with `\U`-style sequences keep their raw text but were not exercised on Windows.
8. Case (c) of the hook prompt (a lost write) is mitigated (longer second lock wait, blocks.log line) but its true cause is still unproven; the new blocks.log line will show it next time.
