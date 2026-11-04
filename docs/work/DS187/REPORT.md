# DS187 report

Reproduced: with docs/design-system/v2, next-version and docs/archive/design-system-v1/, docs_check warned DS3 "without a gap" (R15.1).

Fixed:
- `design_system.py`: new `archived()`; DS3 loop now checks each number below the highest live one and accepts `docs/archive/design-system-vN/` or `docs/archive/design-system/vN/`. A gap with no archive still warns.
- Checked the rest: approvals.json entry for an archived version gives no DS2 (loop is over live folders only); `enforced()` picks the highest live version; branch diff in `check()` only looks at live folders, so it already passed; its D-skip for archived versions is a safeguard.
- Guard templates (typescript-vitest): `isArchived()` in design-system.ts; layout guard accepts archived numbers; freeze guard accepts a delete of a numbered folder that is archived. Risk: these .ts files were edited but not run (no vitest here).
- docspec.md R15.1: one sentence added. No Version line, numbering or change log touched.

Tests: 4 new tests in test_design_system.py (gap archived both layouts, gap unarchived warns, approval of archived version, branch archive). Two failed before the fix, all pass after.
