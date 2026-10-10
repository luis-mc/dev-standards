---
name: feature-artifact-new
description: Create a feature artifact — the claude.ai artifact of one feature, titled `Feature: <name>`, with a status checklist, written content and a history. Use when the user starts a feature and wants it tracked, asks for a feature artifact or feature page, or says a feature needs its own status view. Creates the project's full-progress artifact first when it does not exist yet.
model: opus
effort: high
---

# Feature artifact — new

Creates one feature artifact from the project's record (`docs/artifacts/`,
ARTIFACTSPEC 1.0.0). The script is the only writer of `manifest.json` and
`registry.json`; never edit either by hand.

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`, run from
anywhere inside the project's repository. Exit 0 is success; on any other exit
read the message, fix the cause and rerun. Never work around a refusal by
editing the record.

The record lives in the record worktree `<repo>/.claude/worktrees/artifacts-record`
(a worktree of the default branch). Write content files there, never in the
session's own working tree.

## Steps

1. **Ask** with AskUserQuestion: the feature's name, the apps or services it
   touches (comma-separated), and its task prefix (2 to 5 capital letters, not
   used by any other feature or project prefix). Derive the key from the name:
   lowercase letters, digits and hyphens. If the project has no record yet, also
   ask the project name and time zone (IANA name, short label; offer the
   machine's) for `init`.
2. **Create it.** With no `docs/artifacts/manifest.json` yet (in the repo or
   on the default branch), run
   `init --project NAME --timezone IANA --label LABEL` first (add
   `--windows-timezone ID` and `--default-branch B` when the owner gave them).
   Then run
   `feature-new --key K --title "NAME" --prefix P --apps a,b [--hero "TEXT"]`.
   The full-progress artifact exists after `init`; `feature-new` also installs
   the rule file and the gitignore lines on first use.
3. **Find the project's design** (R5.12), only when
   `docs/artifacts/design.css` does not exist. Look in this order and stop at
   the first hit: design-token files; Tailwind or theme configuration; CSS
   custom properties in the app; the live site, if the project names one. Show
   the owner what you found (file, colours, fonts) and ask before using it.
   Only on a yes, write `docs/artifacts/design.css` in the record worktree:
   every token of the contract in `${CLAUDE_PLUGIN_ROOT}/design/DESIGN.md`,
   light values on `:root`, dark values under both
   `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`
   and `:root[data-theme="dark"]`. Then run `render --all`. A no, or nothing
   found, keeps the default design. The manifest's `design` field is the
   script's to set: if the render still uses the default tokens, tell the
   owner and keep the default rather than editing `manifest.json`. Design never
   blocks the artifact.
4. **Write the content** in `<record worktree>/docs/artifacts/content/<key>/`:
   - `meta.json`: `title`, `hero` (one line saying what the feature is), `lede`
     (one or two sentences on where the work stands now; the script appends the
     needs-you line), `extra_css` (empty unless needed).
   - Replace the stub `01-what-and-why.html` and add `02-...`, `03-...` as the
     feature needs (design, how it works, decisions, links). Number files from
     `01-` upward, with no gaps.
   - Each file is an HTML fragment whose first line is `<!-- title: Section title -->`.
     No `<script>`, no `<style>` and no section numbers in fragments. Section 0
     (status and checklist) and the last section (History) are generated.
   - `extra_css` may add classes; it must never redefine a selector of the
     structure stylesheet.
   Write what is true now, from the code and the owner's words. Do not invent
   status, dates or results.
5. **Render and validate:** `edit-content <key>`. Fix any validation error it
   reports in the files and run it again.
6. **Add the feature's tasks**, one per unit of work, with
   `task-add --owner <key> --item "TEXT" --detail "TEXT" --expected "DD Mon" --status "To do"`
   (or the status it truly has). The command prints each task's ID. `item` is at
   most 80 characters. `expected` is a real date from `date` in the project's
   zone, `DD Mon` or `DD Mon ~HH:MM`, optionally followed by `; ` and a note;
   never `today`, `soon` or `next` alone.
7. **Publish** every artifact `pending` lists, per "Publishing" below. The new
   feature artifact comes first, then the full-progress artifact, which links
   to it.
8. **Check:** run `check`. Report any finding with its requirement ID. The
   script commits and pushes the record on every writing command; if `pending`
   or a push fails, say so and stop.
9. **Tell the owner** the artifact's URL, its task IDs, and that branch names
   for these tasks must start with the task ID (`<ID>-short-name`).

## Publishing

Repeat until `pending` exits 0.

1. Run `pending --json`. Handle every artifact it lists. For each, take `file`
   and `url` from `docs/artifacts/manifest.json` in the record worktree (read
   only).
2. Publish with the Artifact tool: `file_path` is
   `<record worktree>/docs/artifacts/<file>`, unchanged, and `url` is the
   manifest URL when it is not empty. On a first publish pass `icon` (a generic
   word such as `tracker`) and a one-sentence `description`. Publish the file as
   rendered; do not edit it.
3. If the publish is refused because the artifact does not exist, list the
   owner's artifacts (`action: "list"`, `scope: "mine"`) and look for one whose
   title is exactly the artifact's title (`Feature: <name>` or
   `Full Progress: <project>`). If one exists, publish to its `url`. Only when
   none does, publish without `url`. At most one artifact per title is ever
   created.
4. If it is refused because the artifact changed elsewhere, `read` the live
   version once. Copy changes to content sections into `content/<key>/` and run
   `edit-content <key>`; drop changes to the generated section 0. Retry once.
5. Run `mark-published <key> --url <URL>` with the URL the publish returned.
6. If there is no Artifact tool, say what is still unpublished and stop; the
   end-of-turn hook then reminds you.
