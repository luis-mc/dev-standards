---
name: task-status-update
description: Change a task's status in a project's artifacts and, at the end of the turn, publish Full Progress once. Use when work starts, finishes, fails, waits or is blocked on the owner, when a pull request is opened, ready or merged, when CI passes or fails, when a deploy goes live, when a hook reports queued status events or pending artifacts, or when the user asks to mark, update or move a task. The only way to change a status; never type a status row by hand.
model: sonnet
effort: medium
---

# Task — status update

Changes a task's status through the script. Full Progress shows it and is
published once, at the end of the turn, never after each change: claude.ai
allows 200 publishes per account per day and every republish counts. Feature
artifacts are files in the repository and are never published. Every activity is a task, the session's own
included (contracts, joins, test runs, releases, cleanup): a task is `Running`
while any work for it runs, `Waiting` or `Needs you` when blocked on
something or someone. `Built` means finished but not released (`Live` is released; `Done` is a
retired name the script stores as `Built`); release work still to come (join,
CI, release) is its own task, Running or To do. Before a turn
ends with work still running in the background, its task is `Running`. Only the script writes the registry; never edit
`registry.json` or `manifest.json` by hand, and never type a status row into an
artifact.

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`, run from
anywhere inside the project's repository. Exit 0 is success; on any other exit
read the message, fix the cause and rerun.

## Steps

1. **Find the task ID and the new status.** The ID is the one in the user's
   words, in a queued event (`queue list`), or the start of the current branch
   name (`AR5-artifactspec` is task `AR5`). The status is one of Live, Built,
   Running, Needs you, Waiting, To do, On hold, Failed. A suggested status from
   a queued event is a suggestion: confirm it matches what happened. A word
   outside the eight maps to the nearest (`Merged` is `Live`, or `Built` when the
   project's `merged_status` says so).
2. **Change it:**
   `set-task-status <ID> "<Status>" [--detail "TEXT"] [--expected "DD Mon"] [--history "TEXT"]`.
   - `--detail`: plain text, at most 600 characters, when what the row says
     changed.
   - `--expected`: a real date from `date` in the project's zone, `DD Mon` or
     `DD Mon ~HH:MM`, optionally followed by `; ` and a short note. Never
     `today`, `soon`, `tomorrow` or `next` alone. For Live or Built it defaults
     to the current date; do not pass one.
   - `--history`: one line for the feature artifact's History table, for a
     feature task whose change the owner should be able to look up later.
   The command renders every artifact that shows the task, removes the task's
   queued events and commits the record. Exit 3 or 4 means the record could not
   be pushed; report that and stop, because the change would be lost.
3. **Do not publish yet.** Change as many statuses as the turn needs, each
   with `set-task-status`; they accumulate. Publish at the end of the turn, per
   "Publishing" below.
4. **Clear what is stale.** If `queue list` still shows events for tasks that
   no longer apply, remove them with `queue clear --id <ID>`.
5. **Report** the task, its old and new status, and whether Full Progress was
   published. If there is no Artifact tool, say what is still unpublished and
   stop.

## Publishing

Once, at the end of the turn, never mid-turn. Repeat until `pending` exits 0:

- Run `pending --json`. It lists Full Progress (the only artifact it lists) and
  writes the publish copy: the same page with absolute `file:///` links to the
  feature files. The entry carries `key`, `title`, `path` (the absolute path of
  the publish copy) and `url`.
- Publish with the Artifact tool: `file_path` is the entry's `path`, unchanged;
  `url` is the entry's `url` when it is not empty. If it is refused because the
  artifact does not exist, list the owner's artifacts (`action: "list"`) and
  match the exact `title`; publish to that one, and only when none matches
  publish a new one (with an `icon` such as `tracker`). If it is refused
  because the artifact changed elsewhere, `read` the live version once, copy
  content-section changes through `export-content full-progress --to <dir>` and
  `edit-content full-progress --from <dir>`, and retry once with the new
  `path`; changes to the generated sections are dropped.
- Run `mark-published full-progress --url <URL>` with the URL the publish
  returned.
