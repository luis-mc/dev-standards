# DP4 report: the 12 'boom' PostToolUse crashes

Verdict: test noise, not a real bug.

- Source: `test_internal_error_still_exits_zero` in `claude/plugins/delivery/tests/test_post_tool.py` makes `handle` raise `RuntimeError("boom")` on purpose.
- Cause: it fed stdin `{}` with no `cwd`. `hook_post_tool._log_failure` then found the root from the process cwd, the real repository, and appended a line to the real `.delivery/blocks.log` each run.
- Evidence: all 12 log lines have an empty command and read `RuntimeError: boom` (31 Oct to 11 Nov).
- Fix: the test now passes a temp root as `cwd` and asserts the line lands in that root's log. `hook_post_tool.py` is unchanged; its logging is correct.
- Tests: `test_post_tool` runs 67 tests, all OK. The 12 old lines remain in the real log; they are harmless and the owner can delete them.
- Change note: `docs/features/delivery/changes/DP4.md` (names `claude/plugins/delivery/.claude-plugin/plugin.json`; no version edit).
