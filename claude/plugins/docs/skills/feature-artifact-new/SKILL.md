---
name: feature-artifact-new
description: Create a feature artifact — the standalone HTML file `docs/artifacts/feature-<slug>.html` of one feature, titled `Feature: <name>`, with a status checklist, written content and a history. It opens by double-click in any browser and is never published. Use when the user starts a feature and wants it tracked, asks for a feature artifact or feature page, or says a feature needs its own status view. Creates the project's full-progress artifact first when it does not exist yet. Also promotes a feature page's decided content into the feature's spec (`docs/features/<x>/spec.md`, DOCSPEC; the file `luismc-docs:feature-spec-new` owns) when the user asks to promote, finish or document a feature.
model: opus
effort: medium
---

# Feature artifact — new

Creates one feature artifact from the project's record (`docs/artifacts/`,
ARTIFACTSPEC 1.8.0). The script is the only writer of `manifest.json` and
`registry.json`. Never edit either by hand. A feature artifact is a standalone
HTML file in the repository (`docs/artifacts/feature-<slug>.html`, CSS inlined,
opens by double-click). It is never published to claude.ai, because claude.ai
allows 200 publishes per account per day: only Full Progress is published, once
at the end of the turn.

Every command below is
`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" <command>`. Run it
from anywhere inside the project's repository. Exit 0 is success. On any other
exit, read the message, fix the cause and rerun. Never work around a refusal by
editing the record.

The record lives in `docs/artifacts/` of the session's working tree
(`python "${CLAUDE_PLUGIN_ROOT}/scripts/project_artifacts.py" worktree` prints
the directory). The plugin writes the files there and stops. It never commits,
pushes or otherwise writes git state. The project commits `docs/artifacts/`
when it chooses. Edit content in a scratch directory outside the repository
and pass it to the script. Never edit the record files by hand.

## Steps

