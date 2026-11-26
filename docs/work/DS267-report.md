# DS267 report

Branch DS267-record-local-agents. DL-123 (record local agents from the prompt, Stop hook closes finished rows), DL-124 (Running with no agent or CI: warn only), R5.81.

No hook sees a local agent end (no SubagentStop hook), so the Stop hook closes a running local row when its worktree or output file is gone or it is older than twice its eta (default 60 min).

Tests: test_ds267_record_local_agents (15), plus test_post_tool, test_stop, test_dl151, test_dl156, test_dl171: 121 OK.

docs_check: one K1 error (docs/guides/set-up-ci.md anchor 13-ci-options), not from this branch.
