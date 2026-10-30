# ARTIFACTSPEC — Project Artifacts Specification

**Status:** Normative
**Version:** 1.15.0
**Applies to:** every project that keeps feature artifacts and a full-progress artifact with the `luismc-artifacts` plugin
**Audience:** Claude Code sessions in those projects, and the implementers of `luismc-artifacts`
**Owner:** Luis Carvalho
**Last reviewed:** 2026-10-11
**Changes in 1.3.0:** an open row's Expected can say what sets the estimate: an optional `expected_basis` (at most 80 characters, open statuses only), given with `--basis`, shown in a small muted line under the Expected value and dropped when the row goes Live, Built or Failed (R6.10, R6.11); and where the record worktree lives is a per-project setting, the environment variable `LUISMC_ARTIFACTS_WORKTREE` first, else `record_worktree` in the git-ignored `.claude/artifacts-local.json`, else the default, resolved by one function for the script and the hooks, with the old worktree removed when the setting moves (R4.24 to R4.27). Nothing is required of an existing record or project.
**Changes in 1.2.0:** the claude.ai pages that feature artifacts had before they became files are retired, not lost: their URLs move to the manifest's `retired` list, are recovered from the history of `manifest.json` when an earlier version already dropped them, are listed by `pending`, `check` and the hooks, and are deleted only with the owner's confirmation, then recorded with `mark-deleted` (R4.19 to R4.23, R8.13); and a project upgrading from an older version needs no manual step: the after-command hook delivers the rule once per session without a restart, the hooks tell the session to migrate an older record and the end-of-turn hook blocks until it has, and an older copy of the rule file is removed (R8.12, R8.14, R8.15, R10.6). The record format string stays `ARTIFACTSPEC 1.0.0`.
**Changes in 1.1.0:** the activity rule and the status `Built` (R3.2 to R3.5, R6.1, R6.9), the rule delivered at session start (R8.9, R10.4, R10.5), the end-of-turn check on background work (R8.8, R8.10), §5.4 Decisions (`decisions.json`, R5.14 to R5.26), feature artifacts as standalone HTML files in the repository that are never published (R5.27 to R5.29, R9.5), Full Progress published once per turn, at its end (R3.1, R9.1), with local-file links to the feature files (§5.5, R5.30 to R5.32), the Earlier fold for `Live` rows only (R6.3), and the end-of-turn background check armed by background agents only (R8.8). Plugin 1.1.1 made R7.1 incremental: a writing command refuses only a change that adds a finding (R7.1, R7.1a). The record format string in `manifest.json` and `registry.json` stays `ARTIFACTSPEC 1.0.0`: existing records stay valid.

---

## 0. How to use this document

### 0.1 What this document is

A project builds many things at once, and its owner needs to see at any moment
what is live, what is running and what needs them, without reading code or
chat. This specification defines the two kinds of project artifact that show
it (feature artifacts and one full-progress artifact), the record in the
project's repository they are generated from, and the commands and hooks that
keep them current. An implementer can build `luismc-artifacts` from it; a
reviewer can check a project's artifacts against it with
`project-artifact-check`.

**What this document is not:** it does not define the content of a feature
(that is the feature's own business), the claude.ai Artifact service, or how a
project plans its work.

### 0.2 Reading order

1. §1 scope and definitions.
2. §4 the record: manifest, task registry, content.
3. §5 what an artifact looks like, §6 statuses and the checklist.
4. §7 commands, §8 hooks, §9 publishing and recreation.
5. §13 test gate and §14 conformance gate.

No script is written before §4 and §7 are settled; the skills and hooks call
the script and never edit the record themselves.

### 0.3 Requirement language

**MUST** / **MUST NOT** are binding. **SHOULD** / **SHOULD NOT** may be
deviated from only with a recorded reason. **MAY** is optional.

Requirements are numbered `R<section>.<n>` and are individually citable.
Letter suffixes (`R<section>.<n>a`) mark requirements added after first
publication. Numbering is append-only: a retired number is never reused, and
sections are never renumbered to close a gap. Invariants are numbered
`INV-<n>`: a property that holds at every instant.

### 0.4 What changed in 1.1.0

**1.15.0 — 2026-10-30.**

- New `retire KEY [--yes]` removes a finished feature artifact (every task Live or Dropped) and its content, moving it to the manifest's `retired_features` list with its decisions archived in `retired/<key>.decisions.json`; its tasks keep their owner, Full Progress lists it in one collapsed line, a retired key is reused only with `feature-new --force`, and without `--yes` it is a dry run (R4.31 to R4.36).

**1.14.0 — 2026-10-26.**

- The At a glance group "Waiting or on hold" is now "Waiting for other work", and a Waiting or On hold task that waits on the owner moves to Needs you, set with the new optional `waits_on` field (`--waits-on owner|work` on `task-add` and `set-task-status`, default `work`, R5.34a); the rows of both groups read what they wait on first, then the item, then Expected, and the Needs you count, sentence and feature summary include the owner's waits.
- `set-task-status ID STATUS --started "DD Mon ~HH:MM"|HH:MM` sets when a task began, so the bar of a waiting or needs-you no-release task on the timeline starts there and not at "now"; a task that first moves to Running gets it automatically (R5.48). A ninth status, `Dropped`, closes a task folded into another or no longer wanted without claiming it shipped: not open, off the timeline, listed under `Live or built` as `dropped: folded into RELEASE-n`, with `--into ID` (required for a release) or `--reason TEXT` (R5.49, R6.1).
- Full Progress section 1 splits the feature artifacts into two collapsible folds, the page's own `status-fold` element: `Feature artifacts in progress (n)`, open by default, and `Complete feature artifacts (n)`, closed by default, each with the same sortable table or a one-line note when empty; `check` verifies the folds, their open state, counts and membership (R5.50).

**1.13.0 — 2026-10-18.**

- A release whose item already starts with its own `RELEASE-<n>` shows the number once in the timeline and the rows (R5.45), and `set-task-status --item TEXT` corrects a task's title, recorded in its History.

**1.12.0 — 2026-10-17.**

- R5.42b: the release timeline gains a second strip, Other work (no release), with one bar per open no-release task due today or tomorrow, on the same axis.

**1.11.0 — 2026-10-14.**

- Full Progress is published at least hourly and whenever a release task's status or phase changes: the end-of-turn hook blocks on both (R8.18, R9.8, R9.9), `pending --refresh` and `publish_hourly.py` drive the hourly publish (R9.10), `pending` records the publish copy's hash and write time and `mark-published` refuses a stale or edited copy (R9.11), and `check` and the hook flag open rows whose Expected time has passed (R6.14, R8.19).

**1.10.0 — 2026-10-13.**

- Each group of the At a glance block in section 0 (Needs you, Running now, Built, Waiting, Live) is a collapsible native `<details>` like the checklist groups (R6.13): chevron, label and a task count in the `<summary>`; Built and Live start closed, the others open, and an empty Needs you group stays open with its sentence.

**1.9.0 — 2026-10-13.**

- Every checklist group in Full Progress and in feature artifacts is a collapsible native `<details>` (R6.12): the heading sits in the `<summary>`, `Live or built` always starts closed (and says how many Built and Live rows it holds), every other group starts open, and the `Earlier` fold now sits inside `Live or built`.

**1.8.0 — 2026-10-12.**

- The plugin writes files and never git state: the record is written in `docs/artifacts/` of the working tree and left uncommitted, and the project commits and pushes it when it chooses. The plugin never runs `git commit`, `push`, `fetch`, `pull`, `reset`, `rebase`, `checkout`, `switch`, `stash`, `add` or `worktree add`/`remove`, nor a `gh` command that writes. The record worktree is retired and its old copy migrates once, by itself, when newer; `commit` and `push` are removed (they exit 1) and `migrate` is added; no hook or `pending` pushes. R4.13 to R4.17, R4.24 to R4.29, R7.6, R8.16 and R8.17 are rewritten or retired, keeping their IDs; D23 is new. The record format string stays `ARTIFACTSPEC 1.0.0`.

**1.7.0 — 2026-10-12.**

- Full Progress needs a publish only when what the owner sees changes (R9.6); a publish refused for claude.ai's daily limit is deferred until the reset with `mark-deferred`, and the end-of-turn hook stops blocking until then (R9.7); a task that ships nothing can say so with `--no-release REASON` and be Running without a release (R5.47a).

**1.6.1 — 2026-10-11.**

- The release timeline puts every release due within 24 hours on its time axis, across midnight, so a release expected just after midnight keeps its phase bars (R5.42, R5.42a).

**1.6.0 — 2026-10-11.**

- Releases are numbered `RELEASE-<n>` (`--release` gives the next number, `--rides` accepts the name, older `"release": true` rows are numbered by the migration, R5.45); Full Progress groups its checklist by release, then `Not in a release yet`, and Live or Built rows show the release they rode (R5.46); every Running or Built task rides a release (R5.47); tiles read `tasks live` (R5.8a); the release timeline is never scaled up (R5.43).

**1.5.0 — 2026-10-11.**

- Release tasks (`--release`, `--phase`, `--risk`, `--rides`; Expected is the end of the last phase) with a release timeline in Full Progress section 0, and a State column in the feature table (R5.40 to R5.44).

**1.4.1 — 2026-10-11.**

- R5.31: the publish copy's Copy link always targets the feature file in the record worktree, so a session checkout on another branch no longer hands out a stale page.

**1.4.0 — 2026-10-11.**

- Section 0 of every artifact gets a generated At a glance block (R5.33 to R5.35): Needs you, Running now, Built not released, Waiting for other work, and Live in the last 24 hours, one task per line. The lede becomes an optional short note (R5.3, R5.7), a lede over 300 characters is a warning (R5.37), and Full Progress section 1 shows a generated summary for a feature with an empty lede (R5.36).
- Full Progress section 1 becomes a table `Feature artifact | Last updated | Tasks | Where it stands` (R5.6): the new column shows the time each feature page last changed (its stamp, kept in the manifest entry as `updated`, R4.30), and the rows start newest first. The two headers `Feature artifact` and `Last updated` are buttons that sort the rows on the page and reverse on a second click, with an arrow and `aria-sort` (R5.39); the template's script does it and stores nothing. Each feature page shows `Full Progress published: DD Mon HH:MM (<label>)` right under its stamp, linking to Full Progress's URL (R5.38), from the new manifest field `published_at` that `mark-published` sets; recording a publish redraws the feature pages keeping their stamp, so Full Progress does not change and `pending` has nothing to list again. A command that renders features and Full Progress draws the features first (R7.5).
- Writing commands commit the record but no longer push it; the record is pushed once, at the end of the turn, by `pending`, by a new `push` command and by a new before-command hook ahead of `gh pr create`, `gh pr ready` and `gh pr merge` (R4.28, R4.29, R7.6, R8.16, R8.17). This stops one secret-scan run per record commit.

**1.3.1 — 2026-10-11.**

- Every writing command also renders each page whose file differs from a fresh render (R7.5), so a plugin upgrade that changes the templates or the stylesheet brings every page up to date at the next status change instead of leaving the untouched pages in the older look until someone runs `render`.
- The publish copy of Full Progress names each feature as text with a Copy link button for its file:/// address, because a page on claude.ai cannot open a file: link; its checklist rows carry no link.

Version 1.0.0 recorded the work given to agents but not the session's own, and
left built-but-unreleased work marked Done (finished-sounding), so the full-progress artifact said
nothing was running while much was. 1.1.0 adds:

- the activity rule: every activity is a task, a task is Running while any work
  for it runs, Built means finished but not released (R3.2 to R3.5);
- the status `Done` is renamed `Built`: finished, not merged or released yet;
  `Live` is released, so no status reads as finished while something is left
  (R6.1, R6.9);
- the rule reaches every project, always current: the session-start hook
  delivers it as context, `init` no longer copies it, and `check` notes a stale
  copy (R8.9, R10.2, R10.4, R10.5);
- an end-of-turn check that background work has a Running task (R8.8, R8.10).
- decisions: a feature artifact records every option the owner was offered and
  the one chosen in `decisions.json`, drawn as a Decisions section (§5.4,
  R5.14 to R5.26);
- a publish budget: claude.ai allows 200 artifact publishes per account per
  day and every republish counts, so only Full Progress is published, once at
  the end of each turn (R3.1, R9.1); a feature artifact is a standalone HTML
  file in the repository that opens by double-click and is never published
  (R5.27 to R5.29, R9.5), and Full Progress links to the feature files as
  local files (§5.5);
- only `Live` rows fold into `Earlier`, so unreleased `Built` work is never
  hidden (R6.3); and only background agents arm the end-of-turn check (R8.8);
- a writing command refuses a change that adds a finding, not a record that
  already has some, so a record migrating from 1.0.0 is repaired one edit at a
  time (R7.1, R7.1a; plugin 1.1.1, with no change to the requirements' meaning
  for a valid record).

The record format is unchanged: `spec` in the manifest and the registry stays
`"ARTIFACTSPEC 1.0.0"`, so a 1.0.0 record is valid under 1.1.0.

### 0.5 What changed in 1.2.0

Version 1.1.0 stopped publishing feature artifacts and dropped their URLs on
migration, so the old claude.ai pages stayed up, stale, and could no longer be
found from the record; and a project upgrading from 1.0.0 needed four manual
steps (restart for the rule, a writing command to migrate, delete the old rule
copy, find and delete the old pages). 1.2.0 adds:

- the `retired` and `deleted` lists in the manifest, the recovery of dropped
  URLs from git history, and `mark-deleted` (R4.19 to R4.22);
- deletion of an old page only with the owner's confirmation (R4.23);
- `pending`, `check` and the hooks surface retired pages without ever blocking
  on them (R4.22, R8.13);
- the rule reaches an already open session through the after-command hook
  (R8.12);
- an older record is migrated because the hooks say so, and the end-of-turn
  hook blocks until it is (R8.14);
- an older copy of the rule file is removed by the migration commit (R8.15,
  R10.6).

### 0.6 What changed in 1.3.0

An Expected time with no stated reason cannot be judged: the owner could not tell
an estimate that waits on an agent slot from one that waits on a person. And a
project that keeps all its worktrees outside the repository had no way to keep
the record worktree there. 1.3.0 adds, both optional:

- `expected_basis`, the `--basis` option of `task-add` and `set-task-status`, its
  display under the Expected value and its checks (R6.10, R6.11);
- the record worktree location as a setting, one resolver, and the move of an
  existing worktree (R4.24 to R4.27).

The record format string stays `ARTIFACTSPEC 1.0.0`; a record without the new field is valid.

---

## Decision record

| # | Question | Resolution | Consequence |
|---|---|---|---|
| D1 | Where is a task's status stored? | Once, in the task registry `docs/artifacts/registry.json`. | Every checklist and tile is generated; none is typed (§4.3). |
| D2 | Do branch names start with the task ID? | Yes: `AR5-artifactspec`. | Hooks match events to tasks by branch name (§8). |
| D3 | How do changes made outside a session arrive? | At the next session start. | No cloud routine in 1.0 (§8.3). |
| D4 | Which look? | The project's own design tokens; the plugin's default design when it has none. | One fixed structure stylesheet, free tokens (§5.3). |
| D5 | App / service column? | On the full-progress artifact only. | Feature checklists keep four columns (§6.3). |
| D6 | Where is the record? | In the repo, `docs/artifacts/` of the working tree; the project commits it. | A deleted artifact is recreated from it without duplicates (§9). |
| D7 | How does a project get the plugin? | `luismc-project-setup` installs it in every project it sets up; it also installs on its own. | Installing creates nothing until the first artifact (§10). |
| D8 | Which clock do times use? | The owner's time zone, per project, from the manifest. | Expected and stamps name the zone (§6.4). |
| D9 | Does the plugin's home repository touch other projects? | No. | Each project adopts the plugin in its own sessions. |
| D10 | How does the activity rule reach a project? | The session-start hook prints the plugin's rule file as context, every session, in any project with a record. | No copy goes stale; a rule update reaches every project with the next plugin version (R8.9, R10.4). |
| D11 | Does the record format change in 1.1.0? | No. | `spec` in the manifest and the registry stays `"ARTIFACTSPEC 1.0.0"` (§4.2). |
| D12 | How are the owner's choices between options kept? | Every option offered and the one chosen, in the feature's `decisions.json`; the script draws the Decisions section. | The options, the recommendation and the choice are never lost in free text (§5.4). |
| D13 | How often is Full Progress published? | Once per turn, at the end of it, never mid-turn. | Status changes accumulate during the turn and cost one of the account's 200 publishes a day, not one per change (R3.1, R9.1). |
| D14 | Are feature artifacts published? | No. Each is a standalone HTML file in the repository, `docs/artifacts/feature-<slug>.html`. | It opens by double-click in any browser and costs no publish; Full Progress links to it as a local file (R5.27, §5.5, R9.5). |
| D15 | Which rows fold into Earlier? | `Live` rows older than 14 days; `Built` rows never fold. | Unreleased work is never hidden (R6.3). |
| D16 | What arms the end-of-turn background check? | A background `Agent`, `Task` or `Bash` call: `tool_input.run_in_background` is true. | A foreground sub-agent no longer asks for a Running task (R8.8). |
| D17 | What happens to the claude.ai pages of feature artifacts published before feature artifacts became files? | Each URL moves to the manifest's `retired` list, recovered from the history of `manifest.json` when an earlier version already dropped it; a page is deleted only with the owner's confirmation, then recorded with `mark-deleted`. | No old page is orphaned, and none is deleted without the owner (R4.19 to R4.23). |
| D18 | Does a retired page block anything? | No: not `pending`'s exit code, not the end-of-turn hook. They are listed, and the session is told once to ask the owner. | Publishing never waits for a decision only the owner can take (R4.22, R8.13). |
| D19 | How does an upgraded project get the new rule and migrate? | The after-command hook delivers the rule once per session and rule text; the hooks tell the session to run `render`; the end-of-turn hook blocks until the record is migrated. | No restart and no manual step (R8.12, R8.14). |
| D20 | What happens to the rule copy that 1.0.0 `init` made? | The next writing command deletes it from the working tree (uncommitted) when its text is one a released version shipped; an edited copy stays and `check` notes it. | The old text, which says to publish feature artifacts, stops competing with the rule (R8.15, R10.6). |
| D21 | Is the basis of an estimate part of Expected? | No: its own optional field `expected_basis`, not a `; note`. | Expected stays machine-readable (R6.6); the basis is shown apart and validated apart (R6.10). |
| D22 | Where does the record worktree live? | Retired in 1.8.0: there is none; the record is `docs/artifacts/` of the working tree. | The old setting is ignored, and an old worktree's record is copied once when newer (R4.24). |
| D23 | Does the plugin commit or push? | No: it writes files; the project commits and pushes. | A record change never triggers a deploy by itself (R4.13, R4.28). |
| D24 | What happens to a finished feature artifact? | `retire` moves it to `retired_features`, keeps its decisions and tasks, deletes its file and content (owner, 30 Oct). | Finished features stop taking most of `docs/artifacts` without breaking INV-3 or R4.6 (R4.31 to R4.36). |

---

## 1. Scope

### 1.1 In scope

| Area | Covered |
|---|---|
| Kinds | Feature artifacts and the one full-progress artifact of a project. |
| Record | `docs/artifacts/`: manifest, task registry, content, design tokens, rendered HTML. |
| Commands | `project_artifacts.py`: create, add tasks, change status, render, check, migrate, publish bookkeeping. |
| Hooks | After-command, end-of-turn and session-start hooks. |
| Look | Fixed structure stylesheet, project design tokens, default design. |

### 1.2 Out of scope

- **Publishing by a script.** Only a Claude session's Artifact tool can publish
  an artifact; the plugin makes sure the session does it (§8.2). Not ever,
  unless the Artifact service offers a non-session API.
- **Cloud routines** that update artifacts while no session runs. Not in 1.0.
- **Other document kinds** (decks, reports). Not this specification.

### 1.3 Deferred extension points

| Deferred capability | The seam that keeps it cheap |
|---|---|
| A cloud routine applying queued events | The queue file format (§8.1); a routine would run the same commands. |
| More event sources (deploy providers) | The event table in the after-command hook (§8.1), one row per pattern. |
| More artifact kinds | `kind` in the manifest (§4.2) and one template per kind (§5.1). |

### 1.4 Definitions

| Term | Meaning |
|---|---|
| project artifact | A feature artifact or the full-progress artifact of a project. Never "page". |
| feature artifact | The artifact of one feature, titled `Feature: <name>`: a standalone HTML file in the repository, `docs/artifacts/feature-<slug>.html`, never published (§5.1, R9.5). |
| full-progress artifact | The project's one artifact of all ongoing work, titled `Full Progress: <project>`: the only claude.ai artifact of the project, published once per turn (R9.1). |
| publish copy | The full-progress artifact rendered for publishing, with absolute `file:///` links to the feature files, written by `pending` to a git-ignored path (R5.31). |
| task | One unit of work with an ID, a status and an owner. |
| owner (of a task) | The feature artifact it belongs to (its `key`), or `project`. |
| project task | A task whose owner is `project`. |
| task registry | `docs/artifacts/registry.json`, the only store of task state. |
| manifest | `docs/artifacts/manifest.json`, the list of the project's artifacts and settings. |
| record | Everything under `docs/artifacts/`. |
| record worktree | Retired in 1.8.0. A git worktree of the default branch where earlier versions wrote and committed the record; `migrate` copies its record once (R4.24). |
| render | Generating an artifact's HTML from the record. |
| publish | Sending the full-progress artifact's publish copy to claude.ai through the session's Artifact tool. |
| queue | Status events waiting for the session to apply (§8.1). |
| the script | `scripts/project_artifacts.py` in the plugin. |

---

## 3. Architecture

### 3.1 Components

| Component | Responsibility |
|---|---|
| `scripts/project_artifacts.py` | The only writer of the record. Every command in §7. Python 3.10+, standard library only. |
| `scripts/render_artifacts.py` | Pure functions: record in, HTML out (§5). Imported by the script. |
| `scripts/artifact_queue.py` | Reads and writes the queue (§8.1). Imported by the hooks and the script. |
| `scripts/artifact_hourly.py`, `scripts/publish_hourly.py` | The hourly, release-change and overdue checks (R6.14, R8.18, R8.19, R9.8 to R9.10): pure helpers imported by the end-of-turn hook and the script, and the command a session's hourly cron runs. |
| `scripts/artifact_retire.py` | Retired and deleted pages, the history recovery, the migration check and the shipped rule hashes (R4.19 to R4.23, R10.6). Pure and read-only except where the script applies it. Imported by the hooks and the script. |
| `scripts/hook_after_command.py`, `hook_end_of_turn.py`, `hook_session_start.py` | The three hooks (§8). |
| `templates/feature-artifact.html`, `templates/full-progress-artifact.html` | Skeletons with placeholders: the first is a complete HTML document, the second a fragment (§5.1). |
| `templates/project-artifact.css` | The fixed structure stylesheet. |
| `design/default-design.css`, `design/DESIGN.md` | Default tokens and the token contract (§5.3). |
| `rules/project-artifacts.md` | The rule file the session-start hook delivers to every project with a record (§10). |
| Five skills | `feature-artifact-new`, `full-progress-artifact-new`, `task-add`, `task-status-update`, `project-artifact-check`. |

### 3.2 Invariants

- **INV-1** — A task's status exists in exactly one place, the task registry.
  Verified by `test_render_from_registry_only`.
- **INV-2** — A project has at most one full-progress artifact, and has one
  whenever it has a feature artifact. Verified by `test_one_full_progress`.
- **INV-3** — Every rendered HTML file in the record equals what rendering the
  record produces now: a feature artifact's standalone document and the
  full-progress artifact with relative links. The publish copy (R5.31) is not in
  the record; it differs from the committed render only in its links. Verified
  by `test_rendered_matches_record`.
- **INV-4** — No hook modifies the record. Verified by
  `test_hooks_never_write_record`.

### 3.3 Status change lifecycle

1. Event: a command the session ran, a session start, or the owner's words.
2. Queue: a hook writes the suggested change to the queue (§8.1), or the
   session acts directly.
3. Apply: the session runs `set-task-status`; the script updates the registry,
   renders every artifact that shows the task, and writes the files in `docs/artifacts/`; it commits nothing (R4.13).
4. Publish, once, at the end of the turn: the session publishes the
   full-progress artifact's publish copy when `pending` lists it, and runs
   `mark-published`. A feature artifact is a file in the repository and is
   never published (R9.5).
5. End of turn: the end-of-turn hook lets the turn end only when the queue is
   empty, Full Progress is not pending, and background work started in the turn
   has a Running task (R8.10).

- **R3.1** — Steps 3 to 5 complete in the same turn as the event. Status
  changes accumulate during the turn: the session publishes Full Progress once,
  at the end of the turn, and never mid-turn, because claude.ai allows 200
  artifact publishes per account per day and every republish counts. The
  end-of-turn hook keeps blocking until it is published (R8.3). Verified by
  `stop_blocks_when_an_artifact_is_pending` and `test_session_sequence_ends_clean`.
- **R3.2** — Every activity is a task before it starts, whoever does it: work
  given to agents and the session's own work (contracts, specs, reviews, joins,
  test runs, releases, deploys, cleanup). The rule file has a line saying so.
  Verified by `rule_file_carries_the_activity_rules`.
