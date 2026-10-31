---
description: Apply Claude Code configuration — statusline, settings.json (auto-compact window, output style, Opus-plans/Sonnet-codes model split with a medium-or-high effort level per model), output styles, rules, and CLAUDE.md — to this project and/or the user-level ~/.claude/, turns on and configures all 8 plugins of the luismc marketplace in the project settings (installing missing ones after the owner confirms), and always enables luismc-transcript-folds and binds its two chords at user level. Use when the user asks to set up Claude, configure the statusline, fix their Claude settings, add a CLAUDE.md, or apply their Claude config to a repo or a new machine, or invokes /luismc-project-setup:claude-setup. Not for repo or product tooling (hooks, gitleaks, CI, playwright) — that is /luismc-project-setup:tech-stack-setup.
model: sonnet
effort: medium
---

# Claude setup

Applies the Claude Code configuration in `assets/` (alongside this file) to one
or both of:

- **project** — `.claude/` and `CLAUDE.md` in the current repo, committed,
  shared with anyone who clones it
- **user** — `~/.claude/`, machine-wide, applies to every project

These are genuinely different decisions and the skill covers both because the
configuration splits across them unevenly: a statusline and an auto-compact
window are machine preferences most people want once, globally; instructions and
a pinned output style are usually per-project.

Two user-level pieces are part of the standard setup and are planned on every
run, whatever target was picked: the `luismc-transcript-folds` entry in
`~/.claude/settings.json` and the two chords in `~/.claude/keybindings.json`
(see "The transcript-folds pieces" in step 2). They are shown in the step 3
confirmation like every other write outside the repo.

## The model split this skill enforces

Every project this skill touches gets the same division of labour: the **main
session runs on Opus** and does the thinking — understanding, planning,
designing, reviewing — and **subagents run on Sonnet** and write the code. Each
model also gets an **effort level**, **medium** or **high**, chosen by the user
on every run. The owner's default is **medium for both**, Opus and Sonnet;
it is what the question below preselects and what the shipped files carry.
Six pieces carry it, and all are needed:

| Piece | Enforces |
|---|---|
| `settings.json` `model: "opus"` | the main loop's model |
| `settings.json` `env.CLAUDE_CODE_SUBAGENT_MODEL: "sonnet"` | the default model of every subagent that does not pin its own |
| `settings.json` `modelSettings.<Opus ID>.effortLevel` | the main loop's effort |
| `settings.json` `modelSettings.<Sonnet ID>.effortLevel` | the Sonnet effort for the session itself; subagent effort comes from the rule file, because the docs do not say this entry reaches subagents |
| `.claude/rules/agents-and-integration.md` | the behaviour — the main loop actually hands implementation to subagents instead of writing it itself, and passes the chosen `effort` on each Agent call |
| `.claude/hooks/effort_drift.py` | the warning when a model has no saved effort (see "The alias-drift warning") |

Settings alone only pick models and effort; without the rule the Opus session
would still write all the code itself and the Sonnet default would rarely be
exercised. The rule alone is advice with nothing behind it. Agents whose
definition pins a model (e.g. `luismc-agents:architect` → `opus`) keep it: a
frontmatter `model` takes precedence over `CLAUDE_CODE_SUBAGENT_MODEL`, which
is the intent —
judgment-call agents stay on Opus. Forked subagents always inherit the parent's
model; that is acceptable, since a fork is for continuing the parent's
reasoning, not for implementation.

The rule file does more than the split. `agents-and-integration.md` is the
plugin's one rule file for how agents are run and how work is integrated:
role lines for the orchestrator, code agents, scripts and log triage; the
integrate-once, deploy-once workflow; and where docs live. Its workflow lines
cite `scripts/delivery/*` by path. Those scripts exist only in repos generated
or repaired by `tech-stack-setup` 12 or later; in any other repo the lines name
tools that are not there, and `tech-stack-setup` is what puts them there. The
file is the same for every target and is never edited per repo. It replaces
`model-delegation.md`, which earlier versions of this skill wrote.

**Why effort is carried twice.** Claude Code saves per-model effort as
`modelSettings.<model ID>.effortLevel`, and that entry beats a top-level
`effortLevel`. The docs say nothing on whether it applies to subagents, though.
What they do document for a non-fork subagent is the Agent call's `effort`
parameter, then the agent definition's `effort` frontmatter, then the session's
effort. So the Opus entry and the Sonnet entry set the session, and the rule
file tells the main loop to pass the subagent effort explicitly. Anything that
overrides saved settings overrides the entries too: the env var
`CLAUDE_CODE_EFFORT_LEVEL` (every model, every setting), and `--effort` or
`/effort` for the session. The skill only offers **medium** (the default for
Opus 5.5 and Sonnet 5.5, and the owner's default for both) and **high** (more
tokens and time); `effortLevel` also accepts `low` and `xhigh`, which are left
to the user to set by hand.

