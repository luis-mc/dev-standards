# DL189 report

Base check: plugin.json version 1.25.0 (ok).

## Fix
ci_tool.py tool_dir, kind 'file': out = base / plat / _exe(bin or name, plat); parent folder created; atomic partial copy and chmod kept. Returned bin folder is the platform folder. No new helper, no renamed function.

## Callers
Only tool_dir itself and the CLI 'tool' command use it (same file); both follow the returned path, no change needed. The only other '<plat>-' name is in gitleaks() (line ~175, separate function, outside my scope, same pattern; archive-style, not affected by argv[0]). Follow-up: give gitleaks the same layout if wanted.

## Tests
- test_dl189_ci_tool_file_name: 5 OK
- test_ds199_tool_fetch 13 OK, test_dl115_ci_tool 9 OK, test_ds205_zig_pin 4 OK, test_dl116_fetch_check 15 OK
- tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- New test is covered by spec-lint's unittest discover of claude/plugins/delivery/tests; branch advice: light.
- spec-lint run 42933896243 (areas=delivery,docs), all jobs ended: all success except "docs check" = failure, only W1 (docs/work report on branch, expected, stripped before join). Skipped: change notes, change notes folded, shard job, transcript folds, artifact renderer, specs/templates, model profiles. M1 answered by commit message "Docs: none, cache path fix; the feature note covers it".

## Docs
Feature note docs/features/delivery/changes/DL189.md; change note docs/architecture/changes/DL189-ci-tool-file-name.md.

Branch head: ac7cab7 (plus this report commit)

READY
