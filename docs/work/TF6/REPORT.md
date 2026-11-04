# TF6 report

Branch: TF6-transcript-folds-fixes

| Finding | Result | Evidence |
|---|---|---|
| F48 | Fixed | Test in change.test.ts failed (PowerShell returned null); `PowerShell` now uses the shell reader. |
| F49 | Fixed | Test in shell.test.ts failed ('fold'); unavailable or skipped edit data now gives 'engine'. |
| F50 | Fixed (spec) | Sections 1, 3, R5.4 and an existing test all fold errored calls to the first error line. The failure table was the odd one out, so it now says interrupted never folds and errored folds to its first error line. No code change. |
| F51 | Fixed | Width tests and a commandRow test failed; escape sequences take no cells and a cut keeps them whole and ends with a reset. |
| F52 | Fixed at unit level | planCommand gave 'fold' for a call with no result. Engine behaviour for a queued call could not be checked (no engine here); the guard is cheap and matches "only a finished call folds". |
| F53 | Fixed | A one-cell base plus U+FE0F is two cells; old '❤️' = 1 test updated to 2. |
| F54 | Fixed | A tab is one cell, and a tab in the error line becomes a space. |
| F55 | Fixed | First line of stderr, else of stdout. |
| F56 | Fixed | Tally keys use forward slashes, lower case for Windows paths. |
| F57 | Fixed | A path starting with `//` is a Windows path. |
| F58 | Fixed | Zero width uses Unicode Mn and Me. |
| F59 | Fixed | Spec test line now `node --test --experimental-strip-types .../tests/*.test.ts`. |
| F60 | Not reproduced | No evidence the engine sends relative paths in bashEditDiff; every fixture and the spec show absolute paths. The tally has no root to resolve against, so a fix would be a guess. Left unchanged; needs a real engine sample. |

## Tests

`node --test --experimental-strip-types claude/plugins/transcript-folds/tests/*.test.ts` on Node 22: pass 101, fail 0 (was 89 plus 12 new).
No e2e specs exist for the folds. docs_check output is in the run log; see the commit.

Files outside my list: none touched. Note: the plugin file is `hooks/transcript_folds.tsx`, not `.ts`; it was not changed.

Head SHA: see `git rev-parse TF6-transcript-folds-fixes` on origin.

READY
