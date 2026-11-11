# SO7 report

Base check: branched from origin/main 85c5d72; the asset rule file exists.

## What changed
- `clarifying-questions.md` lines 2-4 now end `<!-- check: Q-1 -->`, `Q-1`, `Q-2`. Lines 5-6 were already Q-3, Q-4.
- Same fix in `claude/plugins/delivery/rules/clarifying-questions.md`. It is the canonical text, and `test_questions.py` requires the asset to be a byte copy, so both must change together. (Outside the owned list.)
- The other two asset rule files (agents-and-integration, delivery-timing) had no path-for-ID mistake.
- `tools/test_rule_tags.py`: in rule files that ship to projects (`delivery/rules/` and the claude-setup `assets/.claude/rules/`), every check tag must be rule IDs; a path fails. New self-tests cover this. `delivery/rules/clarifying-questions.md` is now in the expected list.
- `tools/test_questions_stop.py` (outside the owned list, task SO6's test): it demanded `questions_stop.py` in the rule text, which is what pushed the paths into the tags. It now checks for the Q-1 and Q-2 tags instead.
- Change notes: `SO7-rule-tag-q-ids.md` (project-setup) and `SO7-rule-tag-q-ids-delivery.md` (delivery).

## Why the test missed it
The tag test accepted any `check:` path that exists in the repo, and the hook file exists. Only tags starting with an ID were checked as IDs. Also, the `questions_stop` test required the hook path in the rule text, so the two tests pulled in opposite directions. `docs/rules/project-artifacts.md` still uses `path#function` tags on purpose; they name code, so I left them.

## Tests
- Before the fix: the full `tools/test_rule_tags.py` run was refused by the local session guard (heavy suite). I ran the new `problems()` check on the old files instead: it reported lines 2-4 of both rule files ("check tag is not a rule ID").
- `python3 tools/test_rule_tags.py`: PASSED, 74 rule lines in 5 files, 74 tagged.
- `python3 tools/test_questions_stop.py`: 0 problems (it failed with the IDs restored until I changed it).
- `unittest claude/plugins/delivery/tests/test_questions.py`: 16 tests OK. project-setup has no unit tests that touch the rules.
- `gh workflow run spec-lint.yml --ref SO7-rule-tag-q-ids -f areas=specs,delivery,profiles`, run 42994247530, head 09762bd: all jobs success except `docs check` (failure: G1 stale decisions.md, W1 work report; both expected and not mine) and skipped jobs (change notes, transcript folds, docs plugin, artifact renderer, branch-gate shards: not in the areas).

## Docs
No feature spec states the rule-tag check in detail. Commits say `Docs: none, template tag fix`. `docs_check.py`: only G1 and W1.

## Follow-ups
- G1 (`decisions.md` stale) is generated; the release fold rebuilds it.
- Decide if `docs/rules` tags should become IDs too.

Branch head: see `git rev-parse origin/SO7-rule-tag-q-ids` (the commit after 09762bd adds this report).

READY
