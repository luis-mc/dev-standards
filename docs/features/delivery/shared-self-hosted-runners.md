---
title: Shared CI on your machine
type: explanation
---
# Shared CI on your machine

The delivery plugin no longer owns the machine layer. The CI slots, the host load file, the load guard, the runner hooks and the Linux pool are removed from it (task DS246). Another project owns machine limits now.

This page keeps the parts that still apply to the plugin: how CI runs show in Full Progress, the CI runs file, and the setup pattern. Section numbers stay fixed, so notes that cite them still resolve. The removed sections are gone, not renumbered.

To set up CI for a project, follow the [setup guide](../../guides/set-up-ci.md).


### 11. CI runs in Full Progress (D48)

A new foldable section in every project's Full Progress page, folded by default.

- **Summary line:** runs in progress, the number of finished runs shown, median run time, fallbacks, failures.
- **Figures:** median and p90 run time, fallbacks to the cloud, passed out of shown.
- **In progress:** run, why, where, started, and now (the current step, or "waiting for a runner").
- **Latest 20 finished:** result, run, why, where, total time, finish time. Each row opens to a bar per step: GitHub queue, then every job step; a failed step is marked.
- **Why** is the trigger: ready PR, push to the default branch, agent branch, schedule, re-run by the owner, or a fallback with its wait.
- **Where** is the runner kind and name: Linux pool, Windows service, GitHub-hosted, Claude cloud.
- The approved sample is the "New in Full Progress: CI runs" section of the Shared CI Plan page.

Data:

- Runs, jobs and step times: the GitHub Actions API (`actions/runs`, `actions/runs/{id}/jobs`, whose steps carry `started_at` and `completed_at`).
- Where: the job's `runner_name` and `labels`; for a cloud session, the `ci-claim` marker's holder.


### 12. Interfaces

Only the CI runs file is left.

#### 12.5 CI runs file (C)

`ci_runs.py collect --root .` writes `.delivery/ci-runs.json` (git-ignored):

```json
{"generated_at": "...", "repo": "owner/name",
 "active": [{"run_id": 1, "workflow": "CI", "why": "ready PR #141", "where": {"kind": "pool|windows|hosted|cloud", "name": "..."},
             "started_at": "...", "now": {"step": "Unit tests", "since": "..."} }],
 "finished": [{"run_id": 1, "workflow": "CI", "conclusion": "success|failure|cancelled", "why": "...", "where": {...},
               "queued_s": 12, "total_s": 600, "completed_at": "...",
               "steps": [{"job": "unit", "name": "Unit tests", "start_s": 82, "duration_s": 165, "conclusion": "success"}]}]}
```

The watcher refreshes it each tick (at most once a minute). The Full Progress renderer reads it when it exists and draws section 11; with no file it draws nothing.


### 13. Setup pattern for every plugin setup (owner request, 4 Nov 2026)

Every setup in dev-standards (the delivery CI setup, `claude-setup`, `docs-setup`, `design-system-setup`, `tech-stack-setup`, `auth-setup`) follows the same pattern, so a user always knows what is happening and what to do next.

1. **Plan first.** Before changing anything, show one plan: what it will install, configure and write (with paths), what it changes outside the repository, what needs the user (a yes, an administrator shell, a sign-in, a web setting, a secret), and about how long it takes.
2. **Do the heavy lifting.** After a yes, the setup runs every install and configuration it can itself. It leaves to the user only what it cannot do (an elevated shell, a setting only in a web page, a secret). Each of those has exact steps, and the setup checks it afterwards.
3. **Say each step.** One line per step while it runs: what it is doing, then done, or failed with the reason and the fix.
4. **Finish with a summary** in three parts: *Done* (what changed, with paths), *Left for you* (numbered, exact steps), and *What you can do now* (the commands and features now available, each with a one-line example).
5. **Safe to run again.** A second run says what is already set and changes only what is missing.

| Agent | Applies it to |
|---|---|
| D (DL33) | the five skill setups above and the delivery part of `claude-setup` |
