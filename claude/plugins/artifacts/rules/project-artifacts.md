# Project artifacts

- Record work as a task before starting it.
- Start branch names with the task ID.
- Change status only with `set-task-status`.
- Publish Full Progress once, at the end of the turn, never mid-turn; feature artifacts are files in the repo (`docs/artifacts/feature-<slug>.html`) and are never published.
- Never type a status row by hand.
- Put every doc under `docs/`.
- Every activity is a task before it starts, whoever does it: work given to agents and the session's own (contracts, specs, reviews, joins, test runs, releases, deploys, cleanup).
- A task is Running while any work for it runs; Waiting or Needs you when blocked on something or someone.
- Built means the work is finished but not released; release work still to come (join, CI, release) is its own task, Running or To do.
- Before ending a turn that leaves work running in the background, its task is Running.
- When the owner chooses between options (designs, approaches, names), record every option offered and the one chosen in the feature's `decisions.json`, in the same turn; an option the owner has not chosen yet is an open decision.
- Old claude.ai pages of feature artifacts are deleted only with the owner's confirmation: when pending lists retired pages, ask the owner, delete each confirmed one with the Artifact tool, then run mark-deleted.