The shipped settings also carry a top-level `"effortLevel": "medium"`. A
per-model `modelSettings` entry beats it, so the main session still runs at the
effort chosen for Opus; the top-level key is what applies to sessions whose
model has no entry, such as cloud agents, which run Opus and so get the Opus
default, medium.

## Scope this plugin does NOT cover

Repo and product tooling — `.githooks/pre-commit`, `.gitleaks.toml`,
`.github/workflows/ci.yml`, `playwright.config.ts`, and the
`package.json`/`core.hooksPath` activation — belongs to the sibling skill in
this plugin, `tech-stack-setup`, which generates them from `STACKSPEC` rather
than from a stack-neutral baseline. The split is the point: this skill sets up
the agent working in the repo, the others set up the repo — `tech-stack-setup`
its structure and gates, `auth-setup` its authentication.

## Step 1 — Ask which target, before reading or writing anything

Do not assume. Ask whether to apply **project**, **user**, or **both**. Two
things make this a real question rather than a formality:

- Writing `~/.claude/settings.json` mutates a file outside the repo that affects
  every other project on the machine. That needs explicit confirmation every
  time, even if the user has run this skill before.
- If a project `.claude/settings.json` and `~/.claude/settings.json` both set a
  key, the project one wins. Applying to both can silently make the user-level
  value dead for this repo. Say so if the user picks both.

Then, **whatever target was picked**, ask a second question: should the model
split also be enforced **for all projects** — i.e. written to
`~/.claude/settings.json` (`model`, `env.CLAUDE_CODE_SUBAGENT_MODEL`, the two
effort entries, the drift-hook registration), `~/.claude/hooks/effort_drift.py`
and `~/.claude/rules/agents-and-integration.md`? Ask it even when the user
chose **project** only — the project target always gets the split; this
question is whether every other repo on the machine does too. A "yes" adds just
those pieces to the user target (not the statusline, output style or
CLAUDE.md, unless the user also picked **user** or **both**). A "no" leaves
`~/.claude/` untouched, apart from the two transcript-folds pieces, which are
always planned (see the intro) and which the owner can still decline in step 3.
Skip the question only when the user already picked **user** or **both**,
since the split is then applied there anyway.

Then ask the **effort question**, once for each model of the split:

- the **main session (Opus)** — medium or high? **Recommend medium**: the
  owner's default is Opus at medium effort.
- the **code-writing subagents (Sonnet)** — medium or high? **Recommend
  medium**: the owner's default is Sonnet at medium effort, so code agents run
  at medium unless the user picks high.

Preselect medium for both models and say that this is the owner's default;
high costs more tokens and time. If a
target's settings already hold a `modelSettings.<model ID>.effortLevel` for
that model (see step 2 for the IDs), show it as well, but still mark the
recommended answer. **Ask both every run**, even when a value is already saved:
effort is the user's per-run choice, and one answer covers every target that
gets the split. If the targets disagree on a saved value, show each; the
recommended answer stays preselected.

For a project target that has no `.delivery/config.json`, ask a last question
in the same message: the delivery values (`work_root`, `tz`, `caps`,
`no_attribution`), or the neutral defaults. See "`.delivery/config.json`" in step 2.

## Step 2 — Build a change plan per target

For each chosen target, compare the templates against what is on disk and
classify. Never write during this step.

### `statusline.sh` — overwrite unconditionally

`.claude/statusline.sh` (project) or `~/.claude/statusline.sh` (user) is a pure
display mechanism this plugin owns outright. It is not hand-edited by a project
owner, so it is replaced without asking. It has no `jq` dependency by design —
`jq` is not guaranteed on PATH — so it parses the statusline JSON with
`grep`/`sed`. Do not "simplify" that to `jq` when copying.

Make it executable after copying: `chmod +x <target>/statusline.sh`.

### `settings.json` — add whole if absent, field-level if present

If the file does not exist, copy the template as-is. For a user target, drop
the template's `enabledPlugins` block first (only a project target enables the
project-artifacts plugin), then add the transcript-folds entry described in
"The transcript-folds pieces".

If it exists, queue only the keys that are **missing**. Never change a key that
already has a value: an existing entry may have been deliberately tuned, and
silently retuning someone's harness is the failure mode this whole step exists
to avoid. The keys, and what each is for:

