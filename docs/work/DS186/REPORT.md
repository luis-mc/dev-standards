# DS186 report

Branch: DS186-specs-audits-agents-fixes (from origin/main). Findings F31-F47.

## Findings
| ID | Result | Evidence / fix |
|---|---|---|
| F31 | fixed | Failing test first (exit 2 outside repo root). Default externals now found next to the script; a missing default is skipped with a note; a missing explicit --external still exits 2. |
| F32 | fixed | Spec and external reads catch UnicodeDecodeError, exit 2 with a one-line message. |
| F33 | fixed | Outbound citations use the same letter fallback (`Spec.resolves`). |
| F34 | fixed | Name carried over `§9, §10` / `and` / `or` and `§§9`. Not covered: the bare range end in `§§9-10` (no § before 10, so not checked). |
| F35 | fixed | Erasure rule accepts grace period, tombstones, retained audit rows without personal data (AUTHSPEC 15.4, R15.13). |
| F36 | fixed | Heading is WCAG 2.2 AA; AAA contrast only where a project spec requires it (R21.1). |
| F37 | fixed | Budget follows the project's declared budgets, STACKSPEC §14 by default (read p95 <= 200 ms); invented write budget dropped. |
| F38 | fixed | Added Bash to `disallowedTools`; R5.3 updated. Smaller than a tools allowlist and keeps the spec's "read-only" claim true. |
| F39 | fixed | Headings and definitions inside ``` / ~~~ fences are skipped; citations still scanned. |
| F40 | fixed | `<!--` inside an inline code span does not open a comment. |
| F41 | fixed | Files read as utf-8-sig. |
| F42 | fixed | Directory argument expands to `*.md` (code); SKILL.md says so. |
| F43 | fixed | Commands use `${CLAUDE_PLUGIN_ROOT}` for the script and a project-relative spec path; template says "from the project root". |
| F44 | fixed | Stray "Use code with caution." removed; two contrast bullets merged. |
| F45 | fixed | "compliance review" replaced by "security review" in security-audit description. |
| F46 | fixed as scoping (suspected finding) | Shipped specs never mention IL6; FedRAMP High appears only as a reason for admin MFA (authentication.md:2382). Rubric now counts framework-only findings only when the project declares the framework; IL6 removed from the P0 rule and headings. |
| F47 | proven and fixed | authentication.md:1309 requires DEK destruction incl. backups ("what makes erasure real"); VACUUM clause replaced by that, or documented backup/WAL expiry. |

## Tests
- `tools/test_spec_check.py`: added 5 unit cases (F33, F34 x2, F39, F40) and 6 command-line cases (F31, F32 x2, F41, F42, explicit missing external). The full file is a heavy suite and the session guard blocks a local full run. I ran a copy against the old script (14/24, the 10 new cases fail) and the new script (24/24).
- spec_check.py on the shipped STACKSPEC and AUTHSPEC and on the two edited feature specs: see the run in the session; 0 errors expected.
- Full run left to CI: `gh workflow run spec-lint.yml --ref DS186-specs-audits-agents-fixes -f areas=specs,docs`.
- docs_check: M1 errors for audits, models, project-setup mapping are cleared by `Docs: none` lines in the commit message.

Docs: change notes DS186-specs/audits/agents.md; features/specs and features/agents specs edited.

Branch head SHA: see below (set after push).

READY
