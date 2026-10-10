# ARTIFACTSPEC — Project Artifacts Specification

**Status:** Normative
**Version:** 1.1.0
**Applies to:** every project that keeps feature artifacts and a full-progress artifact with the `luismc-artifacts` plugin
**Audience:** Claude Code sessions in those projects, and the implementers of `luismc-artifacts`
**Owner:** Luis Carvalho
**Last reviewed:** 2026-10-10
**Changes in 1.1.0:** §5.4 Decisions (`decisions.json`, R5.14 to R5.26).

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

---

## Decision record

| # | Question | Resolution | Consequence |
|---|---|---|---|
| D1 | Where is a task's status stored? | Once, in the task registry `docs/artifacts/registry.json`. | Every checklist and tile is generated; none is typed (§4.3). |
| D2 | Do branch names start with the task ID? | Yes: `AR5-artifactspec`. | Hooks match events to tasks by branch name (§8). |
| D3 | How do changes made outside a session arrive? | At the next session start. | No cloud routine in 1.0 (§8.3). |
| D4 | Which look? | The project's own design tokens; the plugin's default design when it has none. | One fixed structure stylesheet, free tokens (§5.3). |
| D5 | App / service column? | On the full-progress artifact only. | Feature checklists keep four columns (§6.3). |
| D6 | Where is the record? | In the repo, `docs/artifacts/`, committed to the default branch as docs-only commits. | A deleted artifact is recreated from it without duplicates (§9). |
| D7 | How does a project get the plugin? | `luismc-project-setup` installs it in every project it sets up; it also installs on its own. | Installing creates nothing until the first artifact (§10). |
| D8 | Which clock do times use? | The owner's time zone, per project, from the manifest. | Expected and stamps name the zone (§6.4). |
| D9 | Does the plugin's home repository touch other projects? | No. | Each project adopts the plugin in its own sessions. |
| D10 | How are the owner's choices between options kept? | Every option offered and the one chosen, in the feature's `decisions.json`; the script draws the Decisions section. | The options, the recommendation and the choice are never lost in free text (§5.4). |

---

## 1. Scope

### 1.1 In scope

| Area | Covered |
|---|---|
| Kinds | Feature artifacts and the one full-progress artifact of a project. |
| Record | `docs/artifacts/`: manifest, task registry, content, design tokens, rendered HTML. |
| Commands | `project_artifacts.py`: create, add tasks, change status, render, check, commit, publish bookkeeping. |
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
| project artifact | A claude.ai artifact that belongs to a project: a feature artifact or the full-progress artifact. Never "page". |
| feature artifact | The artifact of one feature, titled `Feature: <name>`. |
| full-progress artifact | The project's one artifact of all ongoing work, titled `Full Progress: <project>`. |
| task | One unit of work with an ID, a status and an owner. |
| owner (of a task) | The feature artifact it belongs to (its `key`), or `project`. |
| project task | A task whose owner is `project`. |
| task registry | `docs/artifacts/registry.json`, the only store of task state. |
| manifest | `docs/artifacts/manifest.json`, the list of the project's artifacts and settings. |
| record | Everything under `docs/artifacts/`. |
| record worktree | A git worktree of the default branch where the script writes and commits the record (§4.6). |
| render | Generating an artifact's HTML from the record. |
| publish | Sending rendered HTML to claude.ai through the session's Artifact tool. |
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
| `scripts/hook_after_command.py`, `hook_end_of_turn.py`, `hook_session_start.py` | The three hooks (§8). |
| `templates/feature-artifact.html`, `templates/full-progress-artifact.html` | Page skeletons with placeholders (§5.1). |
| `templates/project-artifact.css` | The fixed structure stylesheet. |
| `design/default-design.css`, `design/DESIGN.md` | Default tokens and the token contract (§5.3). |
| `rules/project-artifacts.md` | The rule file a project gets on its first artifact (§10). |
| Five skills | `feature-artifact-new`, `full-progress-artifact-new`, `task-add`, `task-status-update`, `project-artifact-check`. |

### 3.2 Invariants

- **INV-1** — A task's status exists in exactly one place, the task registry.
  Verified by `test_render_from_registry_only`.
- **INV-2** — A project has at most one full-progress artifact, and has one
  whenever it has a feature artifact. Verified by `test_one_full_progress`.
- **INV-3** — Every rendered HTML file in the record equals what rendering the
  record produces now. Verified by `test_rendered_matches_record`.
- **INV-4** — No hook modifies the record. Verified by
  `test_hooks_never_write_record`.

### 3.3 Status change lifecycle

