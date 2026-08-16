---
description: Apply Claude Code configuration — statusline, settings.json (auto-compact window, output style), output styles, and CLAUDE.md — to this project and/or the user-level ~/.claude/. Use when the user asks to set up Claude, configure the statusline, fix their Claude settings, add a CLAUDE.md, or apply their Claude config to a repo or a new machine, or invokes /luismc-project-setup:claude-setup. Not for repo or product tooling (hooks, gitleaks, CI, playwright) — that is /luismc-project-setup:tech-stack-setup.
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
added. Ask for one confirmation: apply everything, apply a named subset, or
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

## Step 5 — Report

What was applied, per target. What already had a value and was therefore left
alone — that list matters, because "already set" and "just set by me" look
identical afterwards. What the user declined. If both targets were written, note
which keys the project file now shadows.
