# DS300: spec review (duplicates, conflicts, minimal rule sets)

Status: in progress. Read-only review. No repo file is changed except this report.

## Summary

(Written last.)

## 0. Scope and method

Specs read in full: DELIVERYSPEC (`claude/plugins/delivery/references/deliveryspec.md`, 1.19.0), DOCSPEC (`claude/plugins/docs/references/docspec.md`, 1.9.0), ARTIFACTSPEC (`claude/plugins/docs/references/artifactspec.md`, 1.32.0), STACKSPEC (`claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md`), AUTHSPEC (`claude/plugins/project-setup/skills/auth-setup/references/authentication.md`, 3.2.1), the 12 feature specs under `docs/features/*/spec.md`, the shipped rule files and `AGENTS.md`.

Code read for enforcement: `claude/plugins/*/scripts/hook_*.py`, `hooklib.py`, `delivery_watch.py`, `delivery_config.py`, `project_artifacts.py`, `artifact_queue.py`, `docs_check.py`, the shipped `ci_watch.py`, `cleanup.py`, `session_guard.py`, `train_freeze.py`, `change_notes.py`, `tools/ci_areas.py`, `.githooks/` and `.github/workflows/`.

Short names used in file:line references:

| Short | File |
|---|---|
| ds | `claude/plugins/delivery/references/deliveryspec.md` |
| doc | `claude/plugins/docs/references/docspec.md` |
| art | `claude/plugins/docs/references/artifactspec.md` |
| inv | `claude/plugins/project-setup/skills/tech-stack-setup/references/invariants.md` (STACKSPEC) |
| auth | `claude/plugins/project-setup/skills/auth-setup/references/authentication.md` |
| f/del, f/dsp, f/tc, f/art, f/docs, f/ps, f/models, f/specs | `docs/features/{delivery,delivery-speed,test-cost,artifacts,docs,project-setup,models,specs}/spec.md` |
| r/cq | `claude/plugins/delivery/rules/clarifying-questions.md` (the claude-setup copy is byte-equal) |
| r/pa | `claude/plugins/docs/rules/project-artifacts.md` |
| r/ai, r/dt | `claude/plugins/project-setup/skills/claude-setup/assets/.claude/rules/{agents-and-integration,delivery-timing}.md` |
| AG | `AGENTS.md` |
| hpt, hs, hl | `claude/plugins/delivery/scripts/{hook_pre_tool,hook_stop,hooklib}.py` |

IDs in this report: D (duplicates), C (conflicts), G (glossary), E (enforcement), M (minimal set). "Canonical" means the one home that keeps the full text. Every other copy becomes a citation (`see DL-80`) or is dropped.

## 1. Duplicates

Each row names the canonical home first. "Copies" are the places that restate it. Where copies drift, the drift is listed in section 2.

