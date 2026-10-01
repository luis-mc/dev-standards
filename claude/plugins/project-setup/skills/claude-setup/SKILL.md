---
description: Apply Claude Code configuration — statusline, settings.json (auto-compact window, output style, Opus-plans/Sonnet-codes model split), output styles, rules, and CLAUDE.md — to this project and/or the user-level ~/.claude/. Use when the user asks to set up Claude, configure the statusline, fix their Claude settings, add a CLAUDE.md, or apply their Claude config to a repo or a new machine, or invokes /luismc-project-setup:claude-setup. Not for repo or product tooling (hooks, gitleaks, CI, playwright) — that is /luismc-project-setup:tech-stack-setup.
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

## The model split this skill enforces

Every project this skill touches gets the same division of labour: the **main
session runs on Opus** and does the thinking — understanding, planning,
designing, reviewing — and **subagents run on Sonnet** and write the code. Three
pieces carry it, and all three are needed:

| Piece | Enforces |
|---|---|
| `settings.json` `model: "opus"` | the main loop's model |
| `settings.json` `env.CLAUDE_CODE_SUBAGENT_MODEL: "sonnet"` | the default model of every subagent that does not pin its own |
| `.claude/rules/model-delegation.md` | the behaviour — the main loop actually hands implementation to subagents instead of writing it itself |

Settings alone only pick models; without the rule the Opus session would still
write all the code itself and the Sonnet default would rarely be exercised.
The rule alone is advice with nothing behind it. Agents whose definition pins a
model (e.g. `luismc-agents:architect` → `opus`) keep it: a frontmatter `model`
takes precedence over `CLAUDE_CODE_SUBAGENT_MODEL`, which is the intent —
judgment-call agents stay on Opus. Forked subagents always inherit the parent's
model; that is acceptable, since a fork is for continuing the parent's
reasoning, not for implementation.

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
`~/.claude/settings.json` (`model`, `env.CLAUDE_CODE_SUBAGENT_MODEL`) and
`~/.claude/rules/model-delegation.md`? Ask it even when the user chose
**project** only — the project target always gets the split; this question is
whether every other repo on the machine does too. A "yes" adds just those three
pieces to the user target (not the statusline, output style or CLAUDE.md, unless
the user also picked **user** or **both**). A "no" leaves `~/.claude/` untouched.
Skip the question only when the user already picked **user** or **both**,
since the split is then applied there anyway.

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

If the file does not exist, copy the template as-is.

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

**`model` and `env.CLAUDE_CODE_SUBAGENT_MODEL` are the exception to "never
change an existing value"** — they are policy, not tuning. If one already holds
a conforming value, leave it: any Opus alias or ID (`opus`, `opus[1m]`,
`claude-opus-…`) satisfies `model`, any Sonnet one satisfies the subagent key —
do not rewrite `opus[1m]` to `opus` and lose the 1M context. If one holds a
non-conforming value (e.g. `model: "sonnet"`), queue it as a **conflict**: show
the current and policy values and let the user choose per key in step 3 whether
to replace it. Never replace silently, never skip silently.

Do **not** write an `enabledPlugins` block. Enabling and disabling plugins is
the user's call per project, made through `/plugin` or their own settings — not
something this skill decides on their behalf.

**The `statusLine` command differs per target and the template only carries the
project form.** Rewrite it for a user-level install:

```
project → bash "$CLAUDE_PROJECT_DIR/.claude/statusline.sh"
user    → bash "$HOME/.claude/statusline.sh"
```

`$CLAUDE_PROJECT_DIR` is only set for a project-scoped config. Copying the
project form into `~/.claude/settings.json` gives a statusline that silently
prints nothing in any directory Claude does not treat as a project root.

### `output-styles/caveman.md` — add if missing

Copy alongside the `outputStyle` setting; the setting names a style that must
exist as a file or Claude falls back to the default with no error.

### `rules/model-delegation.md` — overwrite unconditionally

`.claude/rules/model-delegation.md` (project) or
`~/.claude/rules/model-delegation.md` (user). Claude Code loads every `.md`
under `rules/` as instructions alongside `CLAUDE.md`, which is why the
delegation behaviour lives here and not in `CLAUDE.md`: it reaches projects
whose `CLAUDE.md` already exists and must not be touched. Like the statusline,
this file is plugin-owned policy, so it is replaced without asking — a local
edit to it is drift, and the fix belongs in the template.

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
being overwritten unconditionally, and which individual settings keys are being
added. List each model-split conflict separately as `key: current → policy`.
Ask for one confirmation: apply everything (conflicts included), apply a named
subset, or cancel.

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
  `rules/model-delegation.md` present — or the conflicting key is listed as
  declined. A project `model` key shadows the user one, so a project left on a
  declined non-Opus value defeats a user-level enforcement; say so.
- The split takes effect from the next session; the current one keeps the
  model it started with (`/model` switches it now).

## Step 5 — Report

What was applied, per target. What already had a value and was therefore left
alone — that list matters, because "already set" and "just set by me" look
identical afterwards. What the user declined, including any model-split
conflict left in place. Whether the model split is now enforced for this
project only or for all projects. If both targets were written, note which keys
the project file now shadows.