| Key | Value | Why |
|---|---|---|
| `statusLine` | see path note below | points at the script from step 2 |
| `env.CLAUDE_CODE_AUTO_COMPACT_WINDOW` | `"500000"` | raises the auto-compact threshold |
| `outputStyle` | `"Caveman"` | terse replies, same technical content |
| `model` | `"opus"` | main loop thinks and plans on Opus |
| `env.CLAUDE_CODE_SUBAGENT_MODEL` | `"sonnet"` | subagents write code on Sonnet |
| `modelSettings.<Opus ID>.effortLevel` | the step 1 answer, `"medium"` or `"high"` | the main loop's effort |
| `modelSettings.<Sonnet ID>.effortLevel` | the step 1 answer, `"medium"` or `"high"` | the Sonnet effort for the session itself (subagents: see the rule file below) |
| `effortLevel` | `"medium"` | the effort for sessions whose model has no `modelSettings` entry, such as cloud agents, which run Opus; the per-model entries beat it |
| `hooks.SessionStart` | the drift-hook entry, see path note below | runs `hooks/effort_drift.py` at session start |
| `enabledPlugins."<plugin>@<marketplace>"` for each of the 8 plugins: `luismc-agents`, `luismc-artifacts`, `luismc-audits`, `luismc-delivery`, `luismc-docs`, `luismc-project-setup`, `luismc-specs`, `luismc-transcript-folds` | `true`, project target only; marketplace as found below; the plugin list is read from `.claude-plugin/marketplace.json` (see "All plugins") | turns on every plugin of the marketplace for the project (artifacts: ARTIFACTSPEC R10.1; delivery: DELIVERYSPEC D2, it supplies the hooks that enforce the rule tags) |
| `enabledPlugins."luismc-transcript-folds@<marketplace>"` | `true`, user level on every run, in `~/.claude/settings.json` only; marketplace as found below | enables the transcript-folds plugin (see "The transcript-folds pieces") |

**The effort keys are written from the user's answer, not queued as missing.**
They are an explicit choice made this run, so they are written into every
target that gets the model split (the same targets as `model` and
`CLAUDE_CODE_SUBAGENT_MODEL`) even when a different value already exists —
unlike tuning keys. Show the existing value in the summary as
`current → chosen`; when it already equals the answer, there is nothing to
write. Merge into an existing `modelSettings` object and never drop its other
entries.

Key the entries by the model's **canonical ID**, not the alias: the docs do not
document alias keys such as `"opus"` for this setting. Use the IDs the `opus`
and `sonnet` aliases resolve to at the time of the run (today `claude-opus-5-5`
and `claude-sonnet-5-5`); take them from the running session's model
information or `/model`, rather than from memory. The consequence: when an alias
later moves to a new model, the old entry stops applying and the new model
falls back to its default effort. Re-running the skill adds the entry for the
new ID.

If `CLAUDE_CODE_EFFORT_LEVEL` is set in the target's `env` block or in the shell
environment, it overrides both answers for every model. Queue it as a
**conflict**, like the model keys: show where it is set and its value, and let
the user choose in step 3 to remove it (from the `env` block; for the shell
environment, tell them where to unset it) or keep it.

**`model` and `env.CLAUDE_CODE_SUBAGENT_MODEL` are the exception to "never
change an existing value"** — they are policy, not tuning. If one already holds
a conforming value, leave it: any Opus alias or ID (`opus`, `opus[1m]`,
`claude-opus-…`) satisfies `model`, any Sonnet one satisfies the subagent key —
do not rewrite `opus[1m]` to `opus` and lose the 1M context. If one holds a
non-conforming value (e.g. `model: "sonnet"`), queue it as a **conflict**: show
the current and policy values and let the user choose per key in step 3 whether
to replace it. Never replace silently, never skip silently.

**`hooks` merges, it does not queue per key.** Add the template's
`SessionStart` entry when no hook with the identical `command` string is
already registered under `hooks.SessionStart`; if one is, there is nothing to
write. Keep every other event and every other `SessionStart` hook exactly as it
is, and never remove or reorder a hook. Create `hooks` and `hooks.SessionStart`
when they are absent.

**`enabledPlugins` merges, and writes one entry per plugin.** See "All plugins"
below for the plugin list, the marketplace name, the install step and the full
configuration. For a project target, add `"<plugin>@<marketplace>": true` for
every plugin to `enabledPlugins` in the project's `.claude/settings.json`. The
settings template carries the placeholder `{{MARKETPLACE}}` in those keys; it
never reaches a target. Create `enabledPlugins` when it is absent. When a key
for the plugin is already there, with `true` or `false`, leave it exactly as it
is: a `false` is the owner's decision. When the project already names the plugin
under a different marketplace than the one found, queue it as a **conflict**
(the entry would enable nothing on this machine) and let the owner choose in
step 3. Keep every other entry, and never remove or reorder one. A user target
gets no project plugin entry; its only plugin entry is
`luismc-transcript-folds@<marketplace>` in `~/.claude/settings.json` (below).

