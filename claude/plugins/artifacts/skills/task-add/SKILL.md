---
name: task-add
description: Add a task to a project's artifacts — a unit of work with an ID, a status and an owner (a feature artifact or the project). Use before starting any piece of work that should be tracked, when the user says "add a task", "track this", or names new work for a feature, and whenever a branch needs a task ID to start its name with. Never edit the task registry by hand.
model: sonnet
effort: medium
---

# Task — add

Records work as a task in the registry (`docs/artifacts/registry.json`,
ARTIFACTSPEC 1.6.0) before the work starts. Only the script writes the
registry; never edit `registry.json` or `manifest.json` by hand.

Every activity is a task before it starts, whoever does it: work given to
agents and the session's own (contracts, specs, reviews, joins, test runs,
releases, deploys, cleanup). A task is Running while any work for it runs.
Work still to come after it (join, CI, release) is a task of its own, Running
or To do. `Built` means finished but not released; `Live` means released.
(`Done` is a retired name for `Built`.)

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`, run from
anywhere inside the project's repository. Exit 0 is success; on any other exit
read the message, fix the cause and rerun.

## Steps

1. **Find the owner.** Read `docs/artifacts/manifest.json` (read only) in
   the record worktree (`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" worktree` prints its path; by default
   `<repo>/.claude/worktrees/artifacts-record`, movable with
   `LUISMC_ARTIFACTS_WORKTREE` or `.claude/artifacts-local.json`), or on the
   default branch if the worktree does not exist yet. The owner is a feature artifact's `key`, or
   `project`. If the manifest does not exist, stop and offer
   `feature-artifact-new` or `full-progress-artifact-new`.
2. **Collect** the item (at most 80 characters), the detail (plain text, at
   most 600 characters), the status (default `To do`; one of Live, Built,
   Running, Needs you, Waiting, To do, On hold, Failed), the expected date and,
   for a project task, the app or service. Ask only for what is missing. Use `Running` for work that is running as you
   add it.
   `expected` is a real date from `date` in the project's zone (the manifest's
   `timezone`): `DD Mon`, or `DD Mon ~HH:MM` for work due within a day,
   optionally followed by `; ` and a short note. Never `today`, `soon`,
   `tomorrow` or `next` alone. When you give an Expected time, give its basis
   too (what it waits on and how long): `--basis "agent slot ~01:30, ~1.5 h"`,
   at most 80 characters, open statuses only; it shows under the Expected value.
   A release (`--release`) may carry phases, repeatable `--phase NAME=HH:MM-HH:MM`
   (`agents`, `join`, `ci`, `merge`) and one named `--risk "LABEL=MINUTES"`; its
   Expected is the end of its last phase, and the risk is named, never padded in.
   `--release` gives the task the next release number, shown as `RELEASE-<n>`.
   Work that rides a release says so with `--rides <release ID or RELEASE-n>`;
   every Running or Built task that is not itself a release must (the command refuses otherwise).
   A task that ships nothing (a publish, a study, a cleanup) says so instead:
   `--no-release "REASON"`, at most 80 characters. It needs no release, is never
   Built (finished, it goes Live), and the command refuses `--no-release` with
   `--release` or `--rides`; Full Progress shows it under `Not in a release yet`
   with the line `ships nothing: REASON`.
3. **Add it:**
   `task-add --owner <key|project> --item "TEXT" --detail "TEXT" --expected "DD Mon" [--basis "TEXT"] [--app A] [--status S] [--prefix P]`.
   For `--owner project`, `--prefix` picks one of the project's prefixes; a new
   prefix that no feature uses is registered by the command. The command prints the new ID and renders and commits the
   record (the push comes once, at the end of the turn).
4. **Do not publish now.** Status changes accumulate during the turn;
   Full Progress is published once, at the end of the turn, per "Publishing" in
   the `task-status-update` skill (claude.ai allows 200 publishes per account
   per day). Feature artifacts are files in the repository and are never
   published.
5. **Tell the owner** the new task ID, and that its branch name must start with
   it (`<ID>-short-name`).

## Old claude.ai pages

If `pending` lists `retired` pages (old claude.ai pages of feature artifacts),
ask the owner to confirm, delete each confirmed one with the Artifact tool
(`action: "delete"`), then run `mark-deleted <key> --url <URL>`.
