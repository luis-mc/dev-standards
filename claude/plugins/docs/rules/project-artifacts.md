# Project artifacts

- Record work as a task before starting it. <!-- advice -->
- Start branch names with the task ID. <!-- advice -->
- Change status only with `set-task-status`. <!-- check: claude/plugins/artifacts/scripts/project_artifacts.py#cmd_set_task_status -->
- Publish Full Progress once, at the end of the turn, never mid-turn; feature artifacts are files in the repo (`docs/artifacts/feature-<slug>.html`) and are never published. <!-- check: claude/plugins/artifacts/scripts/hook_end_of_turn.py#build_reason -->
- Never type a status row by hand. <!-- advice -->
- Put every doc under `docs/`. <!-- advice -->
- The record is written to `docs/artifacts/` (or the project's `record_dir` setting) in the working tree; the plugin never commits or pushes it, the project commits when it chooses. <!-- advice -->
- Every activity is a task before it starts, whoever does it: work given to agents and the session's own (contracts, specs, reviews, joins, test runs, releases, deploys, cleanup). <!-- advice -->
- A task is Running while any work for it runs; Waiting or Needs you when blocked on something or someone. <!-- advice -->
- Built means the work is finished but not released; release work still to come (join, CI, release) is its own task, Running or To do. <!-- advice -->
- Before ending a turn that leaves work running in the background, its task is Running. <!-- check: claude/plugins/artifacts/scripts/hook_end_of_turn.py#build_background_reason -->
- When the owner chooses between options (designs, approaches, names), record every option offered and the one chosen in the feature's `decisions.json`, in the same turn; an option the owner has not chosen yet is an open decision. <!-- advice -->
- Old claude.ai pages of feature artifacts are deleted only with the owner's confirmation: when pending lists retired pages, ask the owner, delete each confirmed one with the Artifact tool, then run mark-deleted. <!-- check: claude/plugins/artifacts/scripts/hook_end_of_turn.py#retired_message -->
- When you give an Expected time, give its basis too (what it waits on and how long). <!-- advice -->
- A release's Expected is the end of its last phase (`--phase`); name any risk with `--risk` instead of padding it. <!-- advice -->
- Every Running or Built task rides a release (`--rides`); `--release` gives a release its RELEASE-n number. <!-- check: claude/plugins/artifacts/scripts/project_artifacts.py#release_problems -->
- A task that ships nothing (a publish, a study, a cleanup) says so with `--no-release REASON` instead of riding a release; it goes Live, never Built. <!-- check: claude/plugins/artifacts/scripts/project_artifacts.py#release_problems -->
- If claude.ai refuses the publish for its daily limit, run `mark-deferred full-progress --until <reset time>` instead of retrying. <!-- check: claude/plugins/artifacts/scripts/project_artifacts.py#cmd_mark_deferred -->