| ID | Topic | Canonical | Copies (file:line) | Action |
|---|---|---|---|---|
| D1 | One full CI run per change; later heads carry | DL-80 (ds:159) | DL-11 (ds:70), DL-116 (ds:131), DL-122 (ds:137), f/del R5.89 (:267), inv:1579 and inv:1586, r/ai:10 and r/ai:20, f/tc S4 (:125) | DL-80 keeps the rule. DL-11, DL-116, DL-122 keep only their own mechanism and cite DL-80. r/ai keeps one sentence. STACKSPEC §13.6 cites DELIVERYSPEC instead of restating it. |
| D2 | Ask every question at once, in the wizard, after doing what needs no answer | Q-1 to Q-5 (ds:347-351) | DL-04 (ds:63), DL-70 (ds:182), DL-71 (ds:183), DL-72 (ds:184), §3 rows (ds:284-286), r/cq (whole file) | D8 already says Q-n "replaces DL-70..72" (ds:346), but the rows are live. Retire DL-04 and DL-70..72 as "Merged into Q-4 / Q-1 / Q-3 / Q-2". Move Q-1..Q-5 into the §1 table so they get Kind and Today columns. |
| D3 | Never `gh pr merge --auto` | DL-05 (ds:64) | D5 (ds:342), §6 `never_auto_merge` (ds:360), r/ai:20, inv:1588 | Keep DL-05. D5 and §6 cite it. |
| D4 | Merge a green train at once | DL-03 (ds:62) | D5 (ds:342), r/dt:6, Q-4 text (r/cq:6), f/del R5.71 (:231) | Keep DL-03 and add the merge mode to it (see C2). |
| D5 | Watch CI by the head commit's runs | DL-07 (ds:66) | r/ai:22, inv:1600 | Keep DL-07. |
| D6 | Train freeze while the ready PR's CI runs | DL-01 (ds:60) | f/dsp DL6 (:52), inv:1590 | Keep DL-01. |
| D7 | Shared contracts committed before agents start | DL-45 (ds:110) | r/ai:21, inv:1571 | Keep DL-45. |
| D8 | Agent test cost (what to run locally, when to use branch CI, no mutation or Docker locally) | DL-12 (ds:71) | r/ai:10, `docs/guides/testing.md:7-11`, f/dsp DL3 (:48), f/tc S4 (:125), DL-81 (ds:160), DL-122 (ds:137) | Keep DL-12 as the single agent rule. Settle C6 first. The guide keeps only the repo's area names and commands. |
| D9 | Publish Full Progress once per turn, three steps, 200 a day | ARTIFACTSPEC R9.1 (art:1943) for when, R9.10 (art:2010) for the steps | R3.1, D13 (art:365), §1.4 (art:416), art:298, art:977, art:1962, art:2254, R8.18, R9.11, R9.12, DL-61 (ds:171), DL-62 (ds:172), r/pa:6 | About ten copies of "once per turn" and of "200 a day" (art index D). Keep R9.1 and R9.10. The Why text stays once, in §15. DL-61 and DL-62 cite R9.8 and R9.11. |
| D10 | The docs plugin never commits or pushes the record | ARTIFACTSPEC R4.13 (art:618) | R4.14, R4.28, R7.6, R8.17, D23, §11, §15, the 1.8.0 log, r/pa:9, AG:11 | Keep R4.13. Others cite it. Fix AG:11 scope (see C4). |
| D11 | Version lines and change logs are written only by the release fold | DOCSPEC R7.1 (doc:306) | DOCSPEC R4.3 (doc:231), AG:8, AG:19, inv:1604, inv:1669-1671, `docs/architecture/changes/README.md`, `docs/README.md` "Change notes", DL-10 (ds:69), DL-24 (ds:83), DL-128 (ds:143) | One rule, two tools (`docs_fold.py`, `change_notes.py`). See C9. |
| D12 | ETA and Expected: clock time, named basis, never padded | DL-31 (ds:95) for chat; ARTIFACTSPEC R6.6 and R6.10 (art:1570, art:1595) for the record | DL-30 (ds:94), D9 (ds:353), r/dt:4-5, r/pa:15-16, f/del R5.16 (:105), f/del R13.89 | Merge DL-30's "state the breakdown" with R6.10's `expected_basis`: one idea, the basis. See C13. |
| D13 | Every doc goes under `docs/` | DOCSPEC §2 (doc:16 says it in prose; no requirement line says it) | DL-75 (ds:187), r/ai:26, r/pa:9 | DOCSPEC R12.2 (doc:426) says other plugins MUST NOT restate docs rules. Add one sentence to DOCSPEC R2.1 (doc:178). Retire DL-75 as "Merged into DOCSPEC R2.1". Drop r/pa:9 (r/ai:26 stays as the one prompt line). |
| D14 | Task branch is `<task-id>-<slug>` | None today | AG:7, r/ai:19 (tagged `check: DL-08`, which is the ready-PR rule), r/pa:4, art D2 (art:354), art:2101, inv:1569 ("named after its task ID") | No rule ID owns it, yet three hooks parse it (`hook_after_command.py:44`, `hook_post_tool.py` DL-123, `session_guard.py`). Add one DELIVERYSPEC row. Others cite it. |
| D15 | Record work as a task before starting | ARTIFACTSPEC R3.2 (art:486) | r/pa:3 and r/pa:10 (same file, two lines) | Keep r/pa:10, drop r/pa:3. |
| D16 | Secret scanning (pre-commit, pre-push, gate, CI over full history) | STACKSPEC §12 (inv:1309) | inv:1370, inv:1500, inv:1557, inv:1955-1966 checklist, auth R24.3 (:2035), auth R27.4 (:2281), f/del R13.57, R13.78, f/dsp R5.10 | No conflict: the CI templates use `--log-opts=HEAD`, which scans all history reachable from the commit. AUTHSPEC cites STACKSPEC §12. |
| D17 | Past-due Expected rows | DL-63 (ds:173) | art R6.14, R8.19 (art:1660, art:1934), f/art R5.25 (:191) | They also disagree. See C12. |
| D18 | Generated files, version-free guides, UX-rules home inside DOCSPEC | DOCSPEC R2.5, R7.5, R11.2 | R6.3 and R4.5 (generated list), R5.2 and §1.1 (no version for guides), D10 and R5.4 (UX home), R15.10 and R15.11 (date pickers, said twice) | Internal. Keep one each. |
| D19 | ARTIFACTSPEC restated by the artifacts feature spec | ARTIFACTSPEC | f/art R5.4 (8 statuses), :255 (4 hooks), R5.17a, R5.11d, :100, :334 (record folder) | The feature spec drifts in six places (C11, C27). It keeps only what the plugin build adds and cites ARTIFACTSPEC for the rest. |
| D20 | AUTHSPEC internal repeats | one place each in AUTHSPEC | About 49 rules said 2 to 5 times: step-up freshness, audit grants, pagination, PKCE, deep links (auth index D) | Keep the rule where its section owns the topic. Other copies cite it. |
| D21 | AUTHSPEC and STACKSPEC on the same topic | STACKSPEC for any product rule; AUTHSPEC for auth-only rules | About 70 pairs (auth index E.2): secrets, server authority, rate limits, sessions, logging, data classes, latency, payload, accessibility | AUTHSPEC keeps a rule only when it is stricter or auth-only, and then cites the STACKSPEC rule it narrows. Real conflicts in C24. |
| D22 | STACKSPEC §13.5-§13.8 restate the delivery flow | DELIVERYSPEC | inv:1500-1610 (gate, join, train, freeze, cleanup, test guard, ready-PR hook, change notes), with script names | STACKSPEC keeps the outcome (one ready PR, one full run, freeze) as MUSTs and cites DELIVERYSPEC for the mechanism. |
| D23 | Stop-hook repeat ceiling | §6 `stop_repeat_limit` (ds:362) | D3 "3-block ceiling" (ds:340), `block_ceiling` (ds:359) | One key, one default. |
| D24 | No retries in CI | DL-121 (ds:136) | DL-99 G3 (ds:120), DL-120 (ds:135) | Keep DL-121; the others cite it. |

Also inside DELIVERYSPEC: DL-76 is repeated word for word at ds:363; `stalled` is defined twice, differently (ds:96 and ds:283); the counts line (ds:190) still counts DL-77..79, which ds:195 says are removed.