**The `statusLine` command differs per target and the template only carries the
project form.** Rewrite it for a user-level install:

```
project → bash "$CLAUDE_PROJECT_DIR/.claude/statusline.sh"
user    → bash "$HOME/.claude/statusline.sh"
```

`$CLAUDE_PROJECT_DIR` is only set for a project-scoped config. Copying the
project form into `~/.claude/settings.json` gives a statusline that silently
prints nothing in any directory Claude does not treat as a project root.

**The drift hook's `command` differs per target the same way.** The template
carries the project form; rewrite both occurrences of the path for a user-level
install:

```
project → python3 "$CLAUDE_PROJECT_DIR/.claude/hooks/effort_drift.py" || python "$CLAUDE_PROJECT_DIR/.claude/hooks/effort_drift.py"
user    → python3 "$HOME/.claude/hooks/effort_drift.py" || python "$HOME/.claude/hooks/effort_drift.py"
```

The `|| python` fallback is for machines where `python3` is missing or is only
a stub (common on Windows). The identical-command check above compares the
rewritten string for the target.

### All plugins — project target, every run

**Which plugins.** Read `.claude-plugin/marketplace.json` at the marketplace
root and take every name in `plugins[]`, so a plugin added later is not
forgotten. If the file cannot be read, use the eight names in the table above
and say so in the report. Today that is `luismc-agents`, `luismc-artifacts`,
`luismc-audits`, `luismc-delivery`, `luismc-docs`, `luismc-project-setup`,
`luismc-specs` and `luismc-transcript-folds`. Scope is the project: everything
is turned on in the target's `.claude/settings.json`, not at user level. The one
user-level exception stays `luismc-transcript-folds` plus its two chords (next
section).

**Marketplace name.** Looked up in this order:

1. The suffix after `@` of the entry whose key starts with
   `luismc-project-setup@` in the `enabledPlugins` of the user's
   `~/.claude/settings.json`. This skill is part of that plugin, so the entry is
   how the owner registered the marketplace on this machine.
2. Only when there is no such entry, the `name` in the marketplace file this
   plugin was installed from.
3. If neither can be read, ask the owner for the marketplace name.

**Install.** For each plugin that is not installed on the machine (check with
`claude plugin list`), the change plan lists the command
`claude plugin install <name>@<marketplace>`. Only after the owner confirms it in
the step 3 summary, run it for each missing plugin. If the owner declines, turn
the plugins on only and print the commands for the owner to run. When a command
fails, report it and go on with the rest. Afterwards tell the owner to run
`/reload-plugins` (or restart) so the plugins load. The skill never touches git.

**Configure each plugin that needs a first-run setup.** Plan these in the
change plan, show them in step 3, and run them only after the owner confirms.
Each skips when the plugin is not installed yet; print the command instead.

- **luismc-docs.** In a repo without `docs/docs.json`, run the docs plugin's
  `docs_setup.py init --apply` (it is under `scripts/` in the installed docs
  plugin). In a repo that already has docs, run `docs_setup.py migrate` without
  `--apply` and show its dry-run plan in the summary. Never apply `migrate`
  without the owner saying so.
- **luismc-artifacts.** When `.claude/artifacts.json` is absent, create it with
  `{"record_dir": "docs/project"}`. When `docs/docs.json` exists it names the
  same `record_dir` (DOCSPEC R2.4: both files name the same folder). Do not
  change an existing `.claude/artifacts.json`; if its `record_dir` differs from
  `docs/docs.json`, report it.
- **luismc-delivery.** Write `.delivery/config.json` from
  `assets/delivery-config.json` when absent (caps cloud 20, local 3, total 23,
  and `watcher.ci_workflows` `["ci.yml"]`), as in the `.delivery/config.json`
  section below. When the file is present, leave every key alone except `caps`:
  when an old `caps` value is lower than the template's (for example `total` 5),
  raise it and show `caps.<key>: current → new` in the step 3 summary. Never
  lower a cap.

### The transcript-folds pieces — user level, every run

`luismc-transcript-folds` folds long diffs and finished shell commands in the
transcript into one line each, with a band above the prompt and two toggle
chords. It is part of the standard setup, so on **every run, whatever target was
picked**, the change plan includes these two pieces at user level. Both land
outside the repo and are shown in the step 3 confirmation; if the owner declines
them there, they are skipped and reported as skipped.

