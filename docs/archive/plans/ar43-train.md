> Superseded by [decision 0012](../../architecture/decisions/0012-release-timeline-and-state-column.md) and the [artifacts spec](../../features/artifacts/spec.md). History only, not binding.

# AR43 train: release timeline and feature State column

Integration branch `AR43-integration`; one agent branch `AR43-release-timeline` (owns `claude/plugins/artifacts/**`, `tools/test_render_artifacts.py`, `tools/test_project_artifacts*.py`, one change note). The owner approved the design from a hand-made preview (Full Progress Version 71, decision D10 in `content/artifacts/decisions.json`). luismc-artifacts **minor**, ARTIFACTSPEC **minor**; the record format string stays valid (new fields are optional).

## 1. Release tasks (record)

- A task may be a **release**: `task-add`/`set-task-status` take `--release` (sets `"release": true`).
- A release may carry **phases**: repeatable `--phase NAME=HH:MM-HH:MM` (today, the project's time zone) or `NAME=DD Mon HH:MM-DD Mon HH:MM`; NAME is one of `agents`, `join`, `ci`, `merge` (merge + cleanup), stored as `"phases": [{"name", "start", "end"}]` (ISO with offset). `--phase ""` clears them.
- A release may carry one named **risk**: `--risk "LABEL=MINUTES"` (e.g. `+1 fix round=10`), stored as `"risk": {"label", "minutes"}`; `--risk ""` clears it.
- Any task may name the release it rides: `--rides <release task id>` (`"rides"`), checked to exist and be a release.
- **Expected = the sum of the phases.** When a release has phases, its Expected time must equal the end of its last phase (to the minute); a writing command refuses a mismatch (new R-ID). No silent padding.

## 2. Release timeline (Full Progress section 0)

Above the status checklist, after the key line, when at least one open (not Live/Done) release exists. Rendered inline SVG, deterministic (same inputs, same bytes; the "now" mark uses the render stamp, never the wall clock):
- One row per open release, ordered by Expected; label = `<ID> · <item>` and, below, the IDs of the tasks that ride it.
- Today's axis is to scale: from the earliest phase start (or the stamp) floored to the half hour, to the latest worst case (or Expected) ceiled to the half hour, ticks every 30 minutes (every hour beyond 4 hours). Releases whose Expected is a later day sit after an axis break, one slot per day, as an outline diamond with the day.
- Phases are bars in fixed colours from the design tokens: agents `--running-mark`, join `--signal`, ci `--live`, merge `--ink`; a release without phases is a filled diamond at Expected only (or an outline diamond for a day estimate).
- Filled diamond at Expected with `live ~HH:MM`. A risk is a thin `--rule-strong` extension from Expected to Expected + minutes, ending at an outline diamond, labelled `LABEL → worst ~HH:MM`.
- A red `--failed` "now HH:MM" line at the render stamp when it falls inside today's axis.
- `<figure class="release-timeline">` with `<figcaption>Next releases (<timezone label>)`, `role="img"` and an `aria-label` that states each release's Expected and worst case; a legend line under it naming the colours and "Expected is the sum of the phases". It scrolls inside its own box at phone width (`min-width` on the SVG inside an `overflow-x:auto` wrapper). Both themes through tokens only.

## 3. State column (Full Progress section 1)

A `State` column after `Tasks`: `Complete` (status-live chip) when the feature has no open task and no open decision; otherwise one chip per open status with its count, in the order Running, Needs you, Failed, Waiting, Built, To do, On hold, plus `N open decision(s)` (needs-you chip). Sortable header like the others is not required.

## 4. Spec, tests, rules

- ARTIFACTSPEC: new requirements after R5.37 (timeline, State column, release fields, Expected = sum of phases), the record schema table and `task-add`/`set-task-status` usage; a change note `docs/specs/changes/AR43-release-timeline.md` (`spec:` and `plugin:`, `change: minor`). Never edit version lines.
- Update the session-start rule text (the "When you give an Expected time" bullet) to say: a release's Expected is the end of its last phase; name any risk instead of padding.
- Tests: renderer cases (rows, axis, break, risk, now line, no releases = no figure, determinism, both themes via tokens only) and command cases (flags, refusal on mismatch, `--rides` to a non-release refused, State column counts). Run locally only the artifacts suites you touch (renderer, commands; hooks only if you change hooks). No CI runs, no Docker.
- Stop only processes you started. Commit with the `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer; push the branch; no PR.