1. **Ask** with AskUserQuestion: the feature's name, the apps or services it
   touches (comma-separated), and its task prefix (2 to 5 capital letters, not
   used by any other feature or project prefix). Derive the key from the name:
   lowercase letters, digits and hyphens. If the project has no record yet
   (no `docs/artifacts/manifest.json` in the repo or on the default branch),
   also ask for the project name and time zone (IANA name, short label; offer
   the machine's), and for the Windows zone ID and default branch if they
   differ from the machine's.
2. **Create it:**
   `feature-new --key K --title "NAME" --prefix P --apps a,b [--hero "TEXT"]`.
   With no record yet, add the `init` flags to the same command
   (`--project NAME --timezone IANA --label LABEL`, plus `--windows-timezone ID`
   and `--default-branch B` when given). The script runs `init` itself, so the
   full-progress artifact exists afterwards. Do not run `init` separately. The
   command also adds the gitignore lines on first use. It does not copy the rule
   file, because the plugin delivers the rule at every session start.
3. **Find the project's design** (R5.12), only when the manifest says
   `"design": "default"`. Look in this order and stop at the first hit:
   design-token files; Tailwind or theme configuration; CSS custom properties
   in the app; the live site, if the project names one. Show the owner what you
   found (file, colours, fonts) and ask before using it. Only on a yes, write
   the design file in the scratch directory: every token of the contract in
   `${CLAUDE_PLUGIN_ROOT}/design/DESIGN.md`, light values on `:root`, dark
   values under both
   `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }`
   and `:root[data-theme="dark"]`. Then run `design set <file>`. If it rejects
   the file, fix the tokens it names and run it again. On a no, or if you found
   nothing, keep the default design. Design never blocks the artifact.
4. **Write the content.** Run `export-content <key> --to <scratch dir>` and edit
   the files there:
   - `meta.json`: `title`, `hero` (one line saying what the feature is), `lede`
     (one or two sentences of context the registry cannot show: an incident, a
     constraint, a plan; never restate statuses, because the At a glance block
     lists them; may be empty), `extra_css` (empty unless needed).
   - Replace the stub `01-what-and-why.html` and add `02-...`, `03-...` as the
     feature needs (design, how it works, links). Number files from
     `01-` upward, with no gaps. Do not write a section titled Decisions. The
     script refuses it, because decisions are drawn from `decisions.json`
     (below).
   - Each file is an HTML fragment whose first line is `<!-- title: Section title -->`.
     No `<script>`, no `<style>` and no section numbers in fragments. Section 0
     (status and checklist) and the last section (History) are generated.
   - `extra_css` may add classes. It must never redefine a selector of the
     structure stylesheet.
   - `decisions.json` (optional, feature artifacts only): the owner's choices
     between options, see "Decisions" below.

   Write what is true now, from the code and the owner's words. Do not invent
   status, dates or results.
5. **Apply and validate:** `edit-content <key> --from <scratch dir>`. Fix any
   validation error it reports in the scratch files and run it again.
6. **Add the feature's tasks**, one per unit of work, with
   `task-add --owner <key> --item "TEXT" --detail "TEXT" --expected "DD Mon" [--basis "TEXT"] --status "To do"`
   (or the status it truly has). The command prints each task's ID. `item` is at
   most 80 characters. `expected` is a real date from `date` in the project's
   zone, `DD Mon` or `DD Mon ~HH:MM`, optionally followed by `; ` and a note.
   Never `today`, `soon` or `next` alone. When you give an Expected time, give
   its basis too (what it waits on and how long) with `--basis`, at most 80
   characters.

   Every activity is a task, the session's own included. `Built` means finished
   but not released. Release work that comes later (join, release) is a task of
   its own.
7. **Do not publish the feature artifact**, and do not publish Full Progress
   yet. Publish it once, at the end of the turn, per "Publishing" below.
8. **Check:** run `check`. Report any finding with its requirement ID. The
   script writes the record to `docs/artifacts/` in the working tree and never
   commits or pushes it; the project commits when it chooses. If `pending`
   fails, say so and stop.
9. **Tell the owner** where the file is (`docs/artifacts/<file>` in the
   repository; open it by double-click), its task IDs, and that branch names
   for these tasks must start with the task ID (`<ID>-short-name`).

## Decisions

Whenever the owner chooses between options (designs, approaches, names), record
every option you offered and the one chosen, in the same turn. An option the
owner has not chosen yet is an open decision. The script draws the section
`Decisions` (just before History) from `content/<key>/decisions.json`. Never
write that section by hand.

1. `export-content <key> --to <scratch dir>`, then edit `decisions.json` there
   (create it when absent): `{"decisions": [...]}`, oldest first.
2. To **add** one, append `{"id": "D<next>", "question": "...", "asked":
   "YYYY-MM-DD", "status": "open" or "decided", "options": [...], "chosen":
   null or a label, "decided": null or "YYYY-MM-DD"}`. IDs run D1, D2, ... with
   no gap; never reuse or remove one. Give at least two options, each with a
   unique `label` and a `summary`. A yes/no question lists Yes and No. Mark at
   most one option `"recommended": true`. When the decision is decided, put the
   owner's own words, verbatim, in `owner_words`. Put the task the decision
   belongs to in `task`. For an open decision, set that task to Needs you with
   `set-task-status`.
3. Whatever the owner was shown goes into the option's `preview`: the mockup or
   the AskUserQuestion preview text, as a small HTML fragment (usually
   `<pre>...</pre>`). No script, style, iframe, `on*` attribute or external URL.
   Or use `"image": "assets/name.png"` with the file in an `assets/` folder next
   to the other files (png, jpg, gif or webp, at most 300 KB).
4. To **close** an open decision, set `status` to `decided`, `chosen` to the
   option's label and `decided` to the date. A closed decision never changes. A
   changed mind is a new decision with `"replaces": "D<n>"`.
5. Run `edit-content <key> --from <scratch dir>`; fix what it reports and run it
   again.

## Publishing

Only Full Progress is published, once, at the end of the turn. Status changes
accumulate during the turn and never trigger a publish of their own. Feature
artifacts are never published and have no URL; `mark-published` refuses them.

At the end of the turn, repeat until `pending` exits 0:

1. Run `pending --json`. It lists Full Progress when its render changed since
   the last publish. It also writes the publish copy: the same page with
   absolute `file:///` links to the feature files. Each entry carries `key`,
   `title`, `path` (the absolute path of the publish copy) and `url` (empty
   before the first publish).
2. Publish with the Artifact tool. `file_path` is the entry's `path`,
   unchanged. `url` is the entry's `url` when it is not empty. On a first
   publish, pass `icon` (a generic word such as `tracker`) and a one-sentence
   `description`. Publish the file as written; do not edit it.
3. If the publish is refused because the artifact does not exist, list the
   owner's artifacts (`action: "list"`, `scope: "mine"`) and look for one whose
   title is exactly the entry's `title`. If one exists, publish to its `url`.
   Only when none does, publish without `url`. At most one artifact per title
   is ever created.
4. If the publish is refused because the artifact changed elsewhere, `read` the
   live version once. Copy changes to content sections into a scratch export
   (`export-content full-progress --to <dir>`), then run
   `edit-content full-progress --from <dir>`. Drop changes to the generated
   sections. Run `pending --json` again for the new `path`, and retry once.
5. Run `mark-published full-progress --url <URL>` with the URL the publish
   returned.
6. If there is no Artifact tool, say what is still unpublished and stop. The
   end-of-turn hook then reminds you.

## Old claude.ai pages

A feature artifact published by plugin 1.0.0 left a claude.ai page behind. Its
URL is kept in the manifest's `retired` list, and `pending` lists it under
`retired`. Ask the owner to confirm. Delete each confirmed page with the
Artifact tool (`action: "delete"`), then run `mark-deleted <key> --url <URL>`.
This never blocks the feature work or the end of the turn.

## Promote to a spec

The artifact is for work and decisions in flight. The feature's spec is how it
works now (DOCSPEC R4.10, `luismc-docs`). Promote-to-spec is the one link from a feature page's decided content to its feature spec. It writes the same file `luismc-docs:feature-spec-new` owns and follows that skill's template. When a feature's content is decided,
or before its branch joins (R10.4), promote it in the same branch:

1. Dry run: `promote-to-spec KEY [--feature ID]`. It prints:
   - the target `docs/features/<ID>/spec.md` (ID defaults to KEY; it is the
     folder name and never changes, DOCSPEC R4.1)
   - where each page section goes, by heading: why, what, how it works,
     functional and non-functional requirements, screens, design, failure
     modes, tests, not built yet, code map. "for users" goes to 3 and "for
     developers" to 7. A heading that matches none goes under 3 and is listed.
   - the topics it found in `docs/docs.json`
   - which decisions are decided (promoted) or open (left in the artifact)

   When the spec already exists, it prints the diff of the merge.
2. `promote-to-spec KEY [--feature ID] --apply` writes it. A new spec gets
   front matter (`status: proposed`, `version: 0.1.0`, `artifact:` the page's
   file name) and the sections in template order. An existing spec is merged
   section by section:
   - your text is kept
   - new parts are appended under a `<!-- promoted from the feature page -->`
     comment
   - missing sections are inserted in order
   - a template placeholder is replaced (the output says so)
   - a decision already in the table keeps your row

   It never changes the record and never commits.
3. Review the spec against the template. Add the testable requirements (R5.x,
   R6.x), the code map, a diagram and `apps`/`topics` from `docs/docs.json`.
   Delete what does not apply. Then run the `luismc-docs` checks
   (`docs_check.py`) and commit the spec with the branch. Only the release fold
   writes the version (R4.3).

## Retire a finished feature

When every task a feature owns is Live or Dropped and it has no open decision,
its page and content only take space (ARTIFACTSPEC §4.10). First promote what
lasts (above), then retire it:

1. Dry run: `retire KEY`. It lists the tasks it keeps, each file it would
   delete with its size, and the decisions archive it would write. It refuses
   (exit 1, nothing written) while a task is open or a decision is open
   (R4.33). Finish or drop those first.
2. Show the owner the list and ask. Deleting the page is the owner's call.
3. `retire KEY --yes`:
   - the feature moves to the manifest's `retired_features`
   - `decisions.json` is kept as `retired/<key>.decisions.json`
   - the page and `content/<key>/` are deleted
   - Full Progress lists the feature in one collapsed line (R4.31, R4.32,
     R4.34)

   Its tasks keep their owner and become history: `task-add` and
   `set-task-status` refuse them (R4.36).
4. It never deletes a claude.ai page and never commits. Commit the record with
   the branch. A retired key or its prefix is not reused. `feature-new KEY
   --force` brings the same key back with its old tasks (R4.35).