**1. `~/.claude/settings.json` `enabledPlugins."luismc-transcript-folds@<marketplace>": true`.**
`<marketplace>` is found exactly as in "All plugins" above. Create the file
or the `enabledPlugins` block when absent. When the key is already there, with
`true` or `false`, leave it exactly as it is: a `false` is the owner's decision.
Keep every other entry. Nothing else in this file changes because of this piece.

**2. `~/.claude/keybindings.json` — merge `assets/keybindings.json`.** The asset
holds the `Global` context with two chords:

| Chord | Action | Does |
|---|---|---|
| `ctrl+x d` | `theme:toggleSyntaxHighlighting` | toggles folded diffs |
| `ctrl+x f` | `theme:editCustom` | toggles folded commands |

Both actions are handled by the engine only inside the `/theme` dialog, so
outside it the chords reach the plugin's buttons. Merge rules:

- If the file is absent, create it from the asset.
- Otherwise find the `Global` context block in `bindings` (add one when there is
  none) and merge per chord. A chord that is absent is added. A chord already
  bound to the same action is already there, so there is nothing to write. A
  chord bound to **another action** is a **conflict**: queue it with the current
  and wanted action and let the owner choose in step 3 whether to replace that
  one binding.
- Never change or remove any other binding, in `Global` or in any other context,
  and never reorder. Keep unknown top-level keys (`$schema` and anything else).
- The file must parse as JSON after the write. A merge that cannot be written
  safely, for example a file that does not parse now, is reported and left
  untouched, never overwritten.

The plugin itself is installed with `claude plugin install
luismc-transcript-folds@<marketplace>`. This skill does not run that; it tells
the owner in step 5. The entry and the chords take effect after
`/reload-plugins` or a restart.

### `output-styles/caveman.md` — add if missing

Copy alongside the `outputStyle` setting; the setting names a style that must
exist as a file or Claude falls back to the default with no error.

### `hooks/effort_drift.py` — overwrite unconditionally

`.claude/hooks/effort_drift.py` (project) or `~/.claude/hooks/effort_drift.py`
(user). Plugin-owned like the statusline: replaced without asking, and a local
edit is drift. Python 3, standard library only. Create the `hooks/` directory
when absent. No `chmod` is needed, because the registered command runs it
through `python3`. See "The alias-drift warning" below for what it does.

### `rules/agents-and-integration.md` — overwrite unconditionally

`.claude/rules/agents-and-integration.md` (project) or
`~/.claude/rules/agents-and-integration.md` (user). Claude Code loads every
`.md` under `rules/` as instructions alongside `CLAUDE.md`, which is why the
agent and integration behaviour lives here and not in `CLAUDE.md`: it reaches
projects whose `CLAUDE.md` already exists and must not be touched. Like the
statusline, this file is plugin-owned policy, so it is replaced without asking
— a local edit to it is drift, and the fix belongs in the template.

The template contains the placeholder `{{SUBAGENT_EFFORT}}`. When writing the
file, substitute the Sonnet effort chosen in step 1 (`medium` or `high`) for
every occurrence; the placeholder never reaches a target. The file tells the
main loop to pass `effort` on each Agent call that launches an implementation
subagent. That is needed on top of the settings entry because the docs do not
say a `modelSettings` entry applies to subagents, while the Agent call's
`effort` parameter is the documented route.

**Remove the old file.** Earlier versions of this skill wrote
`rules/model-delegation.md`. When a target holds that file, delete it, so the
two rule files never contradict each other. Queue it in the change plan as a
**removal**, and list it under "removed" in the step 3 summary. Only that exact
file name is removed, and only from a target being applied.

**The `scripts/delivery/*` paths.** The rule cites
`scripts/delivery/reach_check.py`, `gate_verify.py`, `join.py` and
`ci_watch.py`. Those scripts exist only in repos generated or repaired by
`tech-stack-setup` 12 or later. This skill does not install them; in a repo without them, the cited lines are guidance for
tooling that has not been generated yet. Say so in the step 5 report when the
project target has no `scripts/delivery/` directory.

### `rules/clarifying-questions.md` — overwrite unconditionally

`.claude/rules/clarifying-questions.md` (project) or
`~/.claude/rules/clarifying-questions.md` (user). Part of the standard setup:
written to every target this skill applies, new or existing, on every install
and every re-run, with no question asked. It tells Claude to gather every
clarifying question it needs and ask them all at once, in the questions
interface, instead of guessing or asking a few per turn. Plugin-owned like
`agents-and-integration.md`, and for the same reason a rule file rather than
`CLAUDE.md` text: it reaches projects whose `CLAUDE.md` already exists. A
local edit is drift; the fix belongs in the template. No placeholders.

### `rules/delivery-timing.md` — overwrite unconditionally