- **R3.3** — A task is Running while any work for it runs, and Waiting or Needs
  you when it is blocked on something or someone. The rule file has a line
  saying so. Verified by `rule_file_carries_the_activity_rules`.
- **R3.4** — Built means the work is finished but not released. Release work
  still to come (join, CI, release) is its own task, Running or To do. The rule
  file has a line saying so. Verified by `rule_file_carries_the_activity_rules`.
- **R3.5** — Before ending a turn that leaves work running in the background,
  its task is Running. The rule file has a line saying so, and R8.10 enforces
  it. Verified by `rule_file_carries_the_activity_rules` and
  `stop_blocks_background_work_without_an_active_task`.

---

## 4. The record

### 4.1 Layout

```
docs/artifacts/
  manifest.json
  registry.json
  design.css                     only when the project has its own design
  content/<key>/meta.json        one folder per artifact; full-progress key is "full-progress"
  content/<key>/NN-<slug>.html   one file per section 1..N, in order
  content/<key>/history.json     feature artifacts only
  content/<key>/decisions.json   feature artifacts only, optional (§5.4)
  content/<key>/assets/<file>    images of decision options, optional (§5.4)
  retired/<key>.decisions.json   the decisions of a retired feature (§4.10), only after `retire`
  feature-<slug>.html            a feature artifact: a standalone HTML document (§5.1)
  full-progress-<slug>.html      the full-progress artifact: a fragment, relative links (§5.5)
  README.md                      how to recreate (generated)
```

- **R4.1** — The record lives under `docs/artifacts/` and nowhere else, except
  the publish copy (R5.31), which is not part of the record. Section 0 of every
  artifact is generated and has no content file.

### 4.2 Manifest

| Field | Type | Meaning |
|---|---|---|
| `spec` | string | `"ARTIFACTSPEC 1.0.0"` |
| `project` | string | Project name shown in titles. |
| `timezone` | string | IANA zone, e.g. `Europe/Lisbon`. |
| `timezone_label` | string | Shown after times, e.g. `Lisbon`. |
| `windows_timezone` | string | Windows zone ID for the fallback, e.g. `GMT Standard Time`. |
| `design` | string | `"default"` or `"design.css"`. |
| `default_branch` | string | The project's default branch, e.g. `main`; recorded, not used to commit. |
| `merged_status` | string | Status a merge suggests: `"Live"` (default) or `"Built"`. |
| `full_progress_artifact` | object | `{key:"full-progress", title, url, file, published_sha256, published_at}`; `published_at` is the ISO time (with offset) of the last `mark-published`, absent before the first publish (R4.30) |
| `feature_artifacts` | array | `{key, title, file, prefix, apps:[...], updated}` each: no `url` and no `published_sha256`, because a feature artifact is never published; `updated` is the ISO time (with offset) of the stamp of the feature's page, written whenever the script writes that page with a new stamp, and absent in an older record (R4.30) |
| `retired_features` | array | Optional. `[{key, title, prefix, retired, url, decisions}]`: features removed by `retire` (§4.10, R4.31); `retired` is the ISO time, `url` the last claude.ai page of the feature or empty, `decisions` the path of its archive or empty. Not to be confused with `retired`, which lists old claude.ai pages. |
| `retired` | array | Optional. `[{key, title, url, retired}]`: claude.ai pages of feature artifacts still to delete (R4.19). |
| `deleted` | array | Optional. `[{key, url, deleted}]`, plus `"gone": true` for a page that no longer existed: pages recorded as deleted (R4.19). |
| `project_prefixes` | array | Task prefixes owned by the project, e.g. `["DS"]`. |
| `updated` | string | ISO time of the last change, with offset. |

