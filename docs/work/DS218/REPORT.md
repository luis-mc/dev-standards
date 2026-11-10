# DS218 report

Base check: `git merge-base --is-ancestor 828faa65 HEAD` passed. origin/main date: Tue Nov 10 13:24:27 2026.

## What changed
1. Deleted the 11 PNG files in docs/archive/reports/CO669/. CO669.md now says they were removed (10 Nov) and the text describes what they showed.
2. Deleted tools/convert_interim_record.py and its test. Removed both from .claude/suites.json and tools/ci_areas.py. Dated reports and docs/project/ pages are unchanged.
3. spec-lint.yml: added steps for test_artifacts_ar67 (artifacts job, after ar66), test_check_stack_rust and test_questions_stop (profiles job), test_delivery_cloud (delivery-ci-scripts job). Added an area rule in tools/ci_areas.py for test_check_stack_rust (profiles). No DL173 step was on main.
4. Moved docs/testing.md to docs/guides/testing.md (links fixed in AGENTS.md, test-cost spec, delivery spec). Moved the two audits and hook-list-mismatch.md to docs/archive/reports/, rust-beside-js-plan.md to docs/archive/plans/ (link in rust-beside-js.md fixed). CI and test_spec_check.py use the plugin's spec_check.py; tools/spec_check.py deleted. specs spec: dropped the tools/spec_check.py source and symlink sentence.

## Not edited, for the owner
- claude/plugins/docs/references/docspec.md R13.3 still names tools/spec_check.py.
- Other plugin files that name tools/spec_check.py: spec-new SKILL.md and template, spec-check SKILL.md, project-setup skills, delivery CONTRACT.md, artifactspec.md, authentication.md, dev-standards.yml.

## Tests
- python3 -I tools/test_spec_check.py: 24/24 pass
- python3 -I tools/test_ci_areas.py: pass
- python3 -I tools/test_artifacts_ar67.py: 3 passed
- python3 -I tools/test_check_stack_rust.py: 9 OK
- python3 -I tools/test_delivery_cloud.py: OK
- python3 -I tools/test_questions_stop.py: 0 problems
- docs_check.py: G1 (generated files) expected; M1 handled by commit line `Docs: none, repo cleanup (D180)`.

## CI: spec-lint.yml on DS218-leftover-cleanup (run 42829350761)
Every job ended success or skipped, except `docs check`: failure from G1 (generated files) and W1 (this report), both expected. First pass had jobs cancelled by the runner (not by a test); they were re-run and passed, including the artifact renderer job with the new ar67 step, the model profiles job with the two new steps, and delivery CI scripts with the cloud step.

Branch head SHA: see `git log -1` of DS218-leftover-cleanup (report written before the final commit).

READY