`.claude/rules/delivery-timing.md` (project) or `~/.claude/rules/delivery-timing.md`
(user). Plugin-owned like the two rule files above and written on every run, no
question asked, no placeholders. It carries the ETA and train-timing rules (ETA =
real start + typical duration with the dependency named; the next train is joined
during CI and pushed at green; waits are gaps; trains leave when green at any
hour; agent ETAs are setup + work + checks). Every rule line in the three rule
files ends with `<!-- check: <DL id or Q id> -->` naming the DELIVERYSPEC id that
enforces it, or `<!-- advice -->`; `tools/test_rule_tags.py` fails on an id the
spec does not define.

### `.delivery/config.json` — project target, add if missing, NEVER overwrite

Per-project settings for the `luismc-delivery` plugin, from
`assets/delivery-config.json`. Written to `<repo>/.delivery/config.json` only when
the file is absent; an existing file is the owner's and is left exactly as it is
(report keys the template has that it lacks, and change nothing) except
`caps`: a value lower than the template's is raised, after the summary shows
`current → new` (see "All plugins"). Keys: `caps`
(`cloud`, `local`, `total`), `work_root`, `tz`, `train_label_re`,
`release_branch_re`, `brief_markers`, `min_question_chars`, `eta_table`,
`heavy_commands`, `outbound_deny`, `no_attribution`, `long_pole_globs`,
`measure_globs`, `update_state_files`, `watcher_interval_s`. The defaults are
neutral (no work root, UTC, no attribution rule). Strip every key that starts
with `_` (the template's `_doc` and `_example_windows_monorepo`) when writing.

Ask once in step 1 whether to fill the project's values; for a Windows monorepo
the documented example is `work_root` `C:\\Work`, `tz` `Europe/Lisbon`, `caps`
8/3/5 (cloud/local/total; an existing smaller cap is raised to 20/3/23 on the next run, which the owner can decline), and `no_attribution` `true`, which makes the
`commit-msg` hook that `tech-stack-setup` installs refuse `Co-Authored-By` and AI
attribution trailers (DL-74). Without the answer, write the neutral defaults.

Add `.delivery/` to the project's `.gitignore` in the same change (the ledger,
suite times and watcher state live there and are per machine). Append the line
only when no line already ignores it; create the file when absent. The
`config.json` itself is local too: it is ignored with the folder, so the
template is the shared record.

### Retire the user-level `no-tomorrow.mjs` Stop hook

The delivery plugin's Stop hook ports `~/.claude/hooks/no-tomorrow.mjs` (DL-31),
so once `luismc-delivery` is enabled the old hook only duplicates it. When
`~/.claude/hooks/no-tomorrow.mjs` exists, or `~/.claude/settings.json` or
`~/.claude/settings.local.json` holds a `hooks.Stop` entry whose command names
`no-tomorrow.mjs`, report it, and queue **only the settings entry** as a
**removal**, shown in the step 3 summary for confirmation. Remove that one hook
entry (and its `Stop` matcher group when it becomes empty), keep every other
hook, and leave the `.mjs` file in place for the owner to delete. Do nothing
when the plugin is not enabled in the target being applied.

### Memory-to-rule map (DELIVERYSPEC D7) — report only

After a lesson is enforced under a DL or Q id, its memory note is redundant. This
skill only reports; it never edits or deletes a memory file. Read the target
project's memory folder, `~/.claude/projects/<project>/memory/*.md` (`<project>` is
the repo path with separators replaced by `-`, e.g. `C--GitHub-my-app`),
and for each file name the DL/Q ids from DELIVERYSPEC section 1 and decision D8
whose rule it states, judging by the note's content against each rule's text (the
spec's "Source" column only says "owner lesson", never a note's name). Show a table
in the step 3 summary:

| Memory file | Enforced by (DL / Q ids) | Delete? |
|---|---|---|
| `no-auto-merge.md` | DL-05, DL-06 | yes, after the plugin release |
| `some-other-note.md` | none | no, keep |

A file maps only when every rule in it has an id; a partly covered note is listed
with the covered ids and marked "keep (partly covered)". The orchestrator deletes
the mapped files after the plugin release. Skip the table when the folder is
absent and say so.

### `CLAUDE.md` — add if missing, NEVER overwrite

Instructions loaded into every session: `CLAUDE.md` at the repo root for a
project target, `~/.claude/CLAUDE.md` for a user target.

**If it exists, leave it alone entirely.** Do not overwrite it, do not merge into
it, do not append. This file is hand-written prose whose whole value is that
someone chose every line — a user-level `~/.claude/CLAUDE.md` in particular is
usually well-developed and may `@`-include other files. Losing it is
unrecoverable from this plugin's side. Report it as already present and move on.