- **R4.2** — `key` is lowercase letters, digits and hyphens; `prefix` is 2 to 5
  capital letters; every prefix appears once across the manifest.
- **R4.3** — The full-progress entry's `url` is empty until the first publish;
  its `published_sha256` is the SHA-256 of the committed render (not of the
  publish copy, R5.32) that was last published, empty before that. A `url` with
  an empty `published_sha256` is valid: an existing artifact adopted by a new
  record, listed by `pending` until it is published from the record. A feature
  entry has neither field (R4.18).
- **R4.4** — `file` is `<kind>-<slug>.html` with kind `feature` or
  `full-progress`; the slug is the title's words, lowercase, hyphenated.

### 4.3 Task registry

```json
{"spec": "ARTIFACTSPEC 1.0.0", "updated": "2026-10-10T12:39+01:00",
 "tasks": [{"id": "AR5", "owner": "artifacts", "app": "luismc-artifacts",
            "status": "Running", "item": "ARTIFACTSPEC 1.0.0",
            "detail": "...", "expected": "10 Oct ~14:15",
            "changed": "2026-10-10T13:02+01:00"}]}
```

- **R4.5** — A task's `id` is a registered prefix plus a positive integer; IDs
  are unique and never reused. A task is never removed from the registry (there
  is no remove command); dropped work is set On hold or Built with a detail
  saying so, so the next number, the highest plus one, is always unused.
- **R4.6** — `owner` is a feature `key` from the manifest or `project`. A
  feature task's prefix is its feature's prefix; a project task's prefix is
  in `project_prefixes`. A task moved into a feature after it got its ID keeps
  its ID, so a feature task may also carry a prefix from `project_prefixes`.
- **R4.7** — `status` is one of the nine statuses of §6.1. `changed` is set by
  the script on every status change, never by hand.
- **R4.8** — `expected` follows §6.4; an open row may also carry
  `expected_basis` (R6.10); a Waiting or On hold row may also carry `waits_on` (R5.34a); a release row may also carry `release`, `phases`,
  `risk` and any row `rides` (R5.40, R5.45). `item` is at most 80 characters; `detail`
  is plain text, at most 600 characters.
- **R4.9** — Tasks are stored in ID order (prefix, then number); rendering
  orders them (§6.2), the file does not.

### 4.4 Content

`meta.json`: `{title, hero, lede, extra_css}`. `lede` is a short note: one or
two sentences of context the registry cannot show (an incident, a constraint, a
plan). It never restates statuses: the generated At a glance block (§5.2) lists
what is live, built, running, waiting and needs the owner. It may be empty, and
a lede over 300 characters is a warning (R5.37). Each `NN-<slug>.html` is an HTML fragment whose first line is an HTML
comment holding the section title: `<!-- title: The design -->`.
`history.json`: `[{"date": "10 Oct 12:23", "change": "..."}]`, newest first.
`decisions.json` is described in §5.4.

- **R4.10** — Content fragments contain no `<script>`, no `<style>` (styles go
  in `extra_css`) and no section numbers; the renderer numbers sections.
- **R4.11** — `extra_css` may add classes but **MUST NOT** redefine a selector
  of the structure stylesheet — a redefined rule changes every artifact's
  layout in a way the check cannot see per project.

### 4.5 Time

- **R4.12** — Every time the script writes comes from the real clock at the
  moment of the change, converted to the manifest's zone: with `zoneinfo`; if
  the zone data is missing (Windows without `tzdata`), with PowerShell
  `TimeZoneInfo` and `windows_timezone`; if that fails, the machine's local
  time with a warning on stderr.

### 4.6 Writing the record

- **R4.13** — The script writes the record in `<repo root>/docs/artifacts/` of
  the session's working tree (the repo root is `git rev-parse --show-toplevel`
  of the current directory) and stops. Every writing command validates, applies,
  renders and writes the files there; they stay uncommitted. Nothing is synced
  from `origin` before a change. The plugin MUST NOT write git state: no script
  or hook of it runs `git commit`, `push`, `fetch`, `pull`, `reset`, `rebase`,
  `checkout`, `switch`, `stash`, `add`, `worktree add` or `worktree remove`, nor a
  `gh` command that writes. The git calls it makes are read-only: `rev-parse`,
  `symbolic-ref`, `status`, `diff`, `log`, `show`, `ls-files`, `config --get` and
  `worktree list`. Verified by `test_writing_commands_change_files_and_leave_git_alone`
  and `test_only_read_only_git_is_run`.
- **R4.14** — Retired in 1.8.0: the script commits nothing. A writing command
  changes only paths under `docs/artifacts/` (and `.gitignore` for `init` and
  `feature-new`, R10.2, and the deletion of a stale rule copy, R10.6); the project
  decides what to commit.
- **R4.15** — Retired in 1.8.0: there is no push, so no push race and no exit 3.
- **R4.16** — Retired in 1.8.0: there is no push, so no protection refusal and no exit 4.
- **R4.17** — The lock that serialises writing commands is a file under
  `<repo root>/.claude/` (`artifacts-record.lock`, git-ignored, R10.2), never a file
  under `docs/artifacts/`. A change that fails puts the files under
  `docs/artifacts/` back as they were. `--push`, `--no-push` and `commit --retry`
  are accepted on writing commands for compatibility and do nothing (`--push`
  prints the note of R4.28 on stderr).

### 4.7 Older records

- **R4.18** — A manifest whose feature entry still holds `url` or
  `published_sha256` (a record made before feature artifacts stopped being
  published) is read as if the entry did not have them. The next writing
  command rewrites the manifest without them, moves each `url` to the
  `retired` list (R4.19) and renders every artifact again (a feature artifact
  as a standalone document, Full Progress with relative links); `check`
  reports the dropped fields as a note, not a finding, and
  `mark-published` never records a feature URL (R9.5). Verified by
  `test_old_feature_urls_migrate`.
- **R4.19** — `retired` is `[{"key", "title", "url", "retired": "<ISO time>"}]`
  and `deleted` is `[{"key", "url", "deleted": "<ISO time>"}]`, with
  `"gone": true` when the page no longer existed; both are optional, and an
  absent list is an empty one. Migration (R4.18) moves a feature entry's `url`
  to `retired` instead of dropping it, unless that URL is already retired or
  deleted. A URL is in at most one of the two lists, and Full Progress's URL is
  in neither. `check` reports a malformed list as a finding. Verified by
  `test_migration_keeps_feature_urls_as_retired` and
  `test_full_progress_url_is_never_retired`.
- **R4.20** — A record already migrated by 1.1.0 to 1.1.2 (feature URLs gone)
  recovers them: when the record loads (so in `check`, `pending` and every
  writing command), the script scans the history of `manifest.json` reachable
  from `HEAD` of the working tree for feature entries
  that had a `url`, and adds each URL not already retired, deleted or Full
  Progress's to `retired`. The scan is bounded (the 200 most recent commits
  that touch a `url` line, read with one `git log` and one `git show` per commit) and keeps no cache outside
  the record; a writing command writes the recovered entries to the manifest.
  Verified by `test_retired_urls_are_recovered_from_history`.
- **R4.21** — `mark-deleted [KEY] --url URL [--gone]` moves the retired entry
  with that URL to `deleted` (stamped with the time), so it is never listed
  again, also not by the history recovery. `--gone` records a page that no
  longer exists (404) and has the same effect, with `"gone": true`. It refuses
  a URL that is not retired, a KEY that is not the entry's, and Full Progress's
  URL, and changes nothing. Verified by
  `test_mark_deleted_removes_the_page_for_good` and `test_mark_deleted_gone`.
- **R4.22** — `pending` lists every retired page, with its title and URL and
  the instruction to ask the owner to confirm, delete it with the Artifact tool
  (`action: delete`) and run `mark-deleted`; in `--json` they are the `retired`
  array. A retired page never changes `pending`'s exit code. `check` reports
  the retired pages as a note, not a finding. Verified by
  `test_pending_lists_retired_pages_without_changing_its_exit_code` and
  `test_check_notes_retired_pages`.
- **R4.23** — A retired page is deleted only with the owner's confirmation:
  the script cannot delete a claude.ai page, so the session asks the owner,
  deletes each confirmed page with the Artifact tool, then runs `mark-deleted`.
  A page the owner declines stays listed. The rule file says so (R10.3).
  Verified by `rule_file_carries_the_retired_pages_rule`.

### 4.8 The retired record worktree

