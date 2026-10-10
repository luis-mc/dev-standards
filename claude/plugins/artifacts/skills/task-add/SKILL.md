---
name: task-add
description: Add a task to a project's artifacts — a unit of work with an ID, a status and an owner (a feature artifact or the project). Use before starting any piece of work that should be tracked, when the user says "add a task", "track this", or names new work for a feature, and whenever a branch needs a task ID to start its name with. Never edit the task registry by hand.
model: sonnet
effort: medium
---

# Task — add

Records work as a task in the registry (`docs/artifacts/registry.json`,
ARTIFACTSPEC 1.0.0) before the work starts. Only the script writes the
registry; never edit `registry.json` or `manifest.json` by hand.

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`, run from
anywhere inside the project's repository. Exit 0 is success; on any other exit
read the message, fix the cause and rerun.

## Steps

1. **Find the owner.** Read `docs/artifacts/manifest.json` (read only) in
   `<repo>/.claude/worktrees/artifacts-record`, or on the default branch if the
   worktree does not exist yet. The owner is a feature artifact's `key`, or
   `project`. If the manifest does not exist, stop and offer
   `feature-artifact-new` or `full-progress-artifact-new`.
2. **Collect** the item (at most 80 characters), the detail (plain text, at
   most 600 characters), the status (default `To do`; one of Live, Done,
   Running, Needs you, Waiting, To do, On hold, Failed), the expected date and,
   for a project task, the app or service. Ask only for what is missing.
   `expected` is a real date from `date` in the project's zone (the manifest's
   `timezone`): `DD Mon`, or `DD Mon ~HH:MM` for work due within a day,
   optionally followed by `; ` and a short note. Never `today`, `soon`,
   `tomorrow` or `next` alone.
3. **Add it:**
   `task-add --owner <key|project> --item "TEXT" --detail "TEXT" --expected "DD Mon" [--app A] [--status S] [--prefix P]`.
   `--prefix` is needed when the owner is `project` and the project has more
   than one prefix. The command prints the new ID and renders and commits the
   record.
4. **Publish** what `pending` lists, in this turn:
   - Run `pending --json`. Handle every artifact it lists. Take `file` and
     `url` from `docs/artifacts/manifest.json` in the record worktree (read
     only).
   - Publish with the Artifact tool: `file_path` is
     `<record worktree>/docs/artifacts/<file>`, unchanged; `url` is the
     manifest URL when it is not empty. If it is refused because the artifact
     does not exist, list the owner's artifacts and match the exact title
     (`Feature: <name>` or `Full Progress: <project>`); publish to that one,
     and only when none matches publish a new one. If it is refused because
     the artifact changed elsewhere, `read` the live version once, copy
     content-section changes into `content/<key>/`, run `edit-content <key>`
     and retry once.
   - Run `mark-published <key> --url <URL>` for each, with the URL the publish
     returned. Rerun `pending` until it exits 0.
5. **Tell the owner** the new task ID, and that its branch name must start with
   it (`<ID>-short-name`).
