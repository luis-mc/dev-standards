# DL208 report

Base check: `git checkout -B DL208-transcript-tail origin/main`; `read_turn` exists in questions_stop.py.

## Hooks changed
- `claude/plugins/project-setup/skills/claude-setup/assets/.claude/hooks/questions_stop.py`: `read_turn` reads from the end in 1 MiB blocks (`tail_lines`), stops at the last real user message, fails open ("", True) when the turn is over 32 MiB.
- `claude/plugins/delivery/scripts/hook_stop.py`: `last_assistant_text` (fallback) read the whole file line by line; it now reads from the end and stops at the first assistant text. The helper is inlined.
- `effort_drift.py` does not read a transcript. No other plugin file does.

## Memory (tracemalloc)
- New reader, 200 MB transcript: peak 2.1 MB (limit 64 MiB).
- Old reader, 20 MB transcript: peak 57.5 MB (about 2.9x the file; a 200 MB file would need about 570 MB).

## Tests
- `claude/plugins/delivery/tests/test_dl208_transcript_tail.py`: 9 passed (same result as old code, small blocks, no final newline, AskUserQuestion mid-turn, empty file, cap, delivery hook, 200 MB memory).
- `tools/test_questions_stop.py`: 0 problems. `tools/test_project_setup_fixes.py`: 0 problems. `tools/test_delivery_hooks.py`: 55 passed. delivery test_stop, test_dl171_hook_rules, test_dl96_eta_forms: 45 OK.
- `docs_check.py`: only G1 (decisions.md stale, generated, not mine) and W1 (this report).
- CI: spec-lint run 43024593046 (advice: light, no extra areas). All jobs success except "docs check" (G1 and W1 only); the rest were skipped by area selection: change notes, change notes folded, shard job, docs plugin, specs/templates/AUTHSPEC, transcript folds plugin, artifact renderer.

## Docs
Spec sentence in docs/features/project-setup/spec.md; notes: features/project-setup, features/delivery, architecture/changes DL208-transcript-tail(.md, -delivery.md).

## Follow-ups
None. G1 needs a docs_index.py build at the release.

Branch head: see the last commit on DL208-transcript-tail.

READY