If the user explicitly asks to *add* the template's guidance to an existing
`CLAUDE.md`, show them the template text and let them place it themselves rather
than editing the file for them.

If the target repo has its own `AGENTS.md` and `CLAUDE.md` does not reference it,
offer to add the `@AGENTS.md` line — that is a real convenience, but only when
the file it points at actually exists.

## Step 3 — Present one batch summary and confirm once

Group every queued change by target and by file: what is being added, what is
being overwritten unconditionally, what is being removed (a target's old
`rules/model-delegation.md`), and which individual settings keys are being
added, including the `hooks.SessionStart` entry and, for a project target, the
`enabledPlugins` entry for each of the 8 plugins (or that it is already there). For a project target also list: the plugins to install with `claude plugin install <name>@<marketplace>` (asking for confirmation), the docs setup (`init --apply`, or the `migrate` dry-run plan), the artifacts record (`record_dir` `docs/project`), the `caps` changes as `current → new`, the new `.delivery/config.json` and `.gitignore` line, `rules/delivery-timing.md`, the proposed removal of a `no-tomorrow.mjs` Stop entry (which lives in the user's settings, so state it lands outside the repo), and the memory-to-rule table. Always list, under the user target, the two transcript-folds
pieces: the `luismc-transcript-folds@<marketplace>` entry (or that it is already
there) and the chords to add to `~/.claude/keybindings.json` (or that they are
already there, or that the file will be created). List each model-split
conflict separately as `key: current → policy`, and each chord bound to another
action as `chord: current action → wanted action`. List the two effort keys per
target as `modelSettings.<ID>.effortLevel: current → chosen` (`none → chosen`
when absent), and any
`CLAUDE_CODE_EFFORT_LEVEL` conflict with where it is set. Ask for one
confirmation: apply everything (conflicts included), apply a named subset, or
cancel.

State plainly which writes land outside the repo. If the user declines part of
it, leave those files untouched and report them as skipped — never quietly drop
a piece because the rest succeeded.

## Step 4 — Apply, then verify

Apply what was confirmed, then check the result rather than assuming it worked:

- `settings.json` parses as JSON after editing. A merge that produces invalid
  JSON makes Claude Code ignore the whole file, which looks exactly like the
  settings not having been applied.
- `statusline.sh` is executable.
- The path in `statusLine.command` resolves for the target you wrote.
- Every target that got the model split has `model` resolving to Opus,
  `env.CLAUDE_CODE_SUBAGENT_MODEL` resolving to Sonnet, and
  `rules/agents-and-integration.md` present — or the conflicting key is
  listed as declined. A project `model` key shadows the user one, so a project left on a
  declined non-Opus value defeats a user-level enforcement; say so.
- Every target that got the split has both `modelSettings` entries, under the
  canonical IDs, with the value `medium` or `high`.
- The target's settings contain a top-level `effortLevel` (unless an existing
  value was left alone) and still parse as JSON.
- The written `rules/agents-and-integration.md` contains no
  `{{SUBAGENT_EFFORT}}` placeholder and names the chosen Sonnet effort.
- No `rules/model-delegation.md` remains in a target that was applied.
- Every applied target has `rules/clarifying-questions.md`, identical to the
  template.
- Every target that got the split has `hooks/effort_drift.py`, and its
  `hooks.SessionStart` holds the command for that target (project form
  with `$CLAUDE_PROJECT_DIR`, user form with `$HOME`), once, next to any
  hooks that were already there.
