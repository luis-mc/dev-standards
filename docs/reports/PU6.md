# PU6: collapsible At a glance groups

Branch `PU6-integration`. Plugin luismc-artifacts 1.9.0 -> 1.10.0, ARTIFACTSPEC 1.9.0 -> 1.10.0.

## Change
- Section 0 "At a glance" groups (Needs you, Running now, Built, Waiting, Live) are now `<details class="glance-group">` with a `<summary>` (chevron, label, count "1 task" / "3 tasks"), the same fold look and CSS as the PU5 checklist groups (R6.12).
- Open by default: Needs you, Running now, Waiting. Closed: Built, Live (done work, the PU5 rule). An empty Needs you stays open with "Nothing needs you."
- No script; groups stack at every width (no grid columns), summary tap target 2.75rem.
- Spec: new R6.13 (6.7), R5.33 updated, check table row; change note folded (spec + plugin version).
- Renderer: `glance_open`, `_at_a_glance`, `check_html` (structure, open state, count).
- Tests: `glance_groups_are_collapsible_details`, `check_finds_a_wrong_glance_state`, updated glance helpers and CSS test.

## Status
- Implementation done; suites and consumer check: see the PR.
