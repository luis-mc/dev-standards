---
name: full-progress-artifact-new
description: Create the project's full-progress artifact — the one claude.ai artifact, titled `Full Progress: <project>`, that lists every feature and every task of the project with its status. Use when a project starts tracking its work, when the user asks for a full-progress or overall progress artifact, or when a project has feature artifacts but no full-progress one. A project has at most one.
model: sonnet
effort: medium
---

# Full-progress artifact — new

Creates the project's one full-progress artifact from the record
(`docs/artifacts/`, ARTIFACTSPEC 1.3.1). The script is the only writer of
`manifest.json` and `registry.json`; never edit either by hand.

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`, run from
anywhere inside the project's repository. Exit 0 is success; on any other exit
read the message, fix the cause and rerun. Never work around a refusal by
editing the record.

Full Progress is the only artifact of a project that is published to claude.ai,
and it is published once per turn, at the end of the turn, never mid-turn:
claude.ai allows 200 publishes per account per day and every republish counts.
Feature artifacts are standalone HTML files in the repository; Full Progress
links to them as local files.

The record lives in the record worktree (a worktree of the default branch);
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" worktree` prints its path. By default it is
`<repo>/.claude/worktrees/artifacts-record`; the project may move it with the
environment variable `LUISMC_ARTIFACTS_WORKTREE` or `record_worktree` in the
git-ignored `.claude/artifacts-local.json` (an absolute path; the next command
moves the worktree there). Never write into it, and never into the
session's own working tree: the script resets the record worktree before each
change and would discard the edit. Edit content in a scratch directory outside
the repository instead (the session's scratchpad directory, in a new folder).

## Steps

1. **Look first.** If `docs/artifacts/manifest.json` exists (in the repo or on
   the default branch) and has a `full_progress_artifact`, the project already
   has one: do not run `init` (it refuses). Go to step 5 to extend its content or
   to publish it, and say so.
2. **Ask** with AskUserQuestion: the project name (shown in the title), the
   time zone (IANA name, for example `Europe/Lisbon`; offer the machine's), its
   short label (for example `Lisbon`), the default branch, and the project's
   task prefixes (2 to 5 capital letters each) for work that belongs to no
   feature.
3. **Create it:**
   `init --project NAME --timezone IANA --label LABEL [--windows-timezone ID] [--default-branch B]`.
   This creates the manifest, an empty registry and the full-progress artifact's
   content, and adds the gitignore lines (the rule itself is delivered by the
   plugin at every session start).
4. **Find the project's design** (R5.12), only when the manifest says
   `"design": "default"`. Look in this order and stop at the first hit:
   design-token files; Tailwind or theme configuration; CSS custom properties
   in the app; the live site, if the project names one. Show the owner what you
   found (file, colours, fonts) and ask before using it. Only on a yes, write
   the design file in the scratch directory: every token of the contract in
   `${CLAUDE_PLUGIN_ROOT}/design/DESIGN.md`, light values on `:root`, dark
   values under both
   `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`
   and `:root[data-theme="dark"]`. Then run `design set <file>`. If it rejects
   the file, fix the tokens it names and run it again. A no, or nothing found,
   keeps the default design.
5. **Write the content.** Run `export-content full-progress --to <scratch dir>`
   and edit the files there:
   - `meta.json`: `title`, `hero` (one line: what the project is), `lede` (a
     note of one or two sentences of context the registry cannot show: an
     incident, a constraint, a plan; never restate statuses, the At a glance
     block lists them; may be empty), `extra_css` (empty unless needed).
   - Optional sections for what the owner wants beside the checklist (how the
     project is released, where things live). Files start at `01-` and render as
     section 2 and up, because section 1 (the list of feature artifacts) is
     generated. Each is an HTML fragment whose first line is
     `<!-- title: Section title -->`. No `<script>`, no `<style>`, no section
     numbers. `extra_css` must never redefine a selector of the structure
     stylesheet.
   The full-progress artifact has no `decisions.json`; decisions belong to the
   feature artifacts.
   Write only what is true now. Then run
   `edit-content full-progress --from <scratch dir>` and fix any validation
   error in the scratch files.
6. **Add the project's tasks**, for work that belongs to no feature, with
   `task-add --owner project --prefix P --item "TEXT" --detail "TEXT" --expected "DD Mon" [--basis "TEXT"] --status "To do" [--app A]`
   (or the status it truly has). `--app` names the app or service shown in the
   App / service column. `item` is at most 80 characters. `expected` is a real
   date from `date` in the project's zone, `DD Mon` or `DD Mon ~HH:MM`,
   optionally followed by `; ` and a note; never `today`, `soon` or `next`
   alone. When you give an Expected time, give its basis too (what it waits on
   and how long) with `--basis`, at most 80 characters. This artifact shows all work, so every activity is a task here, the
   session's own included (contracts, joins, test runs, releases, cleanup);
   `Built` means finished but not released; release work still to come is a task of its own.
7. **Publish** Full Progress at the end of the turn, per "Publishing" below.
8. **Check:** run `check` and report any finding with its requirement ID.
9. **Tell the owner** the artifact's URL, and that every feature artifact
   created later appears in it by itself, linked as a local file.

## Publishing

Once, at the end of the turn, never mid-turn. Repeat until `pending` exits 0:

1. Run `pending --json`. It lists Full Progress (the only artifact it lists)
   when its committed render changed since the last publish, and writes the
   publish copy: the same page with absolute `file:///` links to the feature
   files (some browsers block `file:` links from a web page; the page shows
   each path as text so it can be copied). The entry carries `key`, `title`,
   `path` (the absolute path of the publish copy) and `url` (empty before the
   first publish).
2. Publish with the Artifact tool: `file_path` is the entry's `path`, unchanged,
   and `url` is the entry's `url` when it is not empty. On a first publish pass
   `icon` (a generic word such as `tracker`) and a one-sentence `description`.
   Publish the file as written; do not edit it.
3. If the publish is refused because the artifact does not exist, list the
   owner's artifacts (`action: "list"`, `scope: "mine"`) and look for one whose
   title is exactly the entry's `title`. If one exists, publish to its `url`.
   Only when none does, publish without `url`. At most one artifact per title
   is ever created.
4. If it is refused because the artifact changed elsewhere, `read` the live
   version once. Copy changes to content sections into a scratch export
   (`export-content full-progress --to <dir>`), then
   `edit-content full-progress --from <dir>`; drop changes to the generated
   sections. Run `pending --json` again for the new `path`, and retry once.
5. Run `mark-published full-progress --url <URL>` with the URL the publish
   returned. It records the hash of the committed render, not of the publish
   copy.
6. If there is no Artifact tool, say what is still unpublished and stop; the
   end-of-turn hook then reminds you.

## Old claude.ai pages

`pending --json` has a `retired` array: old claude.ai pages of feature
artifacts. They do not change `pending`'s exit code and are never published.
Ask the owner to confirm, delete each confirmed page with the Artifact tool
(`action: "delete"`), then run `mark-deleted <key> --url <URL>` (`--gone` when
the page no longer exists). Never delete without the owner's confirmation.