- A project target's `enabledPlugins` holds `luismc-delivery@<marketplace>`, `.delivery/config.json` parses as JSON with none of the `_` keys, `.gitignore` ignores `.delivery/`, every applied target has `rules/delivery-timing.md` identical to the template, and no `hooks.Stop` entry naming `no-tomorrow.mjs` remains unless the removal was declined.
- A project target's `enabledPlugins` holds an entry for every plugin in the
  marketplace file (`true`, or the owner's existing value), next to every entry
  that was there before, with no `{{MARKETPLACE}}` left in the file, and the
  file still parses as JSON.
- Each plugin that was confirmed for install shows in `claude plugin list`, or
  its failure is reported.
- `.claude/artifacts.json` parses and names `record_dir` `docs/project` (or the
  owner's existing value), and `docs/docs.json`, when present, names the same.
- `.delivery/config.json` has `caps` at least cloud 20, local 3, total 23.
- `~/.claude/settings.json` holds `enabledPlugins."luismc-transcript-folds@<marketplace>"`
  (`true`, or the owner's existing value), next to every entry that was there
  before, and still parses as JSON.
- `~/.claude/keybindings.json` parses as JSON, its `Global` context binds
  `ctrl+x d` to `theme:toggleSyntaxHighlighting` and `ctrl+x f` to
  `theme:editCustom` (or the conflicting chord is listed as declined), and every
  binding that was there before is unchanged.
- No `CLAUDE_CODE_EFFORT_LEVEL` remains in the target's `env` block, unless the
  user chose to keep it — then say it overrides the saved efforts.
- The split takes effect from the next session; the current one keeps the
  model it started with (`/model` switches it now).

## Step 5 — Report

What was applied, per target. What already had a value and was therefore left
alone — that list matters, because "already set" and "just set by me" look
identical afterwards. What the user declined, including any model-split
conflict left in place. Whether the model split is now enforced for this
project only or for all projects. The effort chosen for each model (Opus main
session, Sonnet subagents) and where it was written, and the top-level
`effortLevel` (added as `medium`, or the existing value left alone) that cloud
agents fall back to. Which of the 8 plugins were enabled for the project, which were installed, and which install commands the owner still has to run, with the marketplace name used and where it came from; tell the owner to run `/reload-plugins`. What was configured for docs (init applied, or the migrate plan shown and left unapplied), the artifacts record, and the delivery `caps` changes. Whether the
`luismc-transcript-folds` entry and the two chords were added, already there or
declined, the marketplace name used for it, and that the plugin must be installed
(`claude plugin install luismc-transcript-folds@<marketplace>`) and that the
chords and the plugin take effect after `/reload-plugins` or a restart. Anything
removed (the old
`model-delegation.md`), and whether the project has `scripts/delivery/`, which
the rule file cites. Whether `.delivery/config.json` was written or already present, the `no-tomorrow.mjs` entry removed or declined, and the memory-to-rule table for the orchestrator. If both targets were
written, note which keys the project file now shadows.

## The alias-drift warning

Per-model effort is saved under the model's canonical ID. The `opus` and
`sonnet` aliases move to new IDs over time, and then the new model has no
saved effort and quietly runs at its default. `hooks/effort_drift.py` is a
`SessionStart` hook that says so.

**What it reads.** Claude Code passes a SessionStart hook a JSON object on
stdin with `source` and, optionally, `model`, the active model identifier
(documented at https://code.claude.com/docs/en/hooks, "SessionStart input").
The field can be missing, for example after `/clear`. The docs also say there
is no `$CLAUDE_MODEL` variable and that `$ANTHROPIC_MODEL` does not follow
`/model`, so `model` from stdin is the only reliable source of the session's
model.

**What it checks.** The model is checked when its ID names Opus or Sonnet,
the two models this skill saves an effort for. Other models never warn. The
hook looks for `modelSettings.<ID>.effortLevel` in `~/.claude/settings.json`,
the project's `.claude/settings.json` and `.claude/settings.local.json`; an
entry in any of them counts. A `[1m]`-style suffix is ignored.

**Fallback.** When `model` is absent, it checks the IDs in the
`ANTHROPIC_DEFAULT_OPUS_MODEL` and `ANTHROPIC_DEFAULT_SONNET_MODEL` variables,
when they are set. With no `model` and no variables there is nothing to
compare, and the hook stays silent.

**What it cannot detect.** A model switched with `/model` after the session
started (it runs at session start only). An alias that moved when none of the
inputs above carry the new ID. An effort overridden by
`CLAUDE_CODE_EFFORT_LEVEL`, `--effort` or `/effort`; it only tests that an
entry exists, not that it applies. A saved entry that holds a value the user
no longer wants.

**Output.** It prints a `systemMessage` JSON object, which Claude Code shows
to the user, and exits 0. Plain stdout would go to Claude's context instead,
which is not wanted here. It never blocks and swallows its own errors. The
message tells the user to re-run `/luismc-project-setup:claude-setup`.

**Disable.** Set `CLAUDE_SETUP_EFFORT_DRIFT` to `off` in the settings `env`
block or the shell, or delete the `SessionStart` entry that runs it. Deleting
only the entry is not durable: the next run of this skill adds it back. To
keep it off, set the variable.

## Per-skill model profiles

`assets/model-profiles.json` is the single source of truth for which model and
effort each skill in this marketplace runs at, in three groups: `judgment`
(Opus, medium: specs, audits, stack setup, auth, writing a feature artifact),
`mechanical` (Sonnet, medium: checks and task bookkeeping, the other artifacts
skills) and `setup` (Sonnet, medium: this skill). Every profile is medium,
the owner's default for both models. Every
skill's `model:` and `effort:` frontmatter must match its group; this skill's
own frontmatter does. `tools/test_model_profiles.py` enforces that, so change
the JSON first and the skill files after. The file is not copied to a target
and nothing here applies it to a user's settings.