- **R4.24** — The record worktree is retired. `project_artifacts.py worktree`
  prints the record directory, `<repo root>/docs/artifacts`.
  `LUISMC_ARTIFACTS_WORKTREE` and `record_worktree` in
  `<repo>/.claude/artifacts-local.json` are ignored for writing and reading;
  `check` says so once, as a note, not a finding. **Migration, once and by
  itself:** when the old record worktree exists (by default
  `<repo>/.claude/worktrees/artifacts-record`, or the path the old setting names)
  and its `docs/artifacts/registry.json` is newer than the working tree's (by
  the newest `changed` stamp of its tasks, or the working tree has no
  registry), the files of its `docs/artifacts/` are copied into the working
  tree's `docs/artifacts/`, and the script says, once: `luismc-artifacts: the
  record now lives in docs/artifacts/ and is never committed or pushed by the
  plugin; copied it from <old path>. You may remove that worktree with git
  worktree remove <path>`. The plugin never removes the worktree itself. The
  command `migrate` runs exactly this and prints the line only when it copies
  (exit 0); every writing command and every read of the record runs it first,
  and the session-start hook runs it when it applies. Verified by
  `test_migrate_copies_the_old_record_once_and_only_when_newer`,
  `test_migrate_runs_before_a_writing_command`,
  `test_worktree_prints_the_record_folder_and_ignores_the_old_setting`.
- **R4.25** — Retired in 1.8.0: a worktree setting is no longer read, so none is refused.
- **R4.26** — The old setting file `.claude/artifacts-local.json` stays in
  `.gitignore`; the record never holds a machine path.
- **R4.27** — Retired in 1.8.0: the plugin does not move or remove a worktree.

### 4.9 Not pushing the record

- **R4.28** — The commands `commit` and `push` are removed: calling either
  exits 1 with `the plugin no longer commits or pushes (ARTIFACTSPEC 1.8.0);
  commit docs/artifacts/ when you choose`. Exit codes 3 and 4 are no longer
  used. No hook pushes, and `pending` does not push. Verified by
  `test_commit_and_push_are_removed` and `test_pending_does_not_push`.
- **R4.29** — Retired in 1.8.0: nothing is fetched or rebased, so the merge of
  concurrent record commits is the project's own git work.
- **R4.30** — A feature entry's `updated` is the ISO time (with offset) of the
  stamp of the feature's page; the script sets it whenever it writes that page
  with a new stamp (a task status change, a content edit, a decision, a plugin
  upgrade that redraws the page), and never when it writes the page keeping its
  stamp (R5.38). Full Progress section 1 shows it (R5.6); a record without it
  is read from the `<time datetime>` of the feature file. The full-progress
  entry's `published_at` is the time `mark-published` last ran; the feature
  pages show it (R5.38). Both are ISO times with an offset, or absent.
  `check` reports a malformed one.
  Verified by `test_feature_updated_and_published_line`.

### 4.10 Retiring a finished feature

A finished feature artifact (every task Live or Dropped) only costs space: a project can have dozens, and `check`
fails when a manifest feature lacks its file or content (INV-3) or a content folder has no manifest entry (R4.1).
`retire` removes one cleanly and keeps what history needs.

- **R4.31** — `project_artifacts.py retire KEY --yes` moves the feature from `feature_artifacts` to the manifest's
  `retired_features` list: `{key, title, prefix, retired, url, decisions}`, all strings. `check` reports a
  malformed entry, a key that is also a live artifact key, and a prefix used twice across `feature_artifacts`,
  `retired_features` and `project_prefixes` (R4.2). A retired feature is never rendered, so `render` and every
  stale refresh (R7.5) leave it gone. Verified by `test_retire_moves_the_feature_and_check_stays_clean` and
  `test_check_reports_a_damaged_retired_record`.
- **R4.32** — `retire` keeps the feature's `decisions.json`, byte for byte, as
  `docs/artifacts/retired/<key>.decisions.json` (the entry's `decisions` field names it; `-2`, `-3` are added to the
  file name when a reused key is retired again); a feature with no decisions writes no archive and `decisions` is
  empty. Images of decision options (`assets/`) are not kept. `check` reports an entry whose archive is missing.
  The feature's `feature-<slug>.html` and its whole `content/<key>/` folder (sections, History, assets) are deleted.
  Verified by `test_retire_moves_the_feature_and_check_stays_clean`, `test_retire_without_decisions_writes_no_archive`.
- **R4.33** — `retire` refuses (exit 1, nothing written) unless every task owned by the feature is `Live` or
  `Dropped` and the feature has no open decision (R5.23); a feature with no task qualifies. Every task keeps its
  owner: R4.6 accepts a retired key as an owner, with the retired entry's prefix. The tasks stay in the registry
  and on Full Progress, as text rows with no link. Verified by `test_retire_refuses_a_feature_with_an_open_task`.
- **R4.34** — Full Progress section 1 lists the retired features in one closed `<details class="retired-features"
  data-group="features-retired">` after the two feature folds, titled `Retired feature artifacts (n)`, one `<li>` line each: the title, the key,
  `retired DD Mon` and, when kept, the decisions archive. The fold is absent when none is retired. It is drawn from
  the manifest, so INV-3 covers it. Verified by `test_retire_moves_the_feature_and_check_stays_clean`.
- **R4.35** — A retired key is not reused: `feature-new` refuses a key in `retired_features` and any prefix a retired
  feature holds, unless `--force` is given for the key. `--force` removes the retired entry, so the key is a live
  feature again and its old tasks belong to it (the new feature must keep the old prefix, else R4.6 refuses the
  change); a prefix held by a retired feature under another key is refused even with `--force`. `task-add` and
  `set-task-status` refuse a retired owner's tasks (R4.36). Verified by
  `test_retired_tasks_are_history_and_the_key_is_not_reused_without_force`.
- **R4.36** — Without `--yes`, `retire` is a dry run: it prints the tasks it keeps, each file it would delete with its
  size, the total, and the archive it would write, and writes nothing (`--json`: `dry_run`, `files`, `bytes`, `tasks`,
  `archive`, `archive_bytes`). With `--yes` it is a writing command like any other (R7.1): it writes files and stops
  (R4.13), puts everything back when the result would be invalid, and renders Full Progress. It never deletes a
  claude.ai page: a page of a retired feature stays on the `retired` list until the owner confirms its deletion
  (R4.23). The tasks of a retired feature are history: `task-add --owner KEY` and `set-task-status` on them are refused.
  Verified by `test_retire_dry_run_lists_files_and_changes_nothing`, `test_retire_leaves_git_alone_and_a_failed_retire_restores_the_files`.

### 4.11 The record folder

- **R4.37** — The record folder is a per-project setting: `record_dir` in `.claude/artifacts.json` (committed with the
  project), a folder relative to the repository root and strictly under `docs/` (for example `docs/work/artifacts`).
  When the file or the key is absent the folder is `docs/artifacts`, so a project that sets nothing is unchanged. A
  value that is absolute, contains `..`, is `docs` itself or lies outside `docs/` is refused: every command that needs
  the record exits 2 naming the setting, and the hooks read the default. Every path this specification gives as
  `docs/artifacts/` means this folder. Verified by `test_record_dir_setting_absent_is_the_old_path`,
  `test_record_dir_setting_is_used_by_every_command`, `test_record_dir_setting_outside_docs_is_refused`,
  `test_hooks_read_the_record_dir_setting`.
- **R4.38** — `move-record NEW_DIR [--yes]` moves the record folder to NEW_DIR (same rules as R4.37) and writes the
  setting; moving back to `docs/artifacts` removes the key. It is a plain file move: it does not run git, so the
  project commits the moved folder and `.claude/artifacts.json` when it chooses (R4.28). Without `--yes` it is a
  dry run that prints the plan and writes nothing. It refuses (exit 1) a NEW_DIR that exists and is not an empty
  folder, and (exit 2) one that contains the current folder or lies inside it. Verified by
  `test_move_record_dry_run_changes_nothing`, `test_move_record_moves_the_folder_and_writes_the_setting`.

---

## 5. Artifact structure and look

### 5.1 Templates

The templates hold `{{placeholders}}`: `title`, `fonts_link`, `design_css`,
`structure_css`, `extra_css`, `kind_label`, `project`, `hero`, `contents`,
`sections`, `stamp`. A feature artifact is rendered as a complete HTML document
that opens in any browser on its own; the full-progress artifact is rendered as
an HTML fragment beginning with `<title>`, as the Artifact tool expects (no
`<html>`, `<head>` or `<body>`). Both are described in §5.5.

- **R5.1** — A feature artifact's title is `Feature: <name>`; the full-progress
  artifact's is `Full Progress: <project>`.
- **R5.2** — Sections are numbered from 0 in order with no gaps, and the
  contents list shows the same numbers and titles.
- **R5.3** — Section 0 is titled `Status and checklist` and holds, in order:
  the stamp, the lede (omitted when empty, R5.7), the At a glance block (R5.33),
  the tiles, the status key and the checklist.
- **R5.4** — A feature artifact's last section is `History`, a table
  `Date | Change`, newest first. The full-progress artifact has no History.
- **R5.5** — The stamp reads `Last update: DD Mon HH:MM (<timezone_label>)` in
  a `<time>` element whose `datetime` attribute is the ISO time with offset.
- **R5.6** — The full-progress artifact's section 1 lists every feature
  artifact, split in two folds (R5.50), each holding a table `Feature artifact | Last updated | Tasks | State | Where it stands`:
  its link to the feature's file (R5.30, R5.31), the time its page was last
  updated (its stamp, `DD Mon HH:MM` in a `<time>` element, from the manifest
  entry's `updated`, R4.30), its task ID range, its State (R5.44) and one line on where it stands
  (taken from its `meta.json` lede's first sentence, or its generated summary
  when the lede is empty, R5.36). The committed rows of each table are in the default order
  (R5.39): Last updated, newest first, ties by title. Section 1 is generated, so the full-progress artifact's
  content files `01-*.html` onward render as sections 2 and up.

### 5.2 Lede, At a glance and tiles

- **R5.7** — The lede is the content lede alone, in `<p class="lede">`: a short
  note (§4.4). When the content lede is empty the paragraph is omitted. The
  statuses are not in it: the At a glance block's Needs you group (R5.34) lists
  every task in Needs you, every Waiting or On hold task that waits on the owner (R5.34a), and every task in Failed, then every open decision (R5.25), and reads
  `Nothing needs you.` when none waits. `check` finds a Needs you group that
  differs from the generated set.
The At a glance block itself is specified in §5.6 (R5.33 to R5.35).

- **R5.8** — Tiles show the count of each status that has at least one task,
  in the order of §6.1, computed from the registry.
- **R5.8a** — A tile's label names what it counts: `tasks <status in lower
  case>`, for example `123` over `tasks live`, `1 task running` in the singular
  (the label reads `task running`). Verified by `tiles_say_tasks`.
- **R5.9** — The full-progress artifact embeds the registry as
  `<script type="application/json" id="task-registry">`, the only JSON
  script it contains. The only other script allowed in any artifact is the
  template's own theme-toggle and contents script, byte-identical to the
  template.

### 5.3 Design

- **R5.10** — Every artifact includes `templates/project-artifact.css`
  unchanged, plus one token block: `docs/artifacts/design.css` when the
  manifest says `design.css`, else `design/default-design.css`.
- **R5.11** — A token block defines every token of the contract in
  `design/DESIGN.md`, light values on `:root`, dark values under both
  `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`
  and `:root[data-theme="dark"]`.
- **R5.12** — A project's own design is found by the `feature-artifact-new` or
  `full-progress-artifact-new` skill, in this order: design-token files,
  Tailwind or theme configuration, CSS custom properties in the app, the live
  site if the project names one. The skill shows the owner what it found and
  writes `design.css` only after the owner agrees; otherwise the default.
- **R5.13** — Artifacts work in light and dark, and at 360 px wide with a
  16 px side gutter and no sideways page scroll; tables scroll inside their
  own box.

### 5.4 Decisions

A feature artifact shows the owner's choices between options (designs,
approaches, names) so that what the owner was offered, what was recommended and
what was chosen stay visible. They are kept in `content/<key>/decisions.json`
and drawn by the renderer; they are never written as a content section.

```json
{"decisions": [
  {"id": "D1", "question": "Which layout for the checkout page?", "asked": "2026-10-10",
   "status": "decided",
   "options": [
     {"label": "Single page", "summary": "One scroll, all fields.", "recommended": true,
      "preview": "<pre>...</pre>"},
     {"label": "Three steps", "summary": "Address, delivery, payment."}],
   "chosen": "Single page", "decided": "2026-10-10",
   "owner_words": "single page, fewer clicks", "task": "AR9"}]}
```

**Data**

- **R5.14** — A feature artifact MAY hold `content/<key>/decisions.json`: an
  object with one key, `decisions`, a list of decision objects. A decision has
  `id`, `question` (1 to 200 characters), `asked` (a date, `YYYY-MM-DD`),
  `status`, `options`, `chosen` and `decided`, and optionally `owner_words`
  (the owner's own words, verbatim), `task` and `replaces`. An option has
  `label` (1 to 60 characters), `summary` (1 to 400) and optionally
  `recommended` (true or false), `preview` and `image`. Other fields are
  refused. The full-progress artifact has no `decisions.json`. The file is part
  of the artifact's content: `export-content` and `edit-content` carry it, and
  the script validates it.
- **R5.15** — Decision IDs are `D1`, `D2`, ... in file order, oldest first,
  with no gap; an ID is never reused and a decision is never removed.
  `edit-content` refuses an edit that removes a decision or changes the status,
  choice or date of a decided one. A changed mind is a new decision that names
  the one it replaces (R5.18).
- **R5.16** — A decision has 2 to 6 options with unique labels (compared
  without case); a yes/no question lists Yes and No as its options. At most one
  option is `recommended`. `status` is `decided` or `open`. A `decided`
  decision has `chosen` equal to one option's label and `decided` a date not
  before `asked`. An `open` decision has `chosen` and `decided` null and no
  `owner_words`.
- **R5.17** — `preview` is a small HTML fragment of at most 4000 characters
  with no `<script>`, `<style>`, `<iframe>`, form, `on*` attribute, `id`, script
  URL or external URL (`http:`, `https:` or `//`); an inline `style` attribute
  may not use `url()`, `@import` or fixed positions; a `data:` URL must be a
  base64 image. `image` is `assets/<file>` under the artifact's content folder:
  the file exists, is a png, jpg, gif or webp, and is at most 300 KB; the
  renderer embeds it as a `data:` URL. An option has a preview or an image, not
  both.
- **R5.18** — `replaces` names an existing earlier decision of the same
  artifact. `task` is a task ID that exists in the registry.
- **R5.19** — A content file whose `<!-- title: -->` is `Decisions` is refused
  (R4.10 applies to fragments in general); decisions are drawn only from
  `decisions.json`.

**Rendering**

- **R5.20** — When `decisions.json` has any decision, the renderer draws a
  generated section titled `Decisions` just before `History`, numbered with the
  other sections (R5.2). Decisions are listed newest first (highest ID first).
  A feature artifact with no decision has no such section.
- **R5.21** — Each decision shows its ID and question, and its options side by
  side as cards: one column at phone width (R5.13), several where there is
  room. Each card shows the label, the summary and the preview or image, all in
  full.
- **R5.22** — In a decided decision the chosen card is marked: an accent
  border, a chip `Chosen by the owner · DD Mon` (the `decided` date) and, when
  given, the owner's words as a quote. Every other card is shown in full but
  muted, with a chip `Not chosen`. The recommended option carries a
  `Recommended` tag whether or not it was chosen.
- **R5.23** — An open decision has a `Needs you` chip on its question and no
  chosen card; its options carry no `Not chosen` chip. A replaced decision (one
  that a later decision names in `replaces`) is collapsed in a closed
  `<details>` whose summary reads `Replaced by Dn`, and has no `Needs you`
  chip.
- **R5.24** — Colour comes only from the design tokens (R5.10); the structure
  stylesheet holds the section's layout. The section adds no script (R5.9) and
  is part of the render, so INV-3 covers it.

**Where decisions surface**

- **R5.25** — The Needs you group (R5.7, R5.34) also lists every open,
  unreplaced decision after the tasks, as `<ID> <question>`; it reads
  `Nothing needs you.` only when no task and no decision waits. In the
  full-progress artifact's section 1 a feature's line ends with `n decisions
  open.` (`1 decision open.`) when it has any.
- **R5.26** — `check` warns, without failing, for an open, unreplaced decision
  whose `task` is not a task of that feature in Needs you, or, when it names no
  task, when the feature has no task in Needs you.
### 5.5 Standalone files, the publish copy and links

claude.ai allows 200 artifact publishes per account per day, and every
republish counts. Only the full-progress artifact is published; a feature
artifact is a file in the repository that anyone with a checkout opens by
double-click.

**The feature file**

- **R5.27** — A feature artifact's rendered file is a complete HTML document:
  it begins with `<!doctype html>` and has `<html lang="en">`, a `<head>` and a
  `<body>`. The `<head>` holds `<meta charset="utf-8">`, a viewport meta
  (`width=device-width, initial-scale=1`), the `<title>` (R5.1), the
  `artifact-kind` meta, the fonts link and the three `<style>` blocks of
  R5.10; the body holds the page and the template's own script (R5.9). Verified
  by `feature_artifact_is_a_standalone_document` and `check_r527_standalone_document`.
- **R5.28** — That document needs nothing but a browser. The structure
  stylesheet and the token block (R5.10, R5.11) are inlined in `<style>`
  elements; the only `<link>` elements are the preconnect and stylesheet links
  to Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) that the token
  block's font URL gives; no `<script src>`, no other stylesheet and no image or
  font file of the record is referenced. It looks the same in light and dark as
  it did as a claude.ai artifact: both themes' tokens are present (R5.11) and the
  theme-toggle script is the template's own (R5.9). Verified by
  `feature_artifact_needs_no_host` and `check_r528_no_external_resources`.
- **R5.29** — The full-progress artifact's rendered file stays a fragment
  beginning with `<title>`, with no `<html>`, `<head>` or `<body>`, as the
  Artifact tool expects. Verified by `full_progress_is_a_fragment_beginning_with_title`
  and `check_r529_full_progress_fragment`.

**Links to the feature files**

- **R5.30** — In the committed full-progress file, section 1 and every task's
  Item link to a feature artifact by its file name relative to the file,
  `feature-<slug>.html` (a `href` with no scheme and no folder), so the links
  work when the file is opened from a checkout. Every task of a feature has this
  link; a project task has none. Verified by `full_progress_links_are_relative`
  and `check_r530_relative_links`.
- **R5.31** — `pending` hands the session a separate publish copy: the same
  render with the same stamp, written to `.claude/artifacts-publish/<file>` in
  the session's repository (git-ignored, R10.2). A page on claude.ai cannot open
  a `file:` link, so in the publish copy each feature artifact in section 1 is
  named as text with a "Copy link" button (`<button class="copy-link">`) that
  copies its address to paste into the browser's address bar; the address is an
  absolute `file:///` URL built from the repository root on this machine:
  `file:///` plus the absolute path with forward slashes, each segment
  percent-encoded (a space is `%20`), for example
  `file:///C:/GitHub/dev-standards/docs/artifacts/feature-x.html`.
  The target is the feature file in `docs/artifacts/` of the working tree. The address
  is shown as selectable text (`<code class="local-path">`, hidden until then)
  only when the clipboard refuses. The publish copy has no link to a feature
  file anywhere: its checklist rows carry none, and only section 1 has the
  buttons, one per feature. The publish copy is outside the record. Verified by
  `publish_copy_has_file_links`, `publish_copy_path_encoding`,
  `publish_copy_with_partial_links_keeps_relative_for_the_rest` and
  `test_pending_and_mark_published`.
- **R5.32** — `mark-published` records the SHA-256 of the committed render, not
  of the publish copy (R4.3), so writing a publish copy never makes the record
  look stale: `pending` compares the committed file with `published_sha256`.
  Verified by `test_pending_and_mark_published`.

### 5.6 At a glance, notes and the feature table