1. Event: a command the session ran, a session start, or the owner's words.
2. Queue: a hook writes the suggested change to the queue (§8.1), or the
   session acts directly.
3. Apply: the session runs `set-task-status`; the script updates the registry,
   renders every artifact that shows the task, and commits the record.
4. Publish: the session publishes every artifact `pending` lists and runs
   `mark-published` for each.
5. End of turn: the end-of-turn hook lets the turn end only when the queue is
   empty and nothing is pending.

- **R3.1** — Steps 3 to 5 complete in the same turn as the event.

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
  <file>.html                    the last rendered HTML of each artifact
  README.md                      how to recreate (generated)
```

- **R4.1** — The record lives under `docs/artifacts/` and nowhere else. Section
  0 of every artifact is generated and has no content file.

### 4.2 Manifest

| Field | Type | Meaning |
|---|---|---|
| `spec` | string | `"ARTIFACTSPEC 1.0.0"` |
| `project` | string | Project name shown in titles. |
| `timezone` | string | IANA zone, e.g. `Europe/Lisbon`. |
| `timezone_label` | string | Shown after times, e.g. `Lisbon`. |
| `windows_timezone` | string | Windows zone ID for the fallback, e.g. `GMT Standard Time`. |
| `design` | string | `"default"` or `"design.css"`. |
| `default_branch` | string | Where the record is committed, e.g. `main`. |
| `merged_status` | string | Status a merge suggests: `"Live"` (default) or `"Done"`. |
| `full_progress_artifact` | object | `{key:"full-progress", title, url, file, published_sha256}` |
| `feature_artifacts` | array | `{key, title, url, file, prefix, apps:[...], published_sha256}` each |
| `project_prefixes` | array | Task prefixes owned by the project, e.g. `["DS"]`. |
| `updated` | string | ISO time of the last change, with offset. |

- **R4.2** — `key` is lowercase letters, digits and hyphens; `prefix` is 2 to 5
  capital letters; every prefix appears once across the manifest.
- **R4.3** — `url` is empty until the first publish; `published_sha256` is the
  SHA-256 of the HTML that was last published, empty before that. A `url` with
  an empty `published_sha256` is valid: an existing artifact adopted by a new
  record, listed by `pending` until it is published from the record.
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
  is no remove command); dropped work is set On hold or Done with a detail
  saying so, so the next number, the highest plus one, is always unused.
- **R4.6** — `owner` is a feature `key` from the manifest or `project`. A
  feature task's prefix is its feature's prefix; a project task's prefix is
  in `project_prefixes`. A task moved into a feature after it got its ID keeps
  its ID, so a feature task may also carry a prefix from `project_prefixes`.
- **R4.7** — `status` is one of the eight statuses of §6.1. `changed` is set by
  the script on every status change, never by hand.
- **R4.8** — `expected` follows §6.4. `item` is at most 80 characters; `detail`
  is plain text, at most 600 characters.
- **R4.9** — Tasks are stored in ID order (prefix, then number); rendering
  orders them (§6.2), the file does not.

### 4.4 Content

`meta.json`: `{title, hero, lede, extra_css}`. `lede` is the session's
sentence about where the work stands; the script appends the needs-you line
(§5.2). Each `NN-<slug>.html` is an HTML fragment whose first line is an HTML
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

### 4.6 Committing the record

- **R4.13** — The script writes the record in a record worktree at
  `<repo>/.claude/worktrees/artifacts-record`, a detached worktree of
  `origin/<default_branch>`, created on first use. Before each change it
  fetches and resets that worktree to `origin/<default_branch>`; after it, it
  commits and pushes to `<default_branch>`. The session's own working tree is
  never touched — a session on a task branch would otherwise carry record
  changes into its pull request.
- **R4.14** — A record commit changes only paths under `docs/artifacts/`; the
  script refuses to commit anything else. Its message is
  `docs/artifacts: <ID> <status>` or the message given.
- **R4.15** — A push rejected as non-fast-forward is retried after a fresh
  fetch and re-apply, at most 3 times; then the command fails with exit 3.
- **R4.16** — A push rejected by branch protection fails with exit 4 and the
  message `record push refused by <default_branch> protection`; the change
  stays committed in the record worktree for `commit --retry`.
- **R4.17** — With `--no-push` (tests and the real-repo test), the script
  commits in the record worktree and does not push.

---

## 5. Artifact structure and look

### 5.1 Templates

The templates hold `{{placeholders}}`: `title`, `fonts_link`, `design_css`,
`structure_css`, `extra_css`, `kind_label`, `project`, `hero`, `contents`,
`sections`, `stamp`. The rendered file is an HTML fragment beginning with
`<title>`, as the Artifact tool expects (no `<html>`, `<head>` or `<body>`).

- **R5.1** — A feature artifact's title is `Feature: <name>`; the full-progress
  artifact's is `Full Progress: <project>`.
- **R5.2** — Sections are numbered from 0 in order with no gaps, and the
  contents list shows the same numbers and titles.
- **R5.3** — Section 0 is titled `Status and checklist` and holds, in order:
  the stamp, the lede, the tiles, the status key and the checklist.
- **R5.4** — A feature artifact's last section is `History`, a table
  `Date | Change`, newest first. The full-progress artifact has no History.
- **R5.5** — The stamp reads `Last update: DD Mon HH:MM (<timezone_label>)` in
  a `<time>` element whose `datetime` attribute is the ISO time with offset.
- **R5.6** — The full-progress artifact's section 1 lists every feature
  artifact with its link, its task ID range and one line on where it stands
  (taken from its `meta.json` lede's first sentence). Section 1 is generated,
  so the full-progress artifact's content files `01-*.html` onward render as
  sections 2 and up.

### 5.2 Lede and tiles

- **R5.7** — The lede is the content lede followed by a generated sentence:
  `Needs you: <ID> <item>; ...` listing every task in Needs you or Failed, or
  `Nothing needs you.` when none is.
- **R5.8** — Tiles show the count of each status that has at least one task,
  in the order of §6.1, computed from the registry.
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

- **R5.25** — The generated needs-you sentence (R5.7) also lists every open,
  unreplaced decision after the tasks, as `<ID> <question>`; the sentence is
  `Nothing needs you.` only when no task and no decision waits. In the
  full-progress artifact's section 1 a feature's line ends with `n decisions
  open.` (`1 decision open.`) when it has any.
- **R5.26** — `check` warns, without failing, for an open, unreplaced decision
  whose `task` is not a task of that feature in Needs you, or, when it names no
  task, when the feature has no task in Needs you.

---

## 6. Statuses and the checklist

### 6.1 Statuses

| Status | Meaning |
|---|---|
| Live | Released or in production. |
| Done | Finished; nothing to release. |
| Running | Being worked on now. |
| Needs you | Waits on the owner. |
| Waiting | Waits on something else: CI, a dependency, a time. |
| To do | Planned, not started. |
| On hold | Paused by decision. |
| Failed | Broke; needs a fix or a decision. |

- **R6.1** — Only these eight statuses exist; each has a fixed chip class
  `status-<lowercase-hyphenated>` styled by the structure stylesheet.

### 6.2 Groups and order

- **R6.2** — Checklist rows are grouped, in this order: `Running now and next`
  (Running, Waiting, To do — earliest expected first), `Needs you, failed or
  on hold` (Needs you, Failed, On hold), `Live or done` (newest `changed`
  first). An empty group is omitted.
- **R6.3** — In the full-progress artifact, Live or Done rows whose `changed`
  is more than 14 days old fold into a closed `<details>` titled `Earlier`.

### 6.3 Columns

- **R6.4** — A feature artifact's checklist columns are
  `Status | Item | Detail | Expected (<timezone_label>)`; the full-progress
  artifact's are `Status | Item | App / service | Detail | Expected
  (<timezone_label>)`.
- **R6.5** — In the full-progress artifact a feature task's Item links to its
  feature artifact (when it has a URL); every feature task appears there.

### 6.4 Expected

- **R6.6** — On a Running, Waiting, To do, Needs you or On hold row, Expected is
  `DD Mon` or `DD Mon ~HH:MM` (a time for work due within a day) in the
  owner's zone, optionally followed by `; ` and a short note. Words such as
  `today`, `soon`, `tomorrow` or `next` alone fail — a relative word goes stale
  without anyone changing it.
- **R6.7** — On a Live or Done row, Expected is the date it happened.
- **R6.8** — `set-task-status` to Live or Done sets Expected to the current
  date when no `--expected` is given.

---

## 7. Commands

All commands run as `python <plugin>/scripts/project_artifacts.py <command>`
from anywhere inside the project's repository, read `docs/artifacts/` from the
record worktree (§4.6), and exit 0 on success, 1 on findings or a refused
action, 2 on an unreadable record, 3 on a push race, 4 on a protected branch.
`--json` prints a machine-readable result.

| Command | Does |
|---|---|
| `init --project NAME [--timezone IANA] [--label L] [--windows-timezone ID] [--default-branch B]` | Creates the manifest, an empty registry and the full-progress artifact's content. Refuses if a manifest exists. Zone defaults to the machine's. |
| `feature-new --key K --title NAME --prefix P --apps a,b [--hero TEXT] [init flags]` | Adds a feature artifact (content folder with `meta.json`, a section `01-what-and-why.html` stub and a first History row). Runs `init` first, with the same `init` flags, when there is no manifest; `--project` is then required. |
| `task-add --owner K\|project --item TEXT --detail TEXT --expected TEXT [--app A] [--status S] [--prefix P]` | Adds a task with the next free number; prints its ID. For `--owner project`, `--prefix` picks one of `project_prefixes`, and a new prefix not used by any feature is registered. |
| `set-task-status ID STATUS [--detail TEXT] [--expected TEXT] [--history TEXT]` | Changes one task; adds a History row to its feature artifact when `--history` is given. |
| `export-content KEY --to DIR` | Copies the artifact's content files from the record to DIR for editing, `decisions.json` and its `assets/` folder included. |
| `edit-content KEY --from DIR` | Replaces the artifact's content files in the record with those in DIR (after the fetch and reset of R4.13), validates, renders and commits. The session never edits the record worktree directly; the reset would discard it. It refuses an edit that removes a decision or changes the choice of a decided one (R5.15). |
| `design set FILE\|default` | Validates FILE against the token contract (R5.11), copies it to `docs/artifacts/design.css`, sets manifest `design`, renders and commits; `default` removes it. |
| `render [--all]` | Renders every artifact whose output would change. |
| `check [--record PATH]` | The conformance checks of §14; lists findings with their requirement ID, then any warnings (R5.26), which do not change the exit code. |
| `pending` | Lists artifacts whose rendered HTML hash differs from `published_sha256`, and queued events. Exit 1 when anything is listed. `--json` prints `{"artifacts": [{"key", "title", "file", "path", "url", "reason"}], "queue": [events]}`; `path` is the absolute path of the HTML to publish. |
| `mark-published KEY --url URL` | Records the URL and the hash of the current HTML. |
| `queue list\|clear [--id ID]` | Shows or removes queued events. |
| `commit [--retry] [--message M]` | Commits and pushes the record (also done by every writing command). |

- **R7.1** — Every writing command validates the record before and after the
  change and writes nothing when either fails.
- **R7.2** — `set-task-status` updates the registry, renders the task's feature
  artifact (if any) and the full-progress artifact with a new stamp, removes
  the task's queued events, and commits — in one invocation.
- **R7.3** — `set-task-status` rejects a status outside §6.1 and names the
  nearest allowed status (`Merged` → `Live`).
- **R7.4** — Rendering is deterministic: the same record and the same stamp give
  byte-identical HTML.

---

## 8. Hooks

All three hooks are registered in the plugin's `hooks/hooks.json`, run
`python <plugin>/scripts/hook_*.py`, and exit 0 doing nothing when the
project has no `docs/artifacts/manifest.json` in the current checkout or on
`origin/<default branch>`.

### 8.1 After-command hook (PostToolUse and PostToolUseFailure, Bash)

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
  command with no task ID in the branch queues nothing.
- **R8.2** — The hook finishes in under 2 s and never fails the tool call: any
  error exits 0 with a one-line message on stderr.

### 8.2 End-of-turn hook (Stop)

- **R8.3** — When the queue is not empty or `pending` lists an artifact, the
  hook blocks the stop (`{"decision": "block", "reason": ...}`) with a reason
  that names each item and the exact commands to run.
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

---

## 9. Publishing and recreation

- **R9.1** — The session publishes an artifact with the Artifact tool, passing
  the manifest URL when there is one, then runs `mark-published`.
- **R9.2** — When the manifest URL no longer opens (the publish is refused
  because the artifact does not exist), the session lists the owner's
  artifacts; if one has the same title, it publishes to that one and runs
  `mark-published` with its URL; only if none does, it publishes a new one.
  At most one artifact per title is ever created.
- **R9.3** — An artifact deleted on claude.ai is recreated from the record
  alone: `render`, then R9.1 and R9.2.
- **R9.4** — A publish refused because the artifact changed elsewhere is
  retried once after reading the live version; changes made by others to a
  generated section are not kept (section 0 is always generated), changes to
  content sections are copied into `content/` first.

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
  `feature-new` or `init` copies `rules/project-artifacts.md` to
  `.claude/rules/project-artifacts.md` and adds `.claude/artifacts-queue.json`,
  `.claude/artifacts-stop-state.json` and `.claude/worktrees/` to `.gitignore`.
- **R10.3** — The rule file holds one short imperative line per rule: record
  work as a task before starting it; start branch names with the task ID;
  change status only with `set-task-status`; publish what `pending` lists in
  the same turn; never type a status row by hand; put every doc under `docs/`;
  record the options the owner chose between, and the choice, in the feature's
  `decisions.json` in the same turn (§5.4).

---

## 11. Failure modes

| Dependency | Unavailable → | Rationale |
|---|---|---|
| Artifact tool | **fail closed** for the turn, then open after 3 blocks (R8.4) | Unpublished status is the drift this exists to stop; a loop is worse. |
| `git push` of the record | **fail closed** (exit 3 or 4) | A status change that is not in the repo is lost on the next reset. |
| `gh` at session start | **fail open** (R8.6) | Catch-up is a convenience; the next session tries again. |
| Time zone data | **fall back** (R4.12) | A slightly wrong label beats no stamp; the warning says so. |
| Project design discovery | **fall back** to the default (R5.12) | The look never blocks a status. |

- **R11.1** — Each failure prints one line naming the dependency and the exit
  code; no failure is silent.

---

## 12. Configuration reference

| Key | Default | Ceiling | Direction | Section |
|---|---|---|---|---|
| `merged_status` | `Live` | — | `Live` or `Done` | §8.1 |
| Earlier fold age | 14 days | 60 days | may only be lengthened | §6.2 |
| End-of-turn blocks | 3 | 3 | fixed | §8.2 |
| Push retries | 3 | 5 | — | §4.6 |
| `CLAUDE_ARTIFACTS_HOOKS` | `on` | — | `off` disables all hooks | §8 |

---

## 13. Test gate

- **R13.1** — `tools/test_project_artifacts.py` builds throwaway git repos with
  a bare remote and proves each command, each check of §14 (one fixture per
  check that fails without it), INV-1 to INV-3, R4.13 to R4.17 and R7.4.
- **R13.2** — `tools/test_project_artifacts_hooks.py` feeds sample hook input
  to each hook and asserts the queue, the exit code and the output, including
  R8.4 and INV-4, and that every hook does nothing without a manifest.
- **R13.3** — Before release, the plugin is run on a scratch clone of the
  plugin's own repository: its existing record is converted to this format,
  rendered and checked with no findings, and a status change runs end to end
  with `--no-push`.
- **R13.4** — `spec_check.py` passes on this document; every SKILL.md declares
  the model and effort of its kind in the model profiles.

---

## 14. Conformance gate

`project_artifacts.py check` reports, each with its requirement ID:

| Check | Requirement |
|---|---|
| Titles start with `Feature: ` or `Full Progress: ` | R5.1 |
| Exactly one full-progress artifact when any feature artifact exists | INV-2 |
| Section 0 first, named `Status and checklist`, holding its five parts in order | R5.3 |
| Sections numbered 0..N without gaps; contents match | R5.2 |
| Stamp format, `datetime` attribute and zone label | R5.5 |
| Checklist columns per kind | R6.4 |
| Only the eight statuses; each row in its group | R6.1, R6.2 |
| Expected format on open rows | R6.6 |
| Checklists and tiles equal the registry | INV-1, R5.8 |
| Every feature task on the full-progress artifact, linked | R6.5 |
| IDs unique, prefixes registered | R4.5, R4.6 |
| History last on feature artifacts, Date / Change | R5.4 |
| `decisions.json` valid: fields, IDs, options, choice, previews, images, task | R5.14 to R5.18 |
| No hand-written Decisions section | R5.19 |
| Decisions section just before History, newest first, one card per option, the choice marked, open and replaced decisions shown | R5.20 to R5.23 |
| Needs-you sentence lists open decisions | R5.25 |
| Warning: open decision with no task in Needs you | R5.26 |
| Structure stylesheet byte-identical; token block complete | R5.10, R5.11 |
| `extra_css` redefines no structure selector | R4.11 |
| Rendered HTML equals a fresh render | INV-3 |

Exit 0 clean, 1 findings, 2 unreadable.

---

## 15. Design rationale

**Why one registry.** Status typed in two places drifted within hours in an
earlier project. A single record with generated views cannot disagree with
itself.

**Why the repo is the record.** A claude.ai artifact can be deleted; a
project's repo is its durable memory. Rendering from the repo makes the
artifacts disposable views.

**Why a record worktree.** A session usually works on a task branch. Writing
the record there would put status changes into feature pull requests and
conflict between parallel sessions. A detached worktree of the default branch
keeps the record linear and the session's tree clean.

**Why hooks block the turn.** A sentence in CLAUDE.md asking to keep pages
current is what already failed. The end-of-turn hook makes "published" a
condition of finishing, and the 3-block limit keeps it from trapping a session
that cannot publish.

**Why Expected is a date.** "today" is true when written and wrong the next
morning without anyone changing it. A date goes visibly stale.
