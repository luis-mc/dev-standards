# DS64 train: transcript-folds, marketplace rename, DS63

Integration branch `DS64-integration` (DS63 already merged into it). Two agent
branches are cut from it. Decisions D1 to D10 are in
`docs/artifacts/content/transcript-folds/decisions.json`.

| Branch | Tasks | Owns |
|---|---|---|
| `TF2-transcript-folds-plugin` | TF2 | everything under `claude/plugins/transcript-folds/`, `tools/ci_areas.py`, `tools/test_ci_areas.py`, `.github/workflows/spec-lint.yml`, `docs/reports/TF2.md` |
| `TF3-claude-setup-install` | TF3, DS65 | `.claude-plugin/marketplace.json`, `README.md`, everything under `claude/plugins/project-setup/skills/claude-setup/`, `tools/test_model_profiles.py`, one change note `docs/specs/changes/TF3-claude-setup-install.md`, `docs/reports/TF3.md` |
| `DS64-integration` (orchestrator) | TF1, DS64, TF4 | this file, the join, change-note fold, the ready PR |

No branch touches another's files. If you need a change in a file you do not
own, stop and write it in your report.

## Shared names (both branches use exactly these)

| Thing | Value |
|---|---|
| Marketplace name | `dev-standards` |
| Plugin name | `luismc-transcript-folds` |
| Plugin folder | `claude/plugins/transcript-folds` |
| Diffs toggle chord | `ctrl+x d` |
| Diffs toggle action | `theme:toggleSyntaxHighlighting` |
| Commands toggle chord | `ctrl+x f` |
| Commands toggle action | `theme:editCustom` |
| Keybindings context | `Global` |
| Slash commands | `/fold-diffs`, `/fold-commands` (each toggles its switch) |

Why those actions: a mod's `Button` with `action` is pressed by the person's
chord for that action from the prompt, but only while no engine handler of the
action is mounted. Both actions are handled only inside the `/theme` dialog, so
outside it the chords reach the plugin. They differ from the ones the
third-party hide-diffs plugin borrows, so the two can be installed together.

## TF2: the plugin, written from scratch

**Originality rule.** Do not open, read, search or copy anything under
`~/.claude/plugins/**/hide-diffs/**` or `**/gixxy22-plugins/**`. Write from
this contract and the API types only. Names, layout and code are our own.

**API reference.** Claude Code 2.1.296's mod API is declared in
`C:/Users/Luis/AppData/Local/Temp/claude/bundled-skills/2.1.296/6d5fd78ed4d2101a011b9188bb836b5f/plugin-authoring/types/claude-code.d.ts`
(about 14,000 lines; grep it for `'tool.call'`, `'ui.render'`, `AbovePrompt`,
`ToolUse`, `ToolResult`, `ToolGroup`, `Button`, `command.register`,
`'command.run'`, `atom`, `$.store`) and described in `reference.md` and the
`examples/` folder beside it (`band.tsx` and `pane.tsx` show a band, a command,
atoms and a contract). Never commit the `.d.ts`. Do not write under
`~/.claude/dev-mods/`.

**Layout**, close to the other plugins here (`hooks/`, `scripts/`-style
folders, snake_case file names):

```
claude/plugins/transcript-folds/
  .claude-plugin/plugin.json      name, version 1.0.0, description, author Luis Carvalho, "types", "userConfig"
  hooks/hooks.json                { "modules": ["./transcript_folds.tsx"] } (+ "description" if validate accepts it)
  hooks/transcript_folds.tsx      register(on, options): the hooks only; every decision is a call into fold/
  hooks/fold/*.ts                 pure logic: no import from 'claude-code', no JSX, no Node APIs
  types/state.d.ts                PluginState contract under 'luismc-transcript-folds'
  tests/*.test.ts                 node:test + node:assert suites over hooks/fold/
```

Split `hooks/fold/` by concern, for example: line counting from hunks, notebook
cells and new files; display width and cutting text to fit (wide characters
and emoji count 2 cells, an ellipsis marks a cut); the summary text of a change;
the outcome of a shell command; the session tally. Imports between files use
explicit `.ts` extensions so Node can run them. Confirm early with
`claude plugin validate claude/plugins/transcript-folds` that the engine loads
a module that imports `./fold/<file>.ts`; if it does not, report it before
going further.