- **R5.33** — Section 0 holds, right after the lede and before the tiles, an
  *At a glance* block generated from the registry: `<div class="at-a-glance">`
  with one `<details class="glance-group" data-glance="<kind>">` per kind (a
  collapsible group, R6.13), a `glance-label` and a list of items one per line. An item is the task ID
  (`<span class="task-id">`), the item text and, for an open status, the
  Expected (and its `expected_basis`, R6.10). The block is the same on a feature
  artifact (its own tasks and decisions) and on the full-progress artifact (all
  tasks; decisions as in R5.25, which the full-progress artifact has none of),
  and is deterministic (R7.4).
- **R5.34** — The groups, in this order, each omitted when empty except the
  first: `you` *Needs you* (tasks in Needs you, then Waiting or On hold tasks
  that wait on the owner, R5.34a, then Failed, then open decisions
  as in R5.25); `running` *Running now* (Running tasks, soonest Expected first);
  `built` *Built, not released* (Built, newest first); `waiting` *Waiting for
  other work* (Waiting, then On hold, except those that wait on the owner); `live` *Live in the last 24 hours* (Live tasks
  whose `changed` is within 24 hours of the stamp, newest first, at most 8, then
  an item `and N more`). To do tasks are not listed. A group in a feature
  artifact never names a task of another owner.
- **R5.34a** — Who a Waiting or On hold task waits on is its optional field
  `waits_on`, `owner` or `work`; absent means `work`, so a record without the
  field groups as before the split, except that the group is now named *Waiting
  for other work*. `task-add` and `set-task-status` take `--waits-on owner|work`
  (`--waits-on ""` clears it on `set-task-status`); the field belongs to a Waiting
  or On hold row only: it is dropped when the status becomes any other and
  ignored with a warning when given for one, and `check` reports a value other
  than `owner` or `work` and the field on a row that does not wait. In the `you`
  and `waiting` groups a row of a Waiting, On hold or Needs you task reads its
  dependency first (`<span class="glance-dep">`), then the item, then the
  Expected: the dependency is the task's `expected_basis`, else the name of the
  release it `rides`, else the first sentence of its `detail`, cut to 80
  characters; the basis is then not repeated under the Expected. The count of the
  `you` group (R6.13) is the number of those tasks, Failed tasks and open
  decisions; the Needs you sentence (R5.7) and a feature's generated summary
  (R5.36) count the owner's waits as Needs you. Verified by
  `glance_splits_owner_waits_from_work_waits`, `glance_default_waits_on_work_keeps_old_grouping`,
  `glance_needs_you_count_matches_the_section`, `check_finds_a_wrong_split_or_dependency`,
  `test_waits_on_is_stored_and_defaults_to_work` and `test_check_refuses_a_bad_waits_on`.
- **R5.35** — `check` finds a group that does not list exactly the tasks (and
  decisions) of its statuses in the order of R5.34, a missing or extra group, a
  group out of order, or a wrong `and N more`.

- **R5.36** — When a feature's lede is empty, its line in the full-progress
  artifact's section 1 (R5.6) is its generated summary, from the registry:
  counts of its Running, Built, Waiting, To do, On hold and Live tasks, then
  `nothing needs you` or `N need(s) you`, as `2 running, 3 built, nothing needs
  you.` The column is never blank.
- **R5.37** — `check` warns, without failing, for a lede over 300 characters:
  keep the note to one or two sentences; the At a glance block lists the
  statuses. Records written before this requirement stay valid.

- **R5.38** — Right under the stamp, a feature artifact shows `Full Progress
  published: DD Mon HH:MM (<timezone_label>)` in `<p class="full-progress-published">`,
  the time linking to Full Progress's `url`. It comes from the manifest's
  `published_at` and `url` and is omitted before the first publish. Recording a
  publish never moves a page's stamp: `mark-published` draws the feature pages
  again keeping their stamp and their `updated`, so Full Progress, which shows
  those stamps, does not change and is not listed by `pending` again. A command
  that renders features and Full Progress draws the features first, then Full
  Progress, so its section 1 shows the stamps just written (R7.4, INV-3).
  Verified by `test_publish_does_not_loop` and `check_r538_published_line`.
- **R5.39** — The headers `Feature artifact` and `Last updated` of section 1 are
  buttons (`<button type="button" class="sort-header" data-sort="name|updated">`):
  a click sorts the rows by that column, a second click reverses the order, an
  arrow and `aria-sort` on the header show the current order. The page starts
  in Last updated, newest first (the committed order); sorting is done by the
  template's own script on the page, stores nothing and calls nothing outside
  the page, so it works in the publish copy, whose Copy link buttons (R5.31)
  keep working in any order. Verified by `check_r539_sort_headers` and
  `test_full_progress_sort_script`.

### 5.7 Releases, the release timeline and the State column

