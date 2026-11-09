# DS197 report: Rust wizard text

## What changed
- `tech-stack-setup/SKILL.md`: Phase 1 machine-side question; Phase 3 native_components binding (parts, written reason D145, targets, napi build matrix, cross-compile licence note, Windows option D144, signing row, what not to change); Phase 7 Cargo workspace layout; Mode 2 Rust audit wording. No renumbering.
- Notes: `docs/architecture/changes/DS197-rust-wizard.md`, `docs/features/project-setup/changes/DS197.md`.

## Tests
- `python3 tools/ci_areas.py --branch-advice`: heavy, unreadable diff, run spec-lint (below).
- `python3 claude/plugins/docs/scripts/docs_check.py`: 0 errors, 2 warnings (T2 on other specs, unrelated).
- spec-lint: see below.