**Settings** (`userConfig`, shown under `/config`):

| Key | Type | Default | Meaning |
|---|---|---|---|
| `foldAbove` | number | `5` | A diff with this many changed lines or fewer is drawn in full; `0` folds every diff. |
| `marker` | string | `»` | Starts every folded diff line; empty for none. |
| `compactCounts` | boolean | `false` | Compact mode: the counts go on the tool call's own row and the line under it is dropped. |

**State** (`$.state` atoms declared in `types/state.d.ts`; the two switches are
also written to `$.store` so they survive restarts): diffs folded (default
`true`), commands folded (default `true`), the session tally (files touched,
lines added, lines removed), the project root at session start (paths are
shown relative to it), the counts of each finished call by `tool_use_id`, and
the outcome of each finished shell call by `tool_use_id`.

**Behaviour.**

1. **Folded diffs** (diffs switch on). The result of an Edit, Write, MultiEdit
   or NotebookEdit whose change is over `foldAbove` lines draws one dim line:
   `<marker> <relative path>:<first changed line> (+<added> −<removed>)`, the
   added count in the success colour and the removed count in the error
   colour; a new file reads `<marker> new <path> (+<lines>)`; a notebook names
   its cell. A Bash result that carries file edits draws its own output
   without the per-file diff, then one line `<marker> <n> files (+a −r)`.
   Errored results, small changes and the permission or review dialog are
   never folded. When the switch is off, the engine draws as usual, and runs
   of edits the engine groups into one row are drawn expanded so every diff is
   visible.
2. **Compact mode.** The Edit or Write row itself carries `<marker> (+a −r)`
   after its label and the result line is dropped; if the label and counts do
   not fit the width, the counts go on the next line.
3. **Folded commands** (commands switch on). A finished Bash or PowerShell call
   draws one row: `● <Tool>(<command on one line, cut to fit>)  ⎿  <outcome>`,
   the bullet in the success or error colour; the outcome is `<n> lines`,
   `no output`, the first line of the error in the error colour, plus
   `· <marker> <n> files (+a −r)` when it edited files. Its result block is
   dropped. A running call keeps the engine's row with its command cut to one
   line. Interrupted calls are never folded. A call that edited files while
   the diffs switch is off is not folded, so its diff shows.
4. **Band above the prompt.** One dim line: two plain buttons and the tally,
   e.g. `Diffs folded (ctrl+x d) · Commands folded (ctrl+x f) · 7 files +120 −34 this session`;
   the tally part is absent before the first change. The buttons carry the
   actions above, so the chords press them; pressing one flips its switch,
   writes it to `$.store`, and shows a toast. The band steps aside while a
   survey is shown.
5. **Slash commands** `/fold-diffs` and `/fold-commands`, registered at
   session start, flip the same switches and answer one line saying the new
   state.
6. **Tally.** After each successful Edit, Write, MultiEdit, NotebookEdit or
   Bash call that changed files, add its files and line counts to the session
   tally and store the call's counts; after each Bash or PowerShell call,
   store its outcome.

