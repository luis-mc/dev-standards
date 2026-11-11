# DL259 report

Base check: render_artifacts.py has check_tokens, NEUTRAL_TOKENS, own_design_problems. OK.

## What changed
- render_artifacts.py: new accent_tokens(); check_tokens(css, accents_only=False); own_design_problems uses accents_only.
- project_artifacts.py: design set and check call check_tokens with accents_only=True.
- DESIGN.md: token contract wording; spec R5.11d; notes for the artifacts feature and the docs plugin (patch).
- tools/test_artifacts_dl259.py (6 cases), registered in .claude/suites.json.

## Tests
- run_suite.py --measure artifacts-dl259: 6 passed, 0 failed.
- run_suite.py render-artifacts: 163 passed, 0 failed.
- project-artifacts test_design_set_and_default, test_design_set_validates_tokens: pass.
- claude/plugins/docs/tests/test_dl239_badge_colour_fonts.py: 17 OK.
- docs_check.py: only W1 on docs/work/ (expected on a branch).
- CI spec-lint areas=specs,artifacts,docs: specs, artifacts (3m19s) and docs plugin jobs passed; only the docs check job failed, on the expected W1.

## Follow-ups
- Strip docs/work/ before the join (docs_work.py strip).
- Code head SHA before this report commit: 3e27868.

READY
