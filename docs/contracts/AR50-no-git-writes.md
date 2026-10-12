# AR50 contract: the plugin never commits or pushes (ARTIFACTSPEC 1.8.0, luismc-artifacts 1.8.0)

Owner's decision (12 Oct): the plugin imposed commits and pushes to the default
branch on every project, which triggered paid deploys (Vercel) on every record
change. From 1.8.0 the plugin **writes files only**. The project decides when to
commit and push anything.

## Rules (binding)

1. **No git write, ever.** No script or hook of the plugin runs `git commit`, `push`,
   `fetch`, `pull`, `reset`, `rebase`, `checkout`, `switch`, `stash`, `add`,
   `worktree add` or `worktree remove`, and no `gh` command that writes. Allowed git calls
   are read-only: `rev-parse`, `symbolic-ref`, `status`, `diff`, `log`, `show`,
   `ls-files`, `config --get`, `worktree list`.
2. **The record lives in the session's working tree**: `<repo root>/docs/artifacts/`
   (repo root = `git rev-parse --show-toplevel` of the current directory). Every
   writing command validates, applies, renders and writes the files there and stops.
   They stay uncommitted. Nothing is synced from `origin` before a change.
3. **The record worktree is retired.** The `worktree` command prints the record directory
   (`<root>/docs/artifacts`). `LUISMC_ARTIFACTS_WORKTREE` and `record_worktree` in
   `.claude/artifacts-local.json` are ignored (and `check` says so once, as info,
   not a finding).
4. **Migration, once, automatic:** when the old record worktree exists (default
   `<root>/.claude/worktrees/artifacts-record`, or the old setting) and its
   `docs/artifacts/registry.json` is newer than the working tree's (by the registry's
   newest `changed` stamp, or the working tree has none), copy its `docs/artifacts/`
   files into the working tree's `docs/artifacts/`. Then say, once: `luismc-artifacts:
   the record now lives in docs/artifacts/ and is never committed or pushed by the
   plugin; copied it from <old path>. You may remove that worktree with git worktree
   remove <path>`. The plugin never removes it itself.
5. **Commands `commit` and `push` are removed.** Calling them exits 1 with
   `the plugin no longer commits or pushes (ARTIFACTSPEC 1.8.0); commit docs/artifacts/ when you choose`.
   `--push`, `--no-push` and `commit --retry` are accepted on writing commands for
   compatibility and do nothing (`--push` prints the same note to stderr).
   Exit codes 3 and 4 are no longer used.
6. **Hooks:**
   - `hook_before_command.py`: no record push before `gh pr create/ready/merge`. If the
     hook does nothing else, it exits 0 and prints nothing.
   - `hook_end_of_turn.py`: no push. The publish gate and background-work checks are unchanged.
   - `pending`: no push before it lists.
   - The session-start hook does no sync/fetch/reset. It runs the migration of rule 4
     when it applies.
7. **Locking stays** (a file lock under `<root>/.claude/`, git-ignored path, as today
   if it already lives there; else `docs/artifacts/.lock` must be avoided: the lock
   may not be a file under `docs/artifacts/`).
8. Rendering, validation, IDs, statuses, publishing bookkeeping (`mark-published`,
   `mark-deferred`, `mark-deleted`) are unchanged apart from writing in place.

## Text to change

- `references/artifactspec.md`: version 1.8.0 with a "Changes in 1.8.0" note. Rewrite
  R4.13 to R4.17 and R4.24 to R4.29 to the rules above, and R7.6, R8.16 and R8.17,
  keeping their IDs (a retired rule says `Retired in 1.8.0:` + one line). Add D-row:
  "Does the plugin commit or push? No: it writes files; the project commits."
- `plugin.json` version 1.8.0, description says ARTIFACTSPEC 1.8.0 and that the record
  is written, never committed or pushed. `marketplace.json` version if it holds one.
- Skills (`skills/*/SKILL.md`), `rules/project-artifacts.md`, README text: drop every
  "commits", "pushes", "record worktree", "push comes at the end of the turn", and
  name `docs/artifacts/` in the working tree as where the record is.
- Labels that say "ARTIFACTSPEC 1.7.0" in code or rule text say 1.8.0.
- `tools/change-notes.json`: an entry for luismc-artifacts 1.8.0 in the existing format.

## Tests

- `tools/test_project_artifacts.py`: every writing command leaves `git log` and the
  remote unchanged and the files changed under `<root>/docs/artifacts/`; `commit`/`push`
  exit 1 with the message; migration copies once and only when newer.
- `tools/test_project_artifacts_hooks.py`: no hook runs a git write (stub `git` on PATH
  or a spy that fails on any write subcommand); before-command hook is silent for
  `gh pr create`.
- Delete tests of push retries, races, protection refusal, rebase of unpushed commits.