**Tests.** No `claude-code/testing` and no npm packages: `node --test
claude/plugins/transcript-folds/tests/` (Node 24 runs `.ts` directly). Cover
every exported function, including: several hunks (first line is the first
hunk's start), CRLF and a missing final newline, a new file, a notebook cell
added, changed and removed, threshold `0` and exactly at the threshold, display
width of wide characters and emoji, cutting with an ellipsis at tiny widths,
empty output, stderr only, an exit code with no text, a multi-line error
(first line only), and the tally adding the same file twice. Also run
`claude plugin validate claude/plugins/transcript-folds` and paste its output
into the report.

**CI.** Add an area `transcript-folds` to `tools/ci_areas.py` (paths under
`claude/plugins/transcript-folds/`) with its test cases in
`tools/test_ci_areas.py`, and a job in `.github/workflows/spec-lint.yml` gated
by it that sets up Node 24 (`actions/setup-node`) and runs the `node --test`
command above. Keep the existing jobs and any required-check names working.

**Version.** The new manifest starts at `1.0.0`. Run the change-notes check
(`claude/plugins/project-setup/skills/tech-stack-setup/assets/tooling/shared/scripts/delivery/change_notes.py check --config tools/change-notes.json --base-ref origin/DS64-integration`);
if a new manifest's version line trips it, leave it and say so in the report:
the orchestrator settles it at the join.

## TF3 and DS65: claude-setup installs it, the marketplace is renamed

1. **DS65, marketplace rename.** `.claude-plugin/marketplace.json` `name`
   becomes `dev-standards`; drop `(luismc-dev-tools)` from its description; add
   the plugin entry `luismc-transcript-folds`, source
   `./claude/plugins/transcript-folds`, with a one-line description. `README.md`:
   every install line uses `@dev-standards`, including luismc-artifacts (drop
   the `<marketplace>` hedge, keep one sentence saying a machine that
   registered the marketplace under another name uses that name), the intro
   names the marketplace `dev-standards`, add the install line and a short
   section for luismc-transcript-folds (what it does, the two chords, the two
   slash commands, the three settings). `tools/test_model_profiles.py` uses
   `dev-standards` where it substitutes the marketplace name.
2. **TF3, claude-setup.** Part of the standard setup (D7): on every run, whatever
   target was picked, the change plan includes two user-level pieces, shown in
   the single step 3 confirmation like every write outside the repo:
   - `~/.claude/settings.json` `enabledPlugins."luismc-transcript-folds@<marketplace>": true`,
     `<marketplace>` found exactly as for luismc-artifacts; an existing entry
     (true or false) is left as it is. Update the text that says the skill
     writes no other `enabledPlugins` entry and none to a user target.
   - New asset `assets/keybindings.json` holding the `Global` context with the
     two chords. Merge into `~/.claude/keybindings.json`: create the file if it
     is absent; otherwise find the `Global` context block (add one if none);
     a chord that is absent is added; a chord bound to the same action is
     already there; a chord bound to another action is a **conflict** the
     owner chooses in step 3. Never change or remove any other binding. Keep
     unknown top-level keys. The file parses as JSON after the write.
   - Step 4 verifies both; step 5 reports them and says the plugin must be
     installed (`claude plugin install luismc-transcript-folds@<marketplace>`)
     and that the chords and plugin take effect after `/reload-plugins` or a
     restart.
   - SKILL.md description and the pieces table name the new pieces.
   - Tests in `tools/test_model_profiles.py` (or a sibling test it already
     calls): the asset parses, has exactly the two chords with the actions in
     the table above, and, when `claude/plugins/transcript-folds/hooks/` exists
     on the branch, the plugin's source names the same two actions; when it is
     absent (this branch before the join) that check is skipped with a printed
     message, never silently passed.
   - Change note `docs/specs/changes/TF3-claude-setup-install.md`, `plugin:`
     the luismc-project-setup `plugin.json`, `change: minor`.

## Rules for both agents

- Work in your own worktree on your branch, cut from `origin/DS64-integration`.
  Write `docs/reports/<task>.md` first, push after every step, keep the report
  current (what changed, test commands and results, open questions).
- Never edit version lines; change notes only. Never edit `docs/artifacts/`.
- Light change: run only the suites you touch, locally
  (`node --test ...`, `python tools/test_ci_areas.py`,
  `python tools/test_model_profiles.py`, `python tools/test_rule_tags.py`).
  No branch CI runs; the ready PR's CI is the one full run.
- Stop only processes you started. Do not open pull requests.
- Commit messages end with the `Co-Authored-By` line you were given.

## TF4: smoke test (orchestrator, after the join)

`claude --plugin-dir claude/plugins/transcript-folds` with the two chords bound:
an Edit over 5 lines folds; one of 3 lines does not; ctrl+x d and ctrl+x f flip
the band and the rows; `/fold-diffs` and `/fold-commands` do the same; a
failing command shows its error in red; the tally counts; compact mode puts the
counts on the row; the choice survives a restart.