- **R5.40** — A task may be a **release**. A release row carries `"release": true`
  and may carry `"phases"`, `"risk"`; any task may carry `"rides"`. All are
  optional, so a record without them stays valid:

  ```json
  {"id": "DS51", "release": true, "expected": "10 Oct ~18:00",
   "phases": [{"name": "agents", "start": "2026-10-10T17:30+01:00", "end": "2026-10-10T17:45+01:00"},
              {"name": "merge", "start": "2026-10-10T17:54+01:00", "end": "2026-10-10T18:00+01:00"}],
   "risk": {"label": "+1 fix round", "minutes": 10}}
  ```

  A phase `name` is `agents`, `join`, `ci` or `merge` (merge and cleanup), at
  most once each; `start` and `end` are ISO times with an offset, `end` after
  `start`. `risk` is one named risk: a `label` of at most 40 characters and
  whole `minutes` of at least 1. `rides` is the ID of a release task, which must
  exist and be a release. Phases and risk belong to a release row only. The
  commands set them: `task-add` and `set-task-status` take `--release`,
  `--phase NAME=HH:MM-HH:MM` (today, in the project's zone) or
  `--phase "NAME=DD Mon HH:MM-DD Mon HH:MM"`, repeatable and replacing all
  phases, `--phase ""` to clear them, `--risk "LABEL=MINUTES"` (`--risk ""`
  clears it) and `--rides ID` (`--rides ""` clears it). A command refuses a
  `--rides` that is not a release, and phases or risk on a task that is not a
  release. `check` reports the same (R5.40). Verified by `test_release_flags_store_the_fields`,
  `test_release_refusals` and the release fixtures of `test_check_fixtures`.
- **R5.41** — A release's Expected is the sum of its phases: when a release in
  an open status has phases, its Expected (before any `; note`) must equal
  `DD Mon ~HH:MM`, the end of its last phase to the minute. A writing command
  that would leave a mismatch is refused, and `check` reports one (R5.41). There
  is no silent padding: a margin for what may go wrong is named as the
  release's `risk`, not added to Expected. Verified by `test_release_expected_is_the_end_of_the_last_phase`,
  `rule_file_carries_the_release_rule` and the R5.41 fixture of `test_check_fixtures`.
- **R5.42** — Section 0 of the full-progress artifact holds, after the status key
  and before the checklist, the **release timeline** whenever at least one
  release is open (Running, Waiting, To do, Needs you or On hold) and nothing
  otherwise: `<figure class="release-timeline">` with a `<figcaption>` reading
  `Next releases (<timezone_label>)`, an inline `<svg>` and a legend. It has one
  row per open release, ordered by Expected (ties by ID); each label is
  `<ID> · <item>` and, below it, the IDs of the tasks whose `rides` names it.
  Releases due within a day (a time in Expected, or phases, ending no more than
  24 hours after the stamp, whatever the calendar date; R5.42a) share a
  time axis drawn to scale: from the earliest phase start, Expected or stamp to
  the latest Expected or worst case, floored and ceiled to the half hour, with a
  tick every 30 minutes (every hour beyond 4 hours). A release whose Expected is
  more than 24 hours after the stamp, or has no time, sits after an axis break in one slot per day, as
  an outline diamond with the day. A release without phases is a filled diamond at
  its Expected only. The figure is deterministic (R7.4): the "now" mark is the
  render stamp, never the wall clock. `check` finds a missing, extra or misplaced
  timeline and a wrong caption (R5.42). Verified by `timeline_rows_axis_and_break`,
  `timeline_axis_is_to_scale_from_the_earliest_phase`, `timeline_is_absent_without_open_releases`,
  `timeline_without_phases_is_a_diamond_at_expected` and `check_finds_a_wrong_timeline`.
- **R5.42a** — The time axis may cross midnight: a tick at midnight, and the
  first tick after it, carry the date (`12 Oct 00:00`), and the "now" mark is
  drawn wherever the stamp falls on the axis. A release expected at `00:05` the
  next day, drawn at `23:57`, keeps its phase bars and its Expected diamond on
  the axis; it never falls back to a bare day slot. `check` finds a timed
  release within 24 hours drawn in a day slot (R5.42a). Verified by
  `timeline_crosses_midnight` and `check_finds_a_timed_release_in_a_day_slot`.
- **R5.42b** — The release timeline carries a second strip, **Other work (no
  release)**, below the release rows and in the same figure, so it shares the
  axis, the axis break and the phone-width scroll. It has one row per task that
  is Running, Waiting, Needs you or To do, carries `no_release` (R5.47a) and has
  an Expected today or tomorrow (an overdue one stays); a Built, Live, Failed or
  On hold task is not shown. Each row is labelled `<ID> · <item>` (cut like the
  release rows), and a task due within 24 hours is a bar from its start (the
  task's optional `started` ISO time, R5.48, else the stamp) to its Expected, coloured
  by status with the status key's colours, with the Expected and its
  `expected_basis` as the label under it; a later or untimed Expected is an
  outline diamond in its day slot. A row past its Expected is outlined in the
  failed colour. Rows are ordered by Expected (ties by ID). With no open
  release the figure still appears when the strip has a row. The caption stays
  `Next releases (<timezone_label>)`. Verified by
  `other_work_strip_renders_beside_the_release_rows` and
  `other_work_strip_alone_and_overdue`.
- **R5.43** — The look of the timeline uses the design tokens only, through
  classes of the structure stylesheet: phases are bars in `--running-mark`
  (agents), `--signal` (join), `--live` (PR CI) and `--ink` (merge and cleanup);
  Expected is a filled diamond labelled `live ~HH:MM`; a risk is a thin
  `--rule-strong` extension from Expected to Expected plus its minutes ending in
  an outline diamond labelled `LABEL → worst ~HH:MM`; a `--failed` line labelled
  `now HH:MM` marks the stamp when it falls inside today's axis. The `<svg>` has
  `role="img"` and an `aria-label` stating each release's Expected and worst
  case; the legend under it names the four colours and says Expected is the sum
  of the phases. At phone width the figure scrolls inside its own
  `div.timeline-scroll` (the `<svg>` has a `min-width`), so the page does not. The drawing is never scaled up: its `viewBox` is at least 960 units wide and the `<svg>` carries a `max-width` equal to that width, so text is drawn at its own size on a wide page (`timeline_is_never_scaled_up`).
  Both themes follow from the tokens. Verified by `timeline_risk_now_and_accessibility`,
  `timeline_is_deterministic_and_uses_the_stamp_for_now`, `timeline_is_never_scaled_up` and `timeline_css_uses_tokens`.
- **R5.44** — The feature table of section 1 has a `State` column right after
  `Tasks`. A feature with no task in an open status (any status but Live) and no
  open decision (R5.23) shows one `Complete` chip (`status-live`); otherwise one
  chip per status with its count, as `2 Running`, in the order Running, Needs
  you, Failed, Waiting, Built, To do, On hold, then `N open decision(s)` in a
  Needs you chip. `check` finds a State that differs from the registry
  (R5.44). Verified by `state_column_counts`, `check_state_column` and
  `test_state_column_counts_in_the_record`.

### 5.8 Release numbers and items grouped by release

- **R5.45** — A release is numbered. A release row carries `"release": <n>`, a
  positive integer unique among all releases of the registry, Live ones
  included; the release is named `RELEASE-<n>` wherever it is shown. `--release`
  on `task-add` or `set-task-status` gives a task that is not yet a release the
  next number (the highest number in the registry plus one, 1 when none) and
  leaves an existing number alone; numbers are never reused or changed, like task
  IDs (R4.5). `--rides` takes a release's task ID or its name `RELEASE-<n>`;
  `rides` always stores the task ID. An older record's `"release": true` rows
  are numbered by the migration (§4.7) in order of `changed`, oldest first, ties
  by ID; `check` reports a `release` that is not a positive integer, a repeated
  number, and `true` left after migration (R5.45). Every release row's Item, in
  the checklists, the At a glance block and the timeline, starts with a
  `<span class="release-name">RELEASE-<n></span>` before its text; the timeline
  label reads `RELEASE-<n> · <item>` (replacing `<ID> · <item>` of R5.42) and
  the task ID stays in the row's ID cell. When the item itself already starts with
  its own `RELEASE-<n>` (optionally followed by `:` or ` · `), that lead is left
  out of the item text shown, so the number appears once (`RELEASE-55: ops` shows
  as `RELEASE-55 · ops` in the timeline); the registry keeps the item as written,
  and `check` compares the item as shown. Verified by `release_number_is_shown_once`,
  `test_release_numbers_are_assigned_and_never_reused`,
  `test_rides_accepts_the_release_name`, `test_migration_numbers_old_releases`
  and the R5.45 fixtures of `test_check_fixtures`.
- **R5.46** — The full-progress checklist is grouped by release, in this order,
  each group omitted when empty:
  1. one group per open release (R5.42), ordered by Expected, ties by number,
     headed `RELEASE-<n> · live ~HH:MM` (the Expected's time; `live DD Mon` when
     it has no time), with ` · worst ~HH:MM` added when the release has a risk;
     its rows are the release row first, then every task riding it in the order
     of R6.2 (Running, Waiting, To do, Needs you, Failed, On hold, Built, Live),
     ties by ID;
  2. `Not in a release yet`: Running, Waiting and To do tasks that ride no open
     release, earliest Expected first;
  3. `Needs you, failed or on hold`, then `Live or built`, as in R6.2, holding
     only tasks that ride no open release.
  A task appears in exactly one group. In `Live or built` (and `Earlier`), and
  in a feature artifact's checklist, a row that rides a release shows
  `<span class="release-name">RELEASE-<n></span>` in a muted line under its
  Item, so what shipped in each release stays visible. Feature artifacts keep
  the groups of R6.2. `check` finds a row in the wrong group or order, a missing
  or extra group, a wrong heading and a missing release line (R5.46). The
  look uses the tokens only: a group heading like R6.2's, in the `<summary>` of R6.12, with the release
  name in `--ink`; `.release-name` is the mono face in `--signal`. Verified by
  `full_progress_groups_by_release`, `release_group_heading_with_risk`,
  `rows_show_the_release_they_rode` and `check_finds_a_row_in_the_wrong_release_group`.
- **R5.47** — Every task in Running or Built that is not itself a release rides
  a release (`rides`, R5.40). A writing command refuses a change that leaves a
  Running or Built task without one: `task-add --status Running` and
  `set-task-status ID Running|Built` take `--rides` in the same call when the
  task has none. `check` reports such a task (R5.47); an older record's
  existing findings do not freeze writing commands (R7.1a). The rule file says
  so in one line. Verified by `test_running_and_built_must_ride_a_release`,
  `rule_file_carries_the_rides_rule` and the R5.47 fixture of `test_check_fixtures`.
- **R5.47a** — A task that ships nothing (a publish, a study, a cleanup) may say
  so: `"no_release": "<reason>"`, at most 80 characters, set by `task-add` or
  `set-task-status` with `--no-release REASON` (`--no-release ""` clears it). Such
  a task may be Running, and any other open status, without riding a release;
  it is never Built (finished, it goes Live), never a release and never rides
  one: a command refuses `--no-release` together with `--release` or `--rides`,
  and refuses Built on a task that carries it. In Full Progress it sits in `Not
  in a release yet` with a muted line `ships nothing: <reason>`. `check` reports
  the same (R5.47a). Verified by `test_no_release_tasks_may_run_without_a_release`,
  `test_no_release_refusals` and `no_release_line_in_full_progress`.

- **R5.48** — A task row may carry `started`, an ISO time with offset: when work
  on it began. `set-task-status` (and `task-add`) take `--started "DD Mon ~HH:MM"`
  or `--started HH:MM` (today), read in the project's zone exactly as `--expected`
  and `--phase` are, and store the ISO time with that zone's offset;
  `--started ""` clears it. A start that does not parse, or that is not before
  the Expected of an open row, is refused and nothing is written, and the same
  holds when a later `--expected` would fall before it. A task that moves to
  Running with no `started` gets the current time (unless its Expected has
  already passed); a start already set is kept. The timeline's Other work strip
  draws a bar from `started` (R5.42b); the fingerprint of Full Progress includes
  it (R9.6). `check` reports an open row whose `started` is not before its
  Expected (R5.48). Verified by `test_started_is_stored_validated_and_cleared`,
  `test_started_is_set_when_a_task_first_runs` and `other_work_bar_starts_at_started`.
- **R5.49** — `Dropped` closes a task whose work was folded into another task
  (two releases merged into one) or is no longer wanted, without claiming it
  shipped (Live), broke (Failed) or waits (On hold). It is terminal and not
  open: its Expected is the date it was dropped, a dropped release is not in
  `open_releases` and has no bar on the timeline, and no task rides it.
  `set-task-status ID Dropped` needs `--into ID|RELEASE-n` (stored as
  `dropped_into`, another task; for a release, another release) or `--reason TEXT`
  (`dropped_reason`, at most 80 characters); a release needs `--into`. The fields
  belong to a Dropped row and are removed when it is reopened. Full Progress
  and feature artifacts list the row under `Live or built` with a muted line
  `dropped: folded into RELEASE-n` (`dropped: <reason>` without `--into`), the
  feature's History records the same line, and `check` reports a Dropped row
  that lacks its reason, a release dropped without a target, a target that is
  not a task (or not a release), a task that still rides a dropped release and a
  line that differs (R5.49). Verified by `test_dropped_release_is_closed_truthfully`
  and `dropped_release_is_closed_history`.

- **R5.50** — Section 1 of Full Progress is two collapsible folds, each the
  page's own `<details class="status-fold feature-group">` with its title in a
  `<summary><strong>` and a count: `Feature artifacts in progress (n)` first
  (`data-group="features-progress"`, rendered open) holding the features whose
  State is not `Complete` (R5.44), then `Complete feature artifacts (n)`
  (`data-group="features-complete"`, rendered closed) holding the features whose
  State is `Complete`. Each fold holds the R5.6 table with its sort buttons
  (R5.39) and links, sorting on its own; a fold with no feature holds no table
  and one line, `No feature artifacts in progress.` or `No feature artifacts are
  complete yet.` (`<p class="feature-none">`). The folds are not checklist
  groups (R6.12). `check` reports folds that are missing, out of order, open or
  closed against this rule, a title whose count differs from its rows, a
  feature in the wrong fold, and an empty fold with a table or without its
  line. Verified by `feature_artifacts_split_mixed_states`,
  `feature_artifacts_split_all_complete`, `feature_artifacts_split_none_complete`
  and `feature_artifacts_split_checker_finds_faults`.

---

## 6. Statuses and the checklist

### 6.1 Statuses

| Status | Meaning |
|---|---|
| Live | Released or in production. |
| Built | Finished, but not merged or released yet. |
| Running | Being worked on now. |
| Needs you | Waits on the owner. |
| Waiting | Waits on something else: CI, a dependency, a time. |
| To do | Planned, not started. |
| On hold | Paused by decision. |
| Failed | Broke; needs a fix or a decision. |
| Dropped | Closed without shipping: folded into another task or no longer wanted (R5.49). |

- **R6.1** — Only these nine statuses exist; each has a fixed chip class
  `status-<lowercase-hyphenated>` styled by the structure stylesheet.

### 6.2 Groups and order

- **R6.2** — Checklist rows are grouped, in this order: `Running now and next`
  (Running, Waiting, To do — earliest expected first), `Needs you, failed or
  on hold` (Needs you, Failed, On hold), `Live or built` (newest `changed`
  first; Dropped rows with them, R5.49). An empty group is omitted. The full-progress artifact groups by
  release instead (R5.46); these groups still order the rows inside it.
- **R6.3** — In the full-progress artifact, `Live` rows whose `changed` is more
  than 14 days old fold into a closed `<details>` titled `Earlier`. `Built` rows
  never fold, however old: unreleased work must not be hidden. Verified by
  `earlier_fold_older_than_14_days` and `built_rows_never_fold`.

### 6.3 Columns

- **R6.4** — A feature artifact's checklist columns are
  `Status | Item | Detail | Expected (<timezone_label>)`; the full-progress
  artifact's are `Status | Item | App / service | Detail | Expected
  (<timezone_label>)`.
- **R6.5** — In the full-progress artifact a feature task's Item links to its
  feature artifact's file (R5.30); every feature task appears there.

### 6.4 Expected

- **R6.6** — On a Running, Waiting, To do, Needs you or On hold row, Expected is
  `DD Mon` or `DD Mon ~HH:MM` (a time for work due within a day) in the
  owner's zone, optionally followed by `; ` and a short note. Words such as
  `today`, `soon`, `tomorrow` or `next` alone fail — a relative word goes stale
  without anyone changing it.
- **R6.7** — On a Live or Built row, Expected is the date it happened.
- **R6.8** — `set-task-status` to Live or Built sets Expected to the current
  date when no `--expected` is given.

### 6.5 The retired status Done

- **R6.9** — `Done`, a status of 1.0.0, is retired: it meant "finished" even
  when merging, releasing or deploying was still to come, and `Built` and `Live`
  say which. `set-task-status` and `task-add` accept `Done` as a deprecated
  alias, store `Built` and print a note. A record that still holds `Done` (a
  task status, or `merged_status`) is read as `Built`, the next writing command
  rewrites it as `Built`, and `check` reports the old values as a note, not a
  finding. Verified by `test_done_is_a_deprecated_alias_of_built` and
  `test_old_done_records_migrate_to_built`.

### 6.6 The basis of Expected

- **R6.10** — A task on an open status (Running, Waiting, To do, Needs you, On
  hold) may carry `expected_basis`, a plain-text line of at most 80 characters
  saying what sets the estimate: what it waits on and how long (for example
  `agent slot ~01:30, ~1.5 h`). `task-add` and `set-task-status` take it as
  `--basis TEXT`; `--basis ""` clears it on `set-task-status`; the field is
  absent when there is none. A task whose status becomes Live, Built or Failed
  loses it, as Expected itself is replaced (R6.7, R6.8); `--basis` given for such
  a status is ignored with a warning. `check` reports an empty or longer
  basis, and a basis on a row that is not open (R6.10). Verified by
  `test_basis_is_stored`, `test_basis_dropped_when_closed`, `test_basis_over_80_refused` and the basis
  fixtures of `test_check_fixtures`.
- **R6.11** — Both artifact kinds show the basis in a small, muted line under the
  Expected value (`span.expected-basis`, design tokens only, wrapping at phone
  width), on open rows only; the checklist still equals the registry (INV-1).
  The rule file says: when you give an Expected time, give its basis too (what
  it waits on and how long) (R10.3), and the skills that give one say so.
  Verified by `render_shows_the_expected_basis`, `check_expected_basis_matches_registry`,
  `basis_style_uses_tokens_and_wraps` and `rule_file_carries_the_basis_rule`.

### 6.7 Collapsible groups

- **R6.12** — Every checklist group, in both artifact kinds (each open release
  group, `Not in a release yet`, `Needs you, failed or on hold`, `Live or
  built`, and a feature artifact's status groups), is a native
  `<details class="status-fold" data-group="<key>">` whose first child is a
  `<summary>` holding the group heading in `<strong>` (and a muted
  `span.fold-count`), followed by the group's `table.status-checklist`; there is
  no group heading row and no script. The group `built` (`Live or built`) is
  rendered closed, without the `open` attribute, every time; every other group
  is rendered `open`. The `Earlier` fold of R6.3 stays closed and sits inside
  the `built` group, after its table. A closed `Live or built` summary shows how
  many `Built` (unreleased) and `Live` rows it holds, so collapsing it does not
  hide unreleased work (R6.3). The structure stylesheet gives the summary a
  chevron that turns when open, a tap target of at least 2.75rem, a visible
  `:focus-visible` outline and no reliance on colour alone; the summary is
  keyboard operable (Enter or Space) by being a `<summary>`; printing shows the
  groups expanded where the browser supports `::details-content`. Columns stay
  aligned across groups with a `<colgroup>` and a fixed table layout. `check`
  reports a group that is not such a `<details>`, a heading kept as a table row,
  a `Live or built` group that is open, another group that is closed, and an
  `Earlier` fold outside `Live or built` (R6.12). Verified by
  `groups_are_collapsible_details`, `live_or_built_starts_closed`,
  `check_finds_a_wrong_open_state` and `collapsible_group_style_is_accessible`.

- **R6.13** — Each group of the At a glance block (R5.33) is the same fold as a
  checklist group: a native `<details class="glance-group glance-<kind>"
  data-glance="<kind>">` whose first child is a `<summary>` holding
  `span.glance-label` (the group label) and a muted `span.fold-count` with the
  number of items the group lists, as `1 task` or `3 tasks` (tasks, open
  decisions and the `and N more` of `live` all count), followed by the list or,
  for an empty `you` group, the sentence `Nothing needs you.`. The groups `built`
  and `live` (done work) are rendered closed, without `open`; `you`, `running`
  and `waiting` are rendered `open`, and `you` is always shown, open, with its
  sentence when empty. The summary is styled by the rules of R6.12 (chevron,
  tap target of at least 2.75rem, `:focus-visible` outline, no script); the
  coloured left bar of each group stays; the groups stack at every width, so a
  phone never scrolls sideways. `check` reports a glance group that is not such
  a `<details>`, one in the wrong open state and one whose count is not the
  number of items it lists. Verified by `glance_groups_are_collapsible_details`,
  `check_finds_a_wrong_glance_state` and `at_a_glance_css_uses_tokens_and_fits_a_phone`.

- **R6.14** — An open row (Running, Waiting, To do, Needs you, On hold) whose
  Expected time is in the past is flagged (DL-63). A date alone (`DD Mon`)
  ends at 23:59 of that day in the project's zone. `check` prints one warning
  per such row, in `--json` under `warnings`, naming the task and its
  Expected; it is a warning and not a finding, so a writing command is never
  refused for it. The end-of-turn hook blocks on it (R8.19). Verified by
  `test_check_flags_open_rows_past_their_expected_time`.

---

## 7. Commands

All commands run as `python <plugin>/scripts/project_artifacts.py <command>`
from anywhere inside the project's repository, read `docs/artifacts/` from the
the working tree (§4.6), and exit 0 on success, 1 on findings or a refused
action, 2 on an unreadable record (exit codes 3 and 4 are no longer used).
`--json` prints a machine-readable result. Every writing command writes files
and stops (R4.13); it accepts `--no-push` and `--push` for compatibility, and
they do nothing (R4.17).

| Command | Does |
|---|---|
| `init --project NAME [--timezone IANA] [--label L] [--windows-timezone ID] [--default-branch B]` | Creates the manifest, an empty registry and the full-progress artifact's content. Refuses if a manifest exists. Zone defaults to the machine's. |
| `feature-new --key K --title NAME --prefix P --apps a,b [--hero TEXT] [--force] [init flags]` | Adds a feature artifact (content folder with `meta.json`, a section `01-what-and-why.html` stub and a first History row; its manifest entry has no `url`). Runs `init` first, with the same `init` flags, when there is no manifest; `--project` is then required. |
| `task-add --owner K\|project --item TEXT --detail TEXT --expected TEXT [--basis TEXT] [--app A] [--status S] [--prefix P] [--release] [--phase NAME=HH:MM-HH:MM]... [--risk LABEL=MINUTES] [--rides ID] [--waits-on owner\|work]` | Adds a task with the next free number; prints its ID. For `--owner project`, `--prefix` picks one of `project_prefixes`, and a new prefix not used by any feature is registered. |
| `set-task-status ID STATUS [--item TEXT] [--detail TEXT] [--expected TEXT] [--basis TEXT] [--history TEXT] [--release] [--phase NAME=HH:MM-HH:MM]... [--risk LABEL=MINUTES] [--rides ID] [--waits-on owner\|work]` | Changes one task; adds a History row to its feature artifact when `--history` is given. `--item TEXT` corrects the task's title (1 to 80 characters, as R4.8) and records `<ID> item changed from "<old>" to "<new>"` in the History of a feature task (a project task has no History; a warning says so). Verified by `test_set_task_status_item_corrects_title`. |
| `export-content KEY --to DIR` | Copies the artifact's content files from the record to DIR for editing, `decisions.json` and its `assets/` folder included. |
| `edit-content KEY --from DIR` | Replaces the artifact's content files in the record with those in DIR validates, renders and writes the files. It refuses an edit that removes a decision or changes the choice of a decided one (R5.15). |
| `design set FILE\|default` | Validates FILE against the token contract (R5.11), copies it to `docs/artifacts/design.css`, sets manifest `design` and renders; `default` removes it. |
| `move-record NEW_DIR [--yes]` | Moves the record folder under `docs/` and writes `record_dir` (R4.37, R4.38). Without `--yes` it prints the plan and writes nothing. |
| `retire KEY [--yes]` | Removes a finished feature artifact (R4.33) and its content, keeping its tasks, its decisions and a line in the manifest's `retired_features` (§4.10). Without `--yes` it lists what it would delete and writes nothing (R4.36). |
| `render [--all]` | Renders every artifact whose output would change (committed renders, with relative links). It is the migration of an older record (R8.14). |
| `check [--record PATH]` | The conformance checks of §14; lists findings with their requirement ID, then notes (including retired pages, R4.22) and any warnings (R5.26, R5.37), which do not change the exit code. |
| `pending` | Lists the full-progress artifact when the hash of its committed render differs from `published_sha256` (a feature artifact is never listed, R9.5), and queued events. When it lists Full Progress it writes the publish copy (R5.31). Exit 1 when anything is listed. `--refresh` lists Full Progress even when unchanged (R9.8). `--json` prints `{"artifacts": [{"key", "kind", "title", "file", "path", "url", "reason", "copy_sha256", "copy_written_at"}], "queue": [events]}`; `path` is the absolute path of the publish copy to publish. It also lists the retired pages (R4.22): `--json` adds `"retired": [{"key", "title", "url", "retired"}]`, and they never change the exit code. |
| `mark-published KEY --url URL` | Records the URL and the hash of the committed render (R5.32). Refuses a feature artifact (R9.5). |
| `mark-deleted [KEY] --url URL [--gone]` | Records that the owner confirmed and the session deleted a retired page (or that it no longer exists): moves it to `deleted` (R4.21). |
| `worktree` | Prints the record directory, `<repo root>/docs/artifacts` (R4.24). |
| `migrate` | Copies the old record worktree's `docs/artifacts/` into the working tree when it is newer, and prints the one-line note only when it copies; otherwise prints nothing. Idempotent; exit 0 (R4.24). |
| `queue list\|clear [--id ID]` | Shows or removes queued events. |
| `push` | Removed in 1.8.0: exits 1 with the message of R4.28. |
| `commit [--retry] [--message M]` | Removed in 1.8.0: exits 1 with the message of R4.28. |

- **R7.1** — Every writing command validates the record before and after the
  change and writes nothing when the change adds a finding: one the record
  did not have before. A finding is identified by its requirement ID and its
  file, never by its message text, and findings are counted, so a second
  finding of the same requirement in the same file is an added one. The
  command prints the added findings and writes nothing.
- **R7.1a** — A writing command MUST NOT refuse a change because of findings
  the record already had. Some of them, such as two feature artifacts each
  holding a hand-written section titled Decisions (R5.19), clear only by
  edits, one artifact at a time. The command prints
  `N earlier findings remain; run check`. An artifact whose content is already
  invalid is not rendered by another change and keeps its file, and the
  command says so; `edit-content` of that artifact refuses content that is
  still invalid and, once the content is valid, renders it. `render` skips such
  an artifact the same way, and Full Progress shows a feature whose content is
  invalid from what can be read of it.
- **R7.2** — `set-task-status` updates the registry, renders the task's feature
  artifact (if any) and the full-progress artifact with a new stamp, removes
  the task's queued events, and writes the files — in one invocation.
- **R7.3** — `set-task-status` rejects a status outside §6.1 and names the
  nearest allowed status (`Merged` → `Live`).
- **R7.4** — Rendering is deterministic: the same record and the same stamp give
  byte-identical HTML.
- **R7.5** — A command that renders Full Progress draws it after the feature
  pages it draws in the same command (R5.38). Every writing command except `render` (which does this itself) also
  renders, with a new stamp, each artifact whose file differs from a fresh render
  with that file's own stamp, so a plugin upgrade that changes the templates or
  the stylesheet brings every page up to date at the next change, not only the
  pages that change names (INV-3). An artifact whose content is invalid is
  skipped as in R7.1a. A page that is already up to date keeps its stamp.
- **R7.6** — `pending` does not push or write git state: it reads the record in
  the working tree and lists, as before. Its output format is unchanged.
  Verified by `test_pending_does_not_push`.

---

## 8. Hooks

All four hooks are registered in the plugin's `hooks/hooks.json` (the
after-command hook for `Bash`, `Agent` and `Task`; the before-command hook for
`Bash` and `PowerShell`), run
`python <plugin>/scripts/hook_*.py`, and exit 0 doing nothing when the
project has no `docs/artifacts/manifest.json` in the current checkout or on
`origin/<default branch>`.

### 8.1 After-command hook (PostToolUse and PostToolUseFailure for Bash; PostToolUse for Agent and Task)

Reads the hook input; takes the task ID from the current branch name
(`^([A-Z]{2,5}[0-9]+)-`); on a matching command, appends an event to the queue
`<repo>/.claude/artifacts-queue.json` (gitignored):
`{"id", "suggested_status", "event", "command", "time"}`.

| Command (exit 0 unless noted) | Suggested status |
|---|---|
| `gh pr create` | Running |
| `gh pr ready` | Waiting |
| `gh pr merge` (not `--auto`, which only schedules) | `merged_status` |
| `scripts/delivery/ci_watch.py`, `gh run watch` with exit ≠ 0 | Failed |
| `scripts/delivery/ci_watch.py`, `gh run watch` with exit 0 | Waiting |
| a production deploy (`vercel deploy --prod`, `fly deploy`, `wrangler deploy`, `firebase deploy`) | Live |

- **R8.1** — The hook only queues; it never writes the record (INV-4). A
  command with no task ID in the branch queues nothing. (It also delivers the
  rule, R8.12, which writes only the stop state.)
- **R8.2** — The hook finishes in under 2 s and never fails the tool call: any
  error exits 0 with a one-line message on stderr.

### 8.2 End-of-turn hook (Stop)

- **R8.3** — When the queue is not empty or `pending` lists Full Progress (the
  only artifact it lists), the hook blocks the stop (`{"decision": "block",
  "reason": ...}`) with a reason that names each item and the exact commands to
  run, Full Progress's as one publish of its publish copy (R5.31) and a
  `mark-published`. It keeps blocking until Full Progress is published, so
  a status change made at any point of the turn is published once, at its end
  (R3.1).
- **R8.4** — After 3 consecutive blocks in one session with no change in what
  is pending, the hook lets the turn end and prints a `systemMessage` naming
  what is still unpublished — a session that cannot publish (no Artifact tool)
  must not loop forever.

### 8.3 Session-start hook (SessionStart)

- **R8.5** — The hook fetches the default branch, lists pull requests with
  `gh pr list --state all --json headRefName,state,mergedAt --limit 200`, and
  queues `merged_status` for every task in Running, Waiting or To do whose
  branch `<ID>-*` was merged, and `On hold` for one whose only pull request
  was closed unmerged.
- **R8.6** — When `gh` is missing or not signed in, the hook queues nothing and
  prints one `systemMessage` saying the catch-up was skipped — the catch-up is
  informational, so it fails open.
- **R8.7** — The hook prints a `systemMessage` listing queued events, if any.

### 8.4 Background work and the rule

- **R8.8** — The after-command hook records that background work started when
  the tool is `Agent`, `Task` or `Bash` and `tool_input.run_in_background` is
  true (a foreground `Agent` or `Task` call, which finishes within the turn,
  records nothing): it stamps the session's entry in
  `<repo>/.claude/artifacts-stop-state.json` (gitignored) with the time and the
  session ID. It writes that file only, never the record (INV-4), needs no task
  ID in the branch name, and does nothing in a project without a manifest. A
  foreground call of any of the three tools, or a call that failed, records
  nothing. Verified by `after_background_agent_and_bash_mark_the_session` and
  `after_foreground_calls_do_not_mark_the_session`.
- **R8.9** — In any repository that has a record manifest, the session-start
  hook prints the plugin's `rules/project-artifacts.md` text as
  `{"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
  ...}}`, alongside the `systemMessage` when there is one, every session,
  whether or not `gh` works. Without a manifest it prints nothing. It stays
  inside R8.2's rule of never failing. The same context then carries what
  R8.13 to R8.15 say. Verified by
  `start_delivers_the_rule_as_additional_context` and
  `start_delivers_the_rule_when_gh_is_missing`.
- **R8.10** — The end-of-turn hook blocks the stop when the session has
  recorded background work (R8.8) since the check was last satisfied and the
  registry has no task in Running, Waiting or Needs you; the reason says that
  work was started in the background with no Running task and to record it with
  `task-add` or `set-task-status`, then publish. Once such a task exists the
  marker is cleared. The check shares R8.4's give-up rule: after 3 consecutive
  blocks with no change it lets the turn end with a `systemMessage`. Without a
  manifest it does nothing. Verified by
  `stop_blocks_background_work_without_an_active_task`,
  `stop_allows_background_work_with_an_active_task_and_clears_the_marker` and
  `stop_background_gives_up_after_three_blocks`.
- **R8.11** — The end-of-turn hook acts on Full Progress only. An entry of
  `pending` for a feature artifact (from a script older than R9.5) is ignored:
  it neither blocks the stop nor counts towards R8.4's give-up. Verified by
  `stop_counts_only_full_progress`.

### 8.5 Upgrading a project

- **R8.12** — The after-command hook also delivers the rule, so a session that
  is already open when the plugin updates does not need a restart: on a
  `PostToolUse` of Bash, Agent or Task in a repository with a manifest, when
  this session (`session_id`) has not yet been given the current rule text, it
  prints `{"hookSpecificOutput": {"hookEventName": "PostToolUse",
  "additionalContext": ...}}` with the rule text, the context of R8.13 to R8.15
  and the line `luismc-artifacts was updated; this rule replaces earlier
  instructions about publishing feature artifacts.` It records a hash of the
  delivered text per session in `.claude/artifacts-stop-state.json` (key
  `rule:<session_id>`; the session-start hook records it too), so it prints
  once per session and again after the rule text changes. It stays inside
  R8.2's rule of never failing and writes that file only (INV-4). Verified by
  `after_delivers_the_rule_once_per_session_and_again_when_it_changes` and
  `start_records_the_delivery_so_after_stays_quiet`.
- **R8.13** — When retired pages exist (the manifest's `retired` list, plus
  feature URLs the history of `manifest.json` still shows that are neither
  retired nor deleted), the session-start and after-command contexts list them
  and tell the session to offer the owner their deletion at the start of the
  session, with the commands of R4.22. The end-of-turn hook never blocks on
  them: it prints a `systemMessage` listing them once per session (and again
  only when the list changes). Verified by
  `start_context_offers_deleting_retired_pages` and
  `stop_tells_retired_pages_once_and_does_not_block`.
- **R8.14** — When the record needs migrating, which the hooks read without
  writing (a feature entry holding `url` or `published_sha256`, a task or
  `merged_status` still `Done`, or a feature file in the old fragment form),
  both contexts say `run project_artifacts.py render now to migrate the
  record`, and the end-of-turn hook blocks the stop with that instruction as
  its reason until the record is migrated. The block shares R8.4's give-up rule:
  after 3 consecutive blocks with no change it lets the turn end with a
  `systemMessage`. The hooks never write the record (INV-4). Verified by
  `stop_blocks_while_the_record_needs_migrating`,
  `stop_migration_gives_up_after_three_blocks` and
  `test_hooks_never_write_record`.
- **R8.15** — Until the migration commit removes it (R10.6), the context of both
  hooks adds: `If .claude/rules/project-artifacts.md exists in this repo, it is
  an older copy; this rule replaces it.` Verified by
  `start_context_names_an_older_rule_copy`.

### 8.6 No push by a hook

- **R8.16** — The before-command hook does not push the record before
  `gh pr create`, `gh pr ready` or `gh pr merge`. Where it has nothing else to
  do it exits 0 and prints nothing. Verified by
  `before_command_is_silent_for_pr_commands_and_runs_nothing` in `tools/test_project_artifacts_hooks.py`.
- **R8.17** — The end-of-turn hook does not push. The publish gate and the
  background-work checks (R8.4, R8.8 to R8.10) are unchanged. Verified by
  `hooks_never_write_record` in the same file.

- **R8.18** — The hook also blocks when Full Progress has a URL and (a) its
  `published_at` is more than 60 minutes old (the hourly fail-safe, R9.8), or
  (b) a release task's `changed` stamp is later than `published_at` (a release
  task's status or phase changed since the last publish, R9.9), even though
  `pending` lists nothing. The reason names the cause and the three steps of
  R9.10. It never blocks a project that has not published Full Progress yet
  (the first publish is `pending`'s), nor when `pending` already lists it.
  The R8.4 ceiling applies. Verified by
  `stop_blocks_when_full_progress_is_over_an_hour_old`,
  `stop_blocks_when_a_release_task_changed_since_the_publish` and
  `stop_hourly_and_overdue_checks_need_a_published_record_and_respect_the_ceiling`.
- **R8.19** — The hook blocks while an open row is past its Expected time
  (R6.14), naming each row and the `set-task-status ... --expected` command
  that fixes it; the R8.4 ceiling applies. Verified by
  `stop_blocks_on_open_rows_past_their_expected_time`.

---

## 9. Publishing and recreation

- **R9.1** — The session publishes the full-progress artifact with the Artifact
  tool once per turn, at the end of the turn, never mid-turn (R3.1): it
  publishes the publish copy that `pending` names in `path` (R5.31), unedited,
  passing the manifest URL when there is one, then runs `mark-published`. No
  other artifact is published.
- **R9.2** — When the manifest URL no longer opens (the publish is refused
  because the artifact does not exist), the session lists the owner's
  artifacts; if one has the same title, it publishes to that one and runs
  `mark-published` with its URL; only if none does, it publishes a new one.
  At most one artifact per title is ever created.
- **R9.3** — The full-progress artifact deleted on claude.ai is recreated from
  the record alone: `render`, then R9.1 and R9.2. A feature artifact cannot be
  lost that way: it is a file in the repository.
- **R9.4** — A publish refused because the artifact changed elsewhere is
  retried once after reading the live version; changes made by others to a
  generated section are not kept (section 0 is always generated), changes to
  content sections are copied into `content/` first.
- **R9.5** — A feature artifact is never published and has no URL.
  `mark-published` refuses its key with a message saying that feature
  artifacts are files in the repository and only Full Progress is published,
  and changes nothing; `pending` never lists one. Verified by
  `test_mark_published_refuses_a_feature_artifact` and
  `test_pending_never_lists_a_feature_artifact`.
- **R9.6** — Full Progress needs a publish only when what the owner sees
  changes: a task added, or a task's status, item, Expected, release (`release`,
  `rides`, `phases`, `risk`, `no_release`), `waits_on`, an open decision, or a feature row of
  section 1. A change to a detail, a basis, a content section or the stamp alone
  is committed and rendered but does not make `pending` list Full Progress; it
  rides the next publish. `mark-published` stores a fingerprint of those fields
  (`published_fingerprint` in the manifest) and `pending` compares against it.
  Verified by `test_detail_only_change_needs_no_publish` and
  `test_status_change_needs_a_publish`.
- **R9.7** — When claude.ai refuses a publish for its daily limit, the session
  runs `mark-deferred full-progress --until <ISO time of the reset>` (for a
  limit that resets at UTC midnight, the next UTC midnight). Until that time
  `pending` lists Full Progress as `deferred until HH:MM (<timezone_label>)` and
  exits 0, and the end-of-turn hook does not block on it: it prints one line
  saying the publish is deferred and when. After that time both behave as
  before. Any later `mark-published` clears the deferral. Verified by
  `test_deferred_publish_does_not_block_until_the_reset` and
  `end_of_turn_reminds_once_while_deferred`.
- **R9.8** — Full Progress is published at least every 60 minutes while the
  project has a record (the hourly fail-safe). `pending --refresh` lists it
  even when nothing changed (reason `refresh requested ...`) and writes a
  fresh publish copy; the end-of-turn hook asks for it (R8.18). Verified by
  `test_pending_refresh_lists_an_unchanged_full_progress`.
- **R9.9** — A change to a release task's status or phase is published in the
  same turn, not left to the hour (R8.18).
- **R9.10** — `scripts/publish_hourly.py` prints exactly what a session's
  hourly cron does: nothing when Full Progress was published less than 60
  minutes ago and no release task changed since; otherwise the one-line
  reason and the three steps (`pending --json --refresh`, publish the copy
  unedited, `mark-published`). It only reads the record and never publishes.
  Verified by `test_publish_hourly_prints_what_the_cron_does_or_nothing`.
- **R9.11** — The fresh-copy check (DL-62). `pending --json` records, for the
  publish copy it writes, `copy_sha256` and `copy_written_at` (and keeps
  them, with a hash of the record files Full Progress is made from, beside the
  copy in `.claude/artifacts-publish/<file>.meta.json`). `mark-published`
  refuses, changing nothing, when that copy was edited since, or when the
  registry, content, design or a rendered page changed after it was written:
  the session runs `pending --json` again and publishes the fresh copy. With
  no recorded copy it behaves as before. Verified by
  `test_pending_records_the_publish_copy_hash_and_time` and
  `test_mark_published_refuses_a_stale_or_edited_copy`.

---

## 10. Installation and the rule file

- **R10.1** — The plugin is installable on its own
  (`/plugin install luismc-artifacts@<marketplace>`) and is enabled by
  `luismc-project-setup`'s `claude-setup` in every project it sets up, through
  `enabledPlugins` in the project's `.claude/settings.json`. `<marketplace>` is
  the name under which the owner registered this plugin's marketplace: the
  suffix of the `luismc-project-setup@...` entry in the owner's user
  `enabledPlugins`, else the marketplace file's own name. A project that names
  a marketplace the owner registered differently enables nothing.
- **R10.2** — Installing creates no file in the project. The first
  `feature-new` or `init` adds `.claude/artifacts-queue.json`,
  `.claude/artifacts-stop-state.json`, `.claude/artifacts-publish/` (the
  publish copy, R5.31), `.claude/artifacts-record.lock` (R4.17) and `.claude/worktrees/` to `.gitignore`.
  Since 1.1.0 it no longer copies the rule file (R10.4). Verified by
  `test_init_session_files`.
- **R10.3** — The rule file holds one short imperative line per rule: record
  work as a task before starting it; start branch names with the task ID;
  change status only with `set-task-status`; publish Full Progress once, at
  the end of the turn, never mid-turn, and never publish a feature artifact;
  never type a status row by hand; put every doc under `docs/`;
  record the options the owner chose between, and the choice, in the feature's
  `decisions.json` in the same turn (§5.4); the four lines of R3.2 to R3.5;
  and that old claude.ai pages of feature artifacts are deleted only with the
  owner's confirmation (R4.23); and that an Expected time comes with its basis (R6.11).
- **R10.4** — The plugin delivers the rule file itself: the session-start hook
  (R8.9) prints it in every project that has a record, every session, so a rule
  change reaches every project with the plugin and no copy can go stale.
- **R10.5** — `check` reports a `.claude/rules/project-artifacts.md` that
  differs from the plugin's `rules/project-artifacts.md` as a note, not a
  finding: it does not change the exit code, and it says that the plugin now
  delivers the rule at session start and the copy can be deleted. Verified by
  `test_check_notes_a_differing_rule_copy`.
- **R10.6** — The `.claude/rules/project-artifacts.md` that `init` of 1.0.0
  copied into the project is deleted from the working tree by the next writing
  command (left uncommitted) when its text, with line endings normalised and
  surrounding whitespace stripped, has the SHA-256 of a rule file a released
  plugin version shipped (the script holds the hash of each) or of the current
  one; the command output says so. A copy that differs (the owner edited it) is
  kept, and `check` keeps noting it (R10.5). Verified by
  `test_stale_rule_copy_is_removed_with_the_migration_commit` and
  `test_edited_rule_copy_is_kept`.

---

## 11. Failure modes

| Dependency | Unavailable → | Rationale |
|---|---|---|
| Artifact tool | **fail closed** for the turn, then open after 3 blocks (R8.4) | Unpublished status is the drift this exists to stop; a loop is worse. |
| `file:` links from a claude.ai page | **fall back** to the path shown as text (R5.31) | Some browsers block `file:` links from a web page; the path beside each link can be copied and opened by hand. |
| Committing the record | **not done** (R4.13) | The plugin writes files; the project commits them when it chooses. |
| `gh` at session start | **fail open** (R8.6) | Catch-up is a convenience; the next session tries again. |
| Time zone data | **fall back** (R4.12) | A slightly wrong label beats no stamp; the warning says so. |
| Project design discovery | **fall back** to the default (R5.12) | The look never blocks a status. |

- **R11.1** — Each failure prints one line naming the dependency and the exit
  code; no failure is silent.

---

## 12. Configuration reference

| Key | Default | Ceiling | Direction | Section |
|---|---|---|---|---|
| `merged_status` | `Live` | — | `Live` or `Built` | §8.1 |
| Earlier fold age (`Live` rows only) | 14 days | 60 days | may only be lengthened | §6.2 |
| End-of-turn blocks | 3 | 3 | fixed | §8.2 |
| `CLAUDE_ARTIFACTS_HOOKS` | `on` | — | `off` disables all hooks | §8 |
| `record_dir` in `.claude/artifacts.json` | `docs/artifacts` | under `docs/` | any folder under `docs/` | §4.11 |

---

## 13. Test gate

- **R13.1** — `tools/test_project_artifacts.py` builds throwaway git repos with
  a local bare remote (to prove it is never touched) and proves each command, each check of §14 (one fixture per
  check that fails without it), INV-1 to INV-3, R4.13 to R4.29, R6.10, R6.11, R5.31, R5.32,
  R5.33 to R5.39, R5.45 to R5.47, R5.8a, R4.30, R4.31 to R4.38, R7.4 to R7.6, R9.5 and R10.6.
- **R13.2** — `tools/test_project_artifacts_hooks.py` feeds sample hook input
  to each hook and asserts the queue, the exit code and the output, including
  R8.4, R8.8 to R8.17 and INV-4, and that every hook does nothing without a
  manifest.
- **R13.3** — Before release, the plugin is run on a scratch clone of the
  plugin's own repository: its existing record is converted to this format,
  rendered and checked with no findings, and a status change runs end to end
  and the git state is unchanged.
- **R13.4** — `spec_check.py` passes on this document; every SKILL.md declares
  the model and effort of its kind in the model profiles.

---

## 14. Conformance gate

`project_artifacts.py check` reports, each with its requirement ID:

| Check | Requirement |
|---|---|
| Titles start with `Feature: ` or `Full Progress: ` | R5.1 |
| Exactly one full-progress artifact when any feature artifact exists | INV-2 |
| Section 0 first, named `Status and checklist`, holding the stamp, the lede (optional), At a glance, tiles, key and checklist in order | R5.3 |
| At a glance block: groups in order; each group lists exactly its tasks; Live within 24 hours, at most 8 | R5.33 to R5.35 |
| Each glance group a `<details class="glance-group">` with label and count in the `<summary>`; `built` and `live` closed, the others open | R6.13 |
| Sections numbered 0..N without gaps; contents match | R5.2 |
| Stamp format, `datetime` attribute and zone label | R5.5 |
| Checklist columns per kind | R6.4 |
| Only the nine statuses; each row in its group; only `Live` rows older than 14 days in Earlier | R6.1, R6.2, R6.3 |
| Every group a `<details class="status-fold">` with its heading in the `<summary>`; `Live or built` closed, the others open; `Earlier` inside `Live or built` | R6.12 |
| Expected format on open rows | R6.6 |
| Warning: open row whose Expected time has passed | R6.14 |
| `expected_basis`: a string of 1 to 80 characters, on open rows only | R6.10 |
| Checklists and tiles equal the registry | INV-1, R5.8 |
| Every feature task on the full-progress artifact, linked to the feature file by a relative link | R6.5, R5.30 |
| Section 1 of Full Progress: the in-progress and complete folds, their open state and counts; the five columns, a Last updated time and a State per feature, sort buttons, rows in the default order | R5.6, R5.39, R5.44, R5.50 |
| Release fields: `release`, `phases`, `risk`, `rides`; Expected is the end of the last phase | R5.40, R5.41 |
| Release numbers: positive, unique, none left `true`; `RELEASE-<n>` on every release row | R5.45 |
| Full Progress grouped by release; release line on rows that rode one | R5.46 |
| Every Running or Built task rides a release | R5.47 |
| Tile labels name tasks | R5.8a |
| The release timeline is present exactly when a release is open, between the key and the checklist, with its caption and `aria-label` | R5.42, R5.43 |
| A feature page's Full Progress published line equals the manifest's | R5.38 |
| `updated` and `published_at` in the manifest are ISO times with an offset | R4.30 |
| A feature artifact is a complete HTML document with its CSS inlined and no external resource but the fonts link; Full Progress is a fragment beginning with `<title>` | R5.27, R5.28, R5.29 |
| IDs unique, prefixes registered | R4.5, R4.6 |
| History last on feature artifacts, Date / Change | R5.4 |
| `decisions.json` valid: fields, IDs, options, choice, previews, images, task | R5.14 to R5.18 |
| No hand-written Decisions section | R5.19 |
| Decisions section just before History, newest first, one card per option, the choice marked, open and replaced decisions shown | R5.20 to R5.23 |
| Needs you group equals the generated set (tasks, then open decisions); `Nothing needs you.` when empty | R5.7, R5.25 |
| Warning: open decision with no task in Needs you | R5.26 |
| Warning: lede over 300 characters | R5.37 |
| Structure stylesheet byte-identical; token block complete | R5.10, R5.11 |
| `extra_css` redefines no structure selector | R4.11 |
| Rendered HTML equals a fresh render | INV-3 |
| `retired` and `deleted` are lists of well-formed entries | R4.19 |
| `retired_features` entries well-formed, keys and prefixes unique, each decisions archive present, no content folder for a retired key | R4.31, R4.32, R4.1 |
| Note, not a finding: retired pages still to delete; feature `url` fields still to move | R4.18, R4.22 |

Exit 0 clean, 1 findings, 2 unreadable.

---

## 15. Design rationale

**Why one registry.** Status typed in two places drifted within hours in an
earlier project. A single record with generated views cannot disagree with
itself.

**Why the repo is the record.** A claude.ai artifact can be deleted; a
project's repo is its durable memory. Rendering from the repo makes the
artifacts disposable views.

**Why the plugin writes files and never commits.** Versions up to 1.7 kept the
record in a worktree of the default branch and pushed it, which committed to the
default branch of every project and triggered a paid deploy on each record
change. From 1.8.0 the record is files in the working tree; the project, which
knows its own branches and deploys, commits them when it chooses.

**Why hooks block the turn.** A sentence in CLAUDE.md asking to keep pages
current is what already failed. The end-of-turn hook makes "published" a
condition of finishing, and the 3-block limit keeps it from trapping a session
that cannot publish.

**Why only Full Progress is published, once per turn.** claude.ai allows 200
artifact publishes per account per day and every republish counts. Publishing
every artifact after every change used the whole day's budget in one day. The
status the owner needs at a glance is Full Progress; the feature pages are
reference material, read from a checkout. Changes accumulate during the turn
and cost one publish at its end.

**Why a feature artifact is a standalone file.** A complete document with its
CSS inlined opens by double-click in any browser, light and dark, with the same
look it had on claude.ai, and it is versioned with the repository. Full
Progress links to it by relative link in the committed file (works from a
checkout) and by absolute `file:///` link in the publish copy (works from the
owner's machine); browsers that block `file:` links from a web page still show
the path as text.

**Why an old page is never deleted without the owner.** Deleting a claude.ai
artifact cannot be undone and stops its link for everyone who has it. The
script cannot delete one, and a hook that made the session delete would turn a
cleanup into a decision taken without the owner. The pages are therefore
listed, the owner is asked, and the end of the turn never waits for the answer.

**Why the hooks tell the session to migrate.** A hook may not write the record
(INV-4), and waiting for an unrelated writing command left an upgraded project
half migrated for days. The hooks read the record, say what is old, and the
end-of-turn block makes the session run the one command that migrates it.

**Why Expected is a date.** "today" is true when written and wrong the next
morning without anyone changing it. A date goes visibly stale.
