# DS73 report: machine load limits

Status: in progress. Branch DS73-load-limits. The plugin version and the spec version are not bumped; a change note is added instead.

Owner rule (23 Oct 2026): no memory above 85%, no CPU above 60%; run as many jobs as fit inside that. Enforced by the plugin, not by a memory note.

## Plan
1. `load.py` measurement, cache, limits.
2. PreToolUse refusal of heavy work and local agent launches; Stop/SessionStart notice.
3. `runner_load_gate.py` for self-hosted runners + doctor check.
4. Spec (DL-77, DL-78), schema, README, change note, tests.

(Filled in as each step lands.)
