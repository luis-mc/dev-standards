# DS300: spec review (duplicates, conflicts, minimal rule sets)

Status: done. Read-only review. No repo file is changed except this report.

## Summary

Counts: 24 duplicates (D), 26 conflicts (C, 10 need an owner decision), 10 terms and 5 glossary proposals (G), 24 enforcement items (E), 7 minimal-set tables (M). DELIVERYSPEC: 106 DL rows; 21 marked Today N are enforced in code, 12 have no check at all.

Top 8 proposals (section 6):
1. C2/E3: in `manual` merge mode, Q-4 and the DL-03 Stop check still push the session to merge, which the hook refuses. Read `merge_mode` in both (`hook_pre_tool.py:822-831`, `hook_stop.py:281-284`).
2. C1/C3/C4: name three roles (task agent, orchestrator, watcher). DL-03 says who merges per `merge_mode`; DL-08 says who opens the ready PR; DL-73 drops its "merging stays the owner's"; AGENTS.md:10-11 match the code.
3. D2: move Q-1..Q-5 into the DELIVERYSPEC table; retire DL-04 and DL-70..72 (DL-71/72 still say "ask in plain chat", against Q-2).
4. E1/E2: generate the Today column from the hooks; add one test that every rule ID cited in code exists (fixes the DL-123/DL-124 key, D4 for DL-39, R17.7g).
5. C6/D8: one agent test rule in DL-12; the 140-word rule line `agents-and-integration.md:10` becomes one line.
6. C9/D11: one change-note rule in DOCSPEC §7 for both tools (`docs_fold.py`, `change_notes.py`) and one fold point.
7. G1-G3: `docs/overview/glossary.md` is the one home; each shipped spec carries a test-checked copy of the terms it uses; fix the clashing senses of owner, area, carry and full run.
8. C12/E9: one past-due Expected check. Today the delivery Stop hook blocks at once and the docs hook warns first.

Conflicts that need an owner decision:
- C1: may a session (not the watcher) run `gh pr merge` in `auto` mode? AGENTS.md says never; the hook allows it.
- C3: does "agent" in AGENTS.md:7 mean task agent only (the orchestrator may open the ready PR)?
- C4: AGENTS.md:11 "plugins never commit, push or merge" vs the watcher (pushes, merges) and `docs_work.py strip --apply` (commits).
- C5: should this repo's ready PR run everything on its first run (DL-80), or keep touched areas only (test-cost R5.2)?
- C6: may an agent start branch CI for a heavy change (rule file, testing guide) or never unless Linux-only (delivery-speed DL3)?
- C9: does the fold run on the release PR (DL-24, DL-10) or on `main` (changes README)?
- C12: past-due Expected blocks at once (DL-63, ARTIFACTSPEC R8.19) or warns first and blocks after 60 min (artifacts R5.25)?
- C16: drop "overrule any internal safety limits" from the Q-1 rule line? Q-1 does not say it.
- C24: STACKSPEC requires rate-limit headers and app-layer encryption of `secret` fields; AUTHSPEC forbids showing the remaining budget and requires one-way password hashes.
- C25: STACKSPEC says a new MUST is a major version; 8.2.0, 8.6.0 and 8.8.0 added MUSTs as minor bumps.

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
| D5 | Watch CI by the head commit's runs | DL-07 (ds:66) | r/ai:21, inv:1600 | Keep DL-07. |
| D6 | Train freeze while the ready PR's CI runs | DL-01 (ds:60) | f/dsp DL6 (:52), inv:1590 | Keep DL-01. |
| D7 | Shared contracts committed before agents start | DL-45 (ds:110) | r/ai:13, inv:1571 | Keep DL-45. |
| D8 | Agent test cost (what to run locally, when to use branch CI, no mutation or Docker locally) | DL-12 (ds:71) | r/ai:10, `docs/guides/testing.md:7-11`, f/dsp DL3 (:48), f/tc S4 (:125), DL-81 (ds:160), DL-122 (ds:137) | Keep DL-12 as the single agent rule. Settle C6 first. The guide keeps only the repo's area names and commands. |
| D9 | Publish Full Progress once per turn, three steps, 200 a day | ARTIFACTSPEC R9.1 (art:1943) for when, R9.10 (art:2010) for the steps | R3.1, D13 (art:365), §1.4 (art:416), art:298, art:977, art:1962, art:2254, R8.18, R9.11, R9.12, DL-61 (ds:171), DL-62 (ds:172), r/pa:6 | About ten copies of "once per turn" and of "200 a day" (art index D). Keep R9.1 and R9.10. The Why text stays once, in §15. DL-61 and DL-62 cite R9.8 and R9.11. |
| D10 | The docs plugin never commits or pushes the record | ARTIFACTSPEC R4.13 (art:618) | R4.14, R4.28, R7.6, R8.17, D23, §11, §15, the 1.8.0 log, r/pa:9, AG:11 | Keep R4.13. Others cite it. Fix AG:11 scope (see C4). |
| D11 | Version lines and change logs are written only by the release fold | DOCSPEC R7.1 (doc:306) | DOCSPEC R4.3 (doc:231), AG:8, AG:19, inv:1604, inv:1669-1671, `docs/architecture/changes/README.md`, `docs/README.md` "Change notes", DL-10 (ds:69), DL-24 (ds:83), DL-128 (ds:143) | One rule, two tools (`docs_fold.py`, `change_notes.py`). See C9. |
| D12 | ETA and Expected: clock time, named basis, never padded | DL-31 (ds:95) for chat; ARTIFACTSPEC R6.6 and R6.10 (art:1570, art:1595) for the record | DL-30 (ds:94), D9 (ds:353), r/dt:4-5, r/pa:15-16, f/del R5.16 (:105), f/del R13.89 | Merge DL-30's "state the breakdown" with R6.10's `expected_basis`: one idea, the basis. See C13. |
| D13 | Every doc goes under `docs/` | DOCSPEC §2 (doc:16 says it in prose; no requirement line says it) | DL-75 (ds:187), r/ai:26, r/pa:8 | DOCSPEC R12.2 (doc:426) says other plugins MUST NOT restate docs rules. Add one sentence to DOCSPEC R2.1 (doc:178). Retire DL-75 as "Merged into DOCSPEC R2.1". Drop r/pa:8 (r/ai:26 stays as the one prompt line). |
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

## 2. Conflicts

Each row quotes both sides. "Code" says which side the hooks or scripts follow. "Owner?" is Yes when the fix needs an owner decision, not just an edit.

### 2.1 Merge, ready PRs and who pushes

**C1. Who merges a green PR.** Owner? **Yes.**
- Side A, the owner merges: DL-73 (ds:185) "agents may open pull requests, mark them ready and edit their title and description; merging stays the owner's." Same text in r/ai:15 and f/ps R5.24 (:114). AG:10 "Agents never run `gh pr merge` in either mode".
- Side B, the watcher or the session merges: DL-03 (ds:62) "Merge a green train at once." D5 (ds:342) "merges the previous train the moment its CI is green". §6 `merge_on_green` default true (ds:360). f/del R5.71 (:231) "`auto` (the default: merge on green)". r/dt:6 "merge it at once". inv:1588 "It merges when that run is green, never by auto-merge" (the word "auto-merge" here means `--auto`, which reads like the opposite of `merge_mode: auto`).
- Code: side B. `delivery_config.py:55-57` defaults to `auto`. The watcher merges (`delivery_watch.py:882`). `hpt:88-93` denies an agent's `gh pr merge` only in `manual` mode or with `--auto`. In `auto` mode an agent session may still run `gh pr merge`, which AG:10 forbids.
- `watcher.merge_mode` is not in DELIVERYSPEC at all; only f/del R5.71 and AG:10 state it.
- Proposal: DL-03 becomes "In `auto` mode the watcher merges a green PR at once; in `manual` mode the owner merges." DL-73 drops its merge clause and cites DL-03. Owner decides: may a session (not the watcher) run `gh pr merge` in `auto` mode? If no, `hpt` denies it in both modes and AG:10 becomes true.

**C2. Manual merge mode deadlocks the question rule.** Owner? No (follows from the owner's choice of `manual`).
- `hpt:822-831` (Q-4) denies `AskUserQuestion` while a green train is unmerged. `hs:281-284` (DL-03) blocks the turn end with "green and not merged ... gh pr merge N". Neither reads `merge_mode` (`hl:300-303`).
- In `manual` mode `hpt:88-90` refuses the merge. The session can neither merge nor ask the owner, until it records a hold.
- Proposal: Q-4 and the DL-03 Stop check skip green trains when `merge_mode` is `manual`; the Stop line says "green, waiting for the owner to merge" once, as a warning. Add a test next to `test_dp16_merge_mode.py`.

**C3. Who opens a ready PR.** Owner? **Yes** (scope of "agent").
- AG:7 "an agent ... never ... opens a ready pull request."
- DL-73 (ds:185) "agents may open pull requests, mark them ready".
- DL-08 (ds:67) "Open a ready PR only from a release/integration branch; every other PR is a draft." r/ai:20 "Open one ready PR when the join is pushed".
- D5 (ds:342): the watcher "opens its ready PR".
- Code: `session_guard.py:247-277` refuses `gh pr create` without `--draft` and `gh pr ready` off a release branch. It is wired only by this repo's `.claude/settings.json`, so it does not ship to projects. The watcher's `gh pr create` (`delivery_watch.py:1081`) runs as a subprocess, so no hook sees it.
- Proposal: name three roles once (G-section): task agent, orchestrator (the main session), watcher. DL-08 says: a task agent opens drafts only; the orchestrator or the watcher opens the one ready PR from the integration branch. DL-73's PR clause cites DL-08. Ship the ready-PR check in `hpt` so projects get it.

**C4. "Plugins never commit, push or merge."** Owner? **Yes.**
- AG:11 "Plugins write files in the working tree. They never commit, push or merge."
- The delivery watcher pushes, opens PRs, merges, cancels and re-runs runs (`delivery_watch.py:702-1124`), and SessionStart starts it (`hook_session_start.py:195-270`). D5 (ds:342) requires this.
- f/tc R5.8 (:163) "The artifacts record commits on every change and pushes once per turn". ARTIFACTSPEC R4.13 (art:618) "The plugin MUST NOT write git state". `docs_work.py strip --apply` commits the `docs/work/` removal (`docs_work.py:108-119`, f/docs 0.10.1 log).
- Code: the record commands follow R4.13; `docs_work.py` and the delivery watcher do not follow AG:11.
- Proposal: AG:11 becomes "Hooks and the docs plugin never commit, push or merge. The delivery watcher pushes trains, opens the ready PR and merges per `merge_mode` (DL-03)." Retire f/tc R5.8 as "Superseded by ARTIFACTSPEC R4.13". Either `strip --apply` stops committing (it prints the command) or AG:11 names it as the one docs-plugin commit.

### 2.2 CI scope and test cost

**C5. Does the ready PR's first run run everything?** Owner? **Yes** (for this repo).
- Products: DL-80 (ds:159) "A release pull request runs the full suite on its first run". f/del R5.89 (:267). inv:1586. r/ai:10 and r/ai:20 "The ready PR's first CI run is the one full run".
- This repo: f/tc R5.2 (:151) "The ready PR runs only the jobs of the touched areas." `docs/guides/testing.md:11` says the same, right after saying the shipped rule "applies here too" (:5).
- Code: this repo follows f/tc R5.2. `tools/ci_areas.py` runs every area only for shared paths, unmapped paths, schedule or dispatch; there is no first-run-full rule.
- Proposal: either this repo adopts DL-80 (first run full), or f/tc R5.2 says "This repository deviates from DL-80: ..." with the reason. Today the guide contradicts itself.

**C6. May an agent start branch CI?** Owner? **Yes.**
- r/ai:10 "A heavy change ... runs a 1-2 minute local smoke ..., then CI on its branch for its area only (`gh workflow run ...`)". `docs/guides/testing.md:9` the same.
- f/dsp DL3 (:48) "It never starts a branch CI run unless the change behaves differently on Linux." f/tc S4 (:125) "No full branch runs by agents ... only for a Linux-specific change".
- DL-12 (ds:71) and DL-81 (ds:160): on the opt-in CI-gate path, "its branch CI is its gate", run by `agent_ci.py`, not `gh workflow run`.
- r/ai:19 "branch gate in the agent sandbox (no Actions)" contradicts r/ai:10 in the same file.
- Code: `session_guard.py:144-201` refuses a full local run of a heavy suite (> 180 s), which pushes agents to branch CI. Nothing refuses `gh workflow run --ref`.
- Proposal: DL-12 states the light/heavy split once, with the CI path named (`agent_ci.py` or `gh workflow run`, one of them). f/dsp DL3 is marked superseded. r/ai:19 drops "(no Actions)".

**C7. Mutation passes on pull requests.** Owner? No (two of three sources and the code agree).
- f/tc R5.3 (:153) "A mutation pass runs only when its own scripts, hooks or suite file change" (any event).
- DL-99 G6 (ds:120) "no mutation ... on a pull request or a non-default push". f/dsp R5.23 (:117) "never run on a pull request: only the nightly".
- Code: `spec-lint.yml:240-748` runs mutation passes on a PR when a guarded file changes (follows f/tc R5.3). `docs/guides/testing.md:11` agrees with the code.
- Proposal: DL-99 G6 is Scope G for products; this repo is a declared exception. State it once in f/tc R5.3 ("unlike DL-99 G6").

**C8. Default-branch run after a merge.** Owner? No.
- f/del R5.88 (:265) calls "main's post-merge full run" a safety net. f/del R5.95 (:279) "replaces main's post-merge full run". f/tc R5.5 (:157) skips only for ignored paths. DL-76 (ds:188) "Nothing after the merge re-runs what the release PR proved".
- Code: the carry-plan action (R5.95).
- Proposal: fix R5.88's parenthesis; f/tc R5.5 cites R5.95.

**C9. Change notes: two folders, two tools, two fold points.** Owner? **Yes** (where the fold runs).
- Folder: AG:8 "adds a change note in `docs/architecture/changes/`". AG:19 "`docs_fold.py note --doc features/<feature>`", which writes `docs/features/<feature>/changes/<task>.md` (DOCSPEC R7.1, doc:306).
- Level: inv:1604 "Branches SHOULD NOT edit a spec's version or change log." AG:8 "never". inv:1669-1671 "A version or change-log edit off a release branch is refused at commit time".
- When: DL-24 (ds:83) "Only the release PR folds spec change notes." DL-10 (ds:69) "A ready PR from `release/*` runs `release:prepare` (fold spec notes) before CI." `docs/architecture/changes/README.md` "the orchestrator folds there [on `main`]". `docs/README.md` "The release fold on `main`".
- Code: `change_notes.py` pre-commit refuses the edit (MUST side). Both tools fold on demand; nothing ties the fold to the release PR or to `main`.
- Proposal: one rule in DOCSPEC §7 covering both note kinds (doc notes and spec/plugin notes), MUST level; STACKSPEC cites it. Owner decides: the fold runs on the release PR (DL-24) or on `main` after the merge (README). Then fix the other.

### 2.3 Time, Expected and the record

**C10. ETA: clock time vs date.** Owner? No.
- DL-31 (ds:95) "Give every ETA as a clock time". r/dt:4 "Every ETA is a clock time".
- ARTIFACTSPEC R6.6 (art:1570) allows `DD Mon` with no time, and `DD Mon ~HH:MM` "for work due within a day".
- Scope differs (chat vs record row), but the words collide. Proposal: DL-31 says "in chat"; R6.6 stays for the record and cites DL-31 for chat.

**C11. Default record folder.** Owner? No (the code already decided, D182).
- ARTIFACTSPEC R4.37 (art:780) and the config table (art:2157): default `docs/artifacts`. R4.13 (art:618) still says `docs/artifacts/`.
- DOCSPEC R2.4 (doc:181) and D14 (doc:112): default `docs/project`. `docs/overview/glossary.md` and f/art :334: `docs/project`.
- Code: `artifact_queue.py:25-26, 74-89`: `record_dir` in `.claude/artifacts.json`; else `docs/artifacts` when that file exists; else `record_dir` in `docs/docs.json`; else `docs/project`.
- Proposal: ARTIFACTSPEC R4.37 states the code's order. DOCSPEC R2.4 cites R4.37. R4.13 says "the record folder (R4.37)".

**C12. Past-due Expected: block now or warn first.** Owner? **Yes.**
- DL-63 (ds:173) "No open row may show an Expected time in the past." Kind STOP. ARTIFACTSPEC R6.14 (art:1660) and R8.19 (art:1934) "The hook blocks while an open row is past its Expected time".
- f/art R5.25 (:191): warn once; block only a Running or Waiting row more than 60 minutes past due.
- Code: both. `hs:613-629` (delivery) blocks at once. `hook_end_of_turn.py:383-421` (docs) warns, then blocks after 60 minutes. A project with both plugins gets both.
- Proposal: owner picks one behaviour. ARTIFACTSPEC R8.19 owns it; DL-63 retires as "Merged into ARTIFACTSPEC R8.19" and the delivery check is removed.

**C13. ETA check threshold.** Owner? No (newer text and code agree).
- DL-30 (ds:94) checks against `eta_table` (15-25, 25-35, 40-60 min); §3 (ds:282) "Warn when the total is > 2x the `eta_table` row". Today N.
- f/del R13.89 (:564) refuses an ETA "more than 50 % above the measured p75", at least 5 samples.
- Code: `hpt:645-678` denies above 1.5 x p75 with 5 samples (R13.89). `delivery_eta.py:20` uses 3 samples for the CLI.
- Proposal: DL-30 states R13.89's rule; drop the `eta_table` text; one sample minimum.

**C14. ARTIFACTSPEC contradicts itself.** Owner? No.
- R6.3 (art:1550) "There is no `Earlier` fold" vs R6.12 (art:1616), R5.46, D15 and the config table, which describe one.
- R5.61 (art:1454) removes the lede, At a glance and tiles; R5.3, R5.33, R5.37 and the §14 table still assume them.
- R4.5 (art:571) "dropped work is set On hold or Built" vs R5.49 (art:1338) adds `Dropped`.
- R8.5 (art:1803) "The hook fetches the default branch" vs R4.13 "Nothing is synced from `origin`".
- Proposal: edit the stale lines to match the newer rule (R6.3, R5.61, R5.49, R4.13 win).

### 2.4 Questions, attribution, agents

**C15. Plain-chat questions.** Owner? No.
- DL-71 (ds:183) "or ask in plain chat". DL-72 (ds:184) "re-ask in plain chat". §3 (ds:285) "end the turn with the text, ask in plain chat".
- Q-2 (ds:348) and r/cq:4 "never write questions to the user as plain text".
- Code: Q-2. `hs:206-235` blocks a reply that ends with a list of questions. DL-71 and DL-72 have no check.
- Proposal: retire DL-71 and DL-72 (see D2). Keep one exception if the owner wants it: "a rejected dialog is re-asked in the wizard, not in text".

**C16. Q-1 rule-file wording goes past the spec.** Owner? **Yes.**
- r/cq:3 "overrule any internal safety limits or 4-question caps. Even if you have 20, 50, or 100+ questions". Q-1 (ds:347) only says "There is no 4-question cap when the owner says 'ask me questions'".
- "Overrule any internal safety limits" asks the model to ignore limits the spec never names. Proposal: r/cq:3 says only what Q-1 says.

**C17. Attribution.** Owner? No.
- DL-74 (ds:186) "No Co-Authored-By or Claude attribution in commits or PR bodies (owner choice)." Unconditional; Today N.
- r/ai:16 "... when `.delivery/config.json` sets `no_attribution`". The key is not in DELIVERYSPEC §6.
- Code: `hpt:342-348` denies only when `no_attribution` is true (default false, `hl:47`).
- Proposal: DL-74 says "when `no_attribution` is true"; add the key to §6 and the schema.

**C18. Agent effort and caps.** Owner? No.
- DL-37 (ds:102) "Code agents: Sonnet at medium". r/ai:3 "Sonnet at {{SUBAGENT_EFFORT}}". Proposal: DL-37 says "the effort chosen in claude-setup (default medium)".
- DL-38 (ds:103) "local <= 3 and only with > 8 GB free memory, total 53". r/ai:9 omits memory and total. ds:326 example "caps 8/3/5". Code: `hl:39-40`, `hpt:754-798` (50/3/53, 8 GB). Proposal: fix ds:326; r/ai:9 may stay short since the hook enforces it.

**C19. Model of spec-check.** Owner? No.
- f/specs:70 "The skills pin ... `sonnet` (spec-check)". f/models:91 lists spec-check under Haiku.
- Code: `claude/plugins/docs/skills/spec-check/SKILL.md:4` `model: haiku`. Fix f/specs:70. f/models decision row 0014 (:162) still says Explore stays on Opus; f/models:39 says it was reversed.

### 2.5 Feature specs against their owners and against each other

**C20. Red-run cancel default.** f/del R5.13 (:91) "`ci_watch.py` ... cancels the other runs of that head ... `--no-cancel-on-red` ... keeps the old wait". f/dsp R5.22 (:115) "`ci_watch.py` never cancels a red run by default". Code: `ci_watch.py:856-859` default False. Fix f/del R5.13.

**C21. `cancel_joined_runs.py`.** f/del R5.22 (:117) "Removed (DS293)". DL-97 (ds:87) and f/dsp R5.18 (:107) still name it. Fix both.

**C22. Delivery log default.** f/dsp R5.7 (:85) logs before every delete. f/del R5.32 (:137) "The default changed from on to off". Code: `cleanup.py:40` off. Fix f/dsp R5.7.

**C23. `docs/work/` on a branch.** AG:22 puts briefs in `docs/work/`; AG:24 says run `docs_check.py` before finishing. DOCSPEC R10.2 (doc:394) runs W1 "on a ready pull request". Code: `docs_check.py:343-349` fails W1 on any branch that adds `docs/work/` files, so the check AG:24 asks for fails on every agent branch with a report. Proposal: W1 runs only with `--ready` (or in the PR gate), as R10.2 says.

**C24. AUTHSPEC against STACKSPEC.** Owner? **Yes** for the first two.
- Rate-limit headers: inv:564 "Responses MUST carry rate-limit headers". auth R17.7 (:1462) "MUST NOT reveal which limit was hit, the remaining budget". Common headers carry the remaining budget. Proposal: STACKSPEC says "except auth endpoints (AUTHSPEC R17.7), which send only `Retry-After`".
- Secret fields: inv:715-717 "Fields classified `secret` MUST additionally be encrypted at the application layer". auth :380 password hash "Never encrypted-and-reversible". Proposal: STACKSPEC names one-way hashes as meeting the `secret` rule.
- Latency: auth :1879-1881 session validation ≤ 5 ms hit, ≤ 30 ms miss; inv:1694 ≤ 10 ms. auth :1880 `GET /v1/me` ≤ 100 ms; inv:1693 typical read ≤ 200 ms. Stricter is allowed; AUTHSPEC should say it narrows STACKSPEC.
- Deviation record: auth :76 "in the project's configuration reference (§24)"; inv:227 "a recorded justification and a named approver (§18)", in the Stack Profile. Proposal: one home, the Stack Profile; AUTHSPEC cites it.
- Fail mode: auth fails closed on all auth endpoints; inv:561-562 only on credential and token buckets. Stricter; cite.
- Levels that differ but are compatible because AUTHSPEC narrows scope: accessibility (auth R21.1 MUST AA for auth flows vs inv:1116 SHOULD), payload (auth R22.38 MUST < 50 KB vs inv:533 SHOULD).

**C25. STACKSPEC breaks its own versioning rule.** inv:1992 "A new `MUST` is a major version." 8.8.0 (inv:64-66, rules at inv:1406-1412), 8.6.0 (inv:76-78) and 8.2.0 added MUSTs as minor bumps. The change-note `change:` kind is chosen by the author and nothing checks it. Owner? **Yes**: keep the rule and bump, or relax it to "a new MUST that breaks a conforming product is a major version".

**C26. Small ID and text slips** (no owner decision):
- f/del uses R5.36c (:149, :155), R5.46 (:175, :179) and R13.96 (:516, :570) twice each. f/docs uses R5.23 twice (:78, :108). `spec_check.py` would report these if it ran on feature specs.
- f/del R5.80 cites DL-12; the matching row is DL-122.
- f/dsp R6.1 (:135) exit codes 0-4; f/del R5.56 (:203) and R5.57 (:205) add exit 5.
- DOCSPEC R15.7 (doc:475) DS2 "warn (never error)" for a missing approval vs R15.25 (doc:489) DS7 fails it.
- f/del R5.12 doctor checks a runner hook; DELIVERYSPEC ds:367 lists five checks without it; runner hooks were removed.
- f/del :378 D5 "85% memory, 60% CPU" vs ds:195 "The plugin no longer owns machine limits".
- ARTIFACTSPEC cites "decision D20" (art:2004) for the hourly fail-safe; D20 in its table is another decision. It cites D48; the table stops at D26.
- inv:333-335 still shows `docs/specs/` and `docs/notes/`; §16 and 8.5.0 replaced them with DOCSPEC's layout. The heading "What changed in 7.x, 6.0 and 5.x" (inv:62) holds 8.x entries.
- ARTIFACTSPEC heading "0.4 What changed in 1.1.0" (art:106) holds every entry to 1.32.0.

## 3. Definitions and one glossary home

Today there are three formal term tables: DOCSPEC §1.1 (doc:120-132), ARTIFACTSPEC §1.4 (art:410-428) and the repo glossary `docs/overview/glossary.md`. DELIVERYSPEC, STACKSPEC and AUTHSPEC have none. The repo glossary does not ship, so projects never see it.

### 3.1 The ten terms

| Term | Meanings found (file:line) | Problem | Proposed single meaning |
|---|---|---|---|
| release | (a) a task row with `"release": <n>`, shown as RELEASE-n: art R5.40, R5.45 (art:1116, art:1249). (b) "One batch of task branches that are joined, tested by one ready pull request and merged together": glossary. (c) one PR can carry several releases: DL-129 (ds:144) "joined as `RELEASE-1 and RELEASE-2`". (d) a branch prefix: DL-10 (ds:69) `release/*`; DOCSPEC R15.25 (doc:489) "a release branch (a name starting `release`, or the default branch)". (e) the fold unit: DOCSPEC R7.3-R7.4 (doc:308-313). STACKSPEC uses it about eight ways (deploy, product version, release PR, release gate). | (b) and (c) disagree: is a release one PR or can one PR hold several? | **release**: a set of tasks that ship together, named RELEASE-n, recorded as a release task. It rides one ready PR; one ready PR may carry several releases. Use "release branch" and "release PR" only as compounds, defined once. |
| train | The ledger's name for a release in flight: glossary; ledger `trains[]` (ds:206-224); "never say train" DL-64 (ds:174). | Fine, but the rule text (DL-01, DL-02, DL-03, DL-16, r/dt) still says "train" to the model, which then says it to the owner. | **train**: ledger-only word for the branch and PR that carry one or more releases. Rule text says "release PR" instead. |
| task | "One unit of work with an ID, a status and an owner": art:418. ID format three ways: art R4.5 (art:569) "a registered prefix plus a positive integer"; DL-123 (ds:138) "2 to 5 capital letters and digits"; code `^([A-Z]{2,5}[0-9]+)-` (`hook_after_command.py:44`). | Three ID formats. | Keep art:418. One ID format in ARTIFACTSPEC R4.5; the hooks cite it. |
| Built | art:1529 "Finished, but not merged or released yet"; art R3.4 (art:493) "finished but not released"; glossary "finished but not yet released"; r/pa:12. | "Not merged" appears only in art:1529. Is a merged, undeployed task Built or Live? | **Built**: the work is finished; its release has not reached Live. |
| Live | art:1528 "Released or in production"; ledger `live_at` and train state `live` = smoke passed after deploy (DL-18, ds:77); DOCSPEC R4.3 (doc:231) feature `status: live` = "the code has shipped and the checks pass"; r/pa:16 a no-release task "goes Live, never Built". | Task Live, train live and feature live are three things. | **Live** (task): its release merged and, where there is a deploy, the smoke passed. Feature `live` and train `live` keep their own names in their own tables. |
| area | (a) CI area: `.delivery/ci-areas.json` (DL-116, ds:131), `tools/ci_areas.py`, inv:1410 "every tracked file belongs to an area". (b) record task field: DL-126 (ds:141) "the same `app` (or `area`)". (c) a docs folder: DOCSPEC R7.1 (doc:306) `docs/<area>/changes/`. | Three meanings. | **area** = CI area only. Rename (b) to "app" (already the primary key) and (c) to "docs folder". |
| full run | DL-11 (ds:70) "The ready PR's first CI run is the one full run"; `--full` local gate (DL-12, DL-122); `release_full` (DL-116); "nightly full run" (f/tc :182, f/del R5.95); "full-run valve" (r/ai:10). Stated four ways in STACKSPEC (inv:1409, 1511, 1579, 1586). | One phrase for a CI run, a local run and a nightly run. | **full run**: a CI run of every job of the required workflows. Local `--full` is "full local gate". Nightly is "nightly run". |
| carry | (a) a CI job skipped because an earlier head proved it: DL-80 (ds:159), f/del R5.88 (:265), inv:1408. (b) a PR carries cargo or releases: DL-15 (ds:74) "Carries: #x, #y", DL-63, DL-129, DL-131. (c) plain verb for a row field: art R4.8. | (a) and (b) are both delivery terms. | **carried job** for (a). "includes" or "cargo" for (b). |
| owner | (a) the person who decides: DELIVERYSPEC legend (ds:47), DL-73, Q-n, AG:10. (b) a task's feature: art:419 "The feature artifact it belongs to (its `key`), or `project`". (c) doc front matter `owner` (`owner` or `agents`): DOCSPEC R4.2 (doc:226). (d) a quarantine entry's task: DL-121 (ds:136). | (b) and (d) clash with (a), which every rule file uses. | **owner** = the person only. Rename (b) to "feature" (`key`), (c) to "maintainer", (d) to "task". |
| join | Glossary "Merging the task branches of a release into one head, with a light check"; DL-11 (ds:70); inv:1573-1584; an artifacts phase name (art R5.40). | Consistent. Not defined in any shipped spec. | Keep the glossary text. |

Also undefined in every shipped spec but used in rules: **wave** (Q-5, ds:351, r/cq:7), **integration branch** (DL-08, DL-45, art R5.59), **orchestrator** (r/ai:2, DL-83), **gate** (branch gate, release gate, conformance gate, docs gate, the CI-gate path), **open row** (three wordings: art:1570, art R5.44 at art:1239 "any status but Live", art R9.8 at art:2002), **stalled** (two definitions, ds:96 and ds:283).

ID-form collisions: DOCSPEC decisions D1-D16 (doc:99-114), DELIVERYSPEC decisions D1-D9 (ds:338-353), ARTIFACTSPEC decisions D1-D26 and DOCSPEC check code D1 (doc:254) all use `Dn`. A citation "D5" is ambiguous (f/del R5.71 cites "owner decision D5", meaning a delivery feature decision).

### 3.2 Proposal

| ID | Proposal |
|---|---|
| G1 | One home: `docs/overview/glossary.md` stays the single place where terms are written and changed. |
| G2 | Each shipped spec gets a short `Terms` table holding only the terms it uses, copied from G1. A test (like the byte-copy test for `clarifying-questions.md`, ds:352) fails when a copy differs from G1. Projects then see the same words without the repo glossary. |
| G3 | Apply the ten meanings in 3.1. Rename the clashing senses (owner, area, carry, full run) in rule text, not in ledger field names, so no code changes. |
| G4 | Add wave, integration branch, orchestrator, task agent, watcher, gate kinds and open row to G1. |
| G5 | Prefix decision IDs per spec in citations (`DOC-D5`, `DEL-D5`, `ART-D5`). The IDs themselves stay (AG:9). |

## 4. Enforcement

### 4.1 State of the checks

- DELIVERYSPEC §1 has 106 DL rows. 21 rows say Today `N` while the code cites and enforces them: DL-02, 03, 05, 17, 20, 23, 30, 32, 32a, 36, 38, 41, 42, 53, 55, 63, 64, 74, 75, 76, 85. Some `~` rows are also enforced in full (DL-06, DL-07, DL-31, DL-37). The counts line (ds:190, "8 Y, 1 W, 17 ~, 37 N") is wrong.
- 12 rows say `N` and no code cites them: DL-04, 15, 16, 21, 34, 35, 44, 45, 61, 65, 71, 72.
- The Q-1..Q-5 rules are enforced (`hpt:816-874`, `hs:206-235`) but sit in a D8 bullet list, outside the table, so they have no Today column.
- No test checks that a rule ID cited in code exists in a spec. `tools/test_rule_tags.py:47-98` checks rule-file tags only, and its pattern accepts only two-digit DL IDs, so a rule file can never cite DL-100 or above.
- In this clone `core.hooksPath` is unset, so `.githooks/` (train freeze, change notes, secret scan) do not run unless the setup sets it.

### 4.2 Proposals

| ID | Finding (file:line) | Proposal | Kind |
|---|---|---|---|
| E1 | The Today column is stale on 21+ rows (4.1). | Generate the Today column: a script reads the `checks` registry of `hpt`, `hs` and `hook_post_tool.py` and fills Y/W/~ per ID. A test fails when the table and the registry differ. | enforce |
| E2 | No test ties code IDs to spec IDs. `hs:632-663` checks "Running but no agent" under `DL-123`, but the spec row is DL-124 (ds:139), so `checks_off: ["DL-124"]` does nothing. `hpt:761-763` denies under `D4` instead of DL-39 (ds:104). `hpt:849` starts a message with `DL136`, a task ID. `tools/authspec_check.py:623, 634` cite R17.7g, which AUTHSPEC lacks. | Add one test: every `DL-n`, `Q-n`, `R<n>.<n>`, `INV-n`, `LC-n` string in hook and script messages exists in its spec. Fix the four slips. Widen `test_rule_tags.py` to three-digit IDs. | enforce |
| E3 | Q-4 and the DL-03 Stop check ignore `merge_mode` (C2). | Read `merge_mode` in both. | fix |
| E4 | AG:10 says agents never run `gh pr merge`; in `auto` mode `hpt:88-93` allows it (C1). | After the owner decides C1: deny in both modes when the caller is not the watcher, or reword AG:10. | enforce or drop |
| E5 | DL-08 is enforced only by `session_guard.py`, wired by this repo's `.claude/settings.json` (`session_guard.py:247-277`). Projects do not get it. | Move the ready-PR check into `hpt` so it ships. | enforce |
| E6 | AG:7 "never pushes to `main`": nothing local denies a push to the default branch. | Add a PRE deny of `git push` whose target is the default branch, and the same check in `.githooks/pre-push`. | enforce |
| E7 | AG:12 "Name no other project": only `tools/test_ci_speedups.py:540-559` checks two scope scripts with hashed names. | Run the same hashed-name check over specs, rule files, `AGENTS.md` and commit messages in CI. | enforce |
| E8 | W1 (`docs_check.py:343-349`) fails any branch that adds `docs/work/`; DOCSPEC R10.2 (doc:394) says ready PR only (C23). | Gate W1 behind the PR gate (`--ready` or the event), as R10.2 says. | fix |
| E9 | Two hooks check past-due Expected with different behaviour (C12): `hs:613-629` and `hook_end_of_turn.py:383-421`. | Keep one, in the docs plugin; remove DL-63's Stop check. | drop one |
| E10 | Prose-only rows that duplicate an enforced rule: DL-04 (= Q-4), DL-71, DL-72 (= Q-2, Q-3), DL-61 (the docs end-of-turn hook enforces R9.8). | Retire as "Merged into ...". | drop |
| E11 | Prose-only rows with no check planned: DL-15 (PR body lists cargo), DL-16 (train never waits for slow cargo), DL-34 (verify the branch moved; overlaps DL-32a, which the watcher does), DL-35 (start cloud runs at once), DL-44 (report first, push after each step), DL-45 (contracts before agents), DL-65 (one shared reading of state, a design property). | DL-15: the watcher writes the `Carries:` line itself, so the rule becomes code. DL-34: merge into DL-32a. DL-35: drop (the launch tool sets the time). DL-65: move to §5 Design. DL-16, DL-44, DL-45: keep as TEXT; mark Kind TEXT honestly. | enforce / merge / drop |
| E12 | DL-21 (ds:80) "CI jobs run only on self-hosted runners" is Scope P, and f/del (:401, :420) offers GitHub-hosted with no default. | Drop from the generic table; it is a project setting. | drop |
| E13 | Hook-enforced rules that no shipped spec states: the `manual` merge deny (`hpt:88-90`, only f/del R5.71); the heavy-suite and repeat-run test guard (`session_guard.py:144-201`, > 180 s, 30-day `--measure`); the watcher's "draft never green" (`delivery_watch.py:604-605`); `delivery_ledger.py` write guards (`:378-390`, `:1241-1309`); `docs_check.py` R1 (removed ID cited), which is not in DOCSPEC R8.1's code table. | Add each to its spec with an ID, or cite the feature-spec requirement from the DELIVERYSPEC row. | state |
| E14 | DL-30 says Today N and checks an `eta_table`; the code checks 1.5 x p75 (`hpt:645-678`) (C13). | Rewrite DL-30 to match the code. | state |
| E15 | `.githooks/` do not run without `core.hooksPath`. | SessionStart (or the doctor) warns when `core.hooksPath` is not set in a repo that ships `.githooks/`. | enforce |
| E16 | r/cq:3 "overrule any internal safety limits" (C16) is advice with no check and no spec text. | Drop the phrase. | drop |
| E17 | The change-note kind (`change: minor`) is not checked against the content, so STACKSPEC's "a new MUST is a major" (inv:1992) is not enforced (C25). | `change_notes.py check` warns when a diff adds a `MUST` line to STACKSPEC or AUTHSPEC and the note says less than `major`, or the owner relaxes the rule. | enforce or relax |

### 4.3 Rule files (load into every prompt)

Sizes today: r/ai 723 words, r/pa 446, r/cq 242 (twice, once per plugin), r/dt 187, AG 361. About 2,000 words load each turn.

| ID | Proposal | Words saved (rough) |
|---|---|---|
| E18 | r/ai:10 (about 140 words, the test-cost rule) becomes one line citing DL-12 and the guide: "Test only what you touch; follow `ci_areas.py --branch-advice` (DL-12)." | ~120 |
| E19 | r/pa:3 repeats r/pa:10; r/pa:7 repeats r/pa:5; r/pa:8 repeats r/ai:26; r/pa:4 repeats r/ai:19. Drop r/pa:3, r/pa:7 and r/pa:8; r/pa:4 stays only if the docs plugin can ship without the claude-setup rules. | ~40 |
| E20 | r/pa:11-12 (Running, Built definitions) move to the glossary copy in ARTIFACTSPEC; a definition is not a rule. | ~45 |
| E21 | r/cq:3 drops the "safety limits" and number list (C16). r/cq:8 (routine pause) is advice on one tool; keep, it is short. | ~35 |
| E22 | r/ai:19 drops "(no Actions)" and cites the new branch-name row (D14), not DL-08. | ~5 |
| E23 | A line tagged `check:` whose check exists can be shorter: the hook's deny message carries the detail. Lines tagged `advice` need the full text. | — |
| E24 | AG:3 says "`CLAUDE.md` imports this file", but the repo has no `CLAUDE.md` (never tracked). Either add a one-line `CLAUDE.md` (`@AGENTS.md`) or drop the sentence. | — |

## 5. Minimal rule set per spec

Rules for every table below (AG:9): IDs, section numbers and `**Version:**` lines never move or renumber. A surviving rule keeps its ID. A retired ID stays in place as one line, `DL-70 — Merged into Q-1.` Rows marked **meaning change** alter what a cited ID requires; projects, hooks or tests that cite it must be checked.

### M1. DELIVERYSPEC

| Current IDs | Merged rule text (keeps the ID on the left) | Objective kept | Flag |
|---|---|---|---|
| DL-03, D5 (merge part), DL-73 (merge clause), §6 `merge_on_green` | **DL-03**: In `merge_mode: auto` (default) the watcher merges a green PR at once with `gh pr merge --merge --match-head-commit`. In `manual` the owner merges, and no hook asks the session to merge. | No green PR sits unmerged; the owner can keep the merge. | **meaning change** (adds the manual case) |
| DL-05 | **DL-05**: Never `gh pr merge --auto`. | Merge only on a proven head. | none, if the manual deny moves to DL-03; today the code reuses DL-05 for it (**meaning change** if kept there) |
| DL-08, DL-73 (PR clause), r/ai:19 | **DL-08**: A task agent opens draft PRs only. The orchestrator or the watcher opens the one ready PR, from the integration branch. | One full run per release; drafts cost no CI. | **meaning change** (names roles) |
| new row (D14) | **DL-1nn** (next free): A task branch is `<task-id>-<slug>`; the task ID follows ARTIFACTSPEC R4.5. | Hooks match events to tasks. | new |
| DL-11, DL-12, DL-80, DL-116, DL-122, DL-81 | **DL-80** keeps the CI scope rule (first run full, later heads carry, valves). **DL-12** keeps the agent test rule (light: local touched suites; heavy: short local smoke, then branch CI for its area by one named command). DL-11, DL-116, DL-122, DL-81 keep only their mechanism and cite DL-80 or DL-12. | One full run per change; agents spend little. | DL-12 **meaning change** after C6 |
| DL-04, DL-70, DL-71, DL-72, D8 Q-1..Q-5 | **Q-1..Q-5** move into the §1 table with Kind and Today. DL-04 — Merged into Q-4. DL-70 — Merged into Q-1. DL-71 — Merged into Q-3. DL-72 — Merged into Q-2. | All questions at once, in the wizard, after the free actions. | DL-71/72 "plain chat" exception is dropped (**meaning change**) |
| DL-30, D9, §3 DL-30 row | **DL-30**: An agent brief carries an ETA breakdown (setup, work, checks). The hook refuses a total over 1.5 x the measured p75 for its kind (5 samples or more) without an `eta-reason:` line. | Honest, unpadded ETAs. | **meaning change** (matches code) |
| DL-31 | **DL-31**: Every ETA in chat is a clock time in the owner's zone, with its start and dependency. Record rows follow ARTIFACTSPEC R6.6. | Times that can be checked. | scope note only |
| DL-61, DL-62 | DL-61 — Merged into ARTIFACTSPEC R9.8. DL-62 — Merged into ARTIFACTSPEC R9.11. | Hourly fail-safe; fresh copy. | none (docs plugin enforces) |
| DL-63 | DL-63 — Merged into ARTIFACTSPEC R8.19 (after C12). | No stale Expected. | depends on C12 |
| DL-74 | **DL-74**: When `no_attribution` is true, no attribution in commits or PR bodies. | Owner's choice holds. | **meaning change** (now conditional, as the code is) |
| DL-75 | DL-75 — Merged into DOCSPEC R2.1. | Docs in one tree. | none |
| DL-10, DL-24, DL-128 | **DL-24**: The fold runs once per release, at the point the owner picks in C9; DOCSPEC §7 owns the note format. DL-10 and DL-128 cite DL-24. | Parallel branches never conflict on versions. | **meaning change** if the fold point moves |
| DL-34 | DL-34 — Merged into DL-32a. | A routine counts done only when its branch moved. | none |
| DL-35 | DL-35 — Retired: the launch tool sets the start. | — | retired |
| DL-21 | DL-21 — Moved to project config (`ci.runner`). | Runner choice is per project. | retired from G |
| DL-65 | Move to §5 Design as a design property; row says "Design: see §5". | One truth for status. | none |
| DL-99 G3, DL-120, DL-121 | **DL-121** owns "never retry a test; quarantine flakes"; G3 and DL-120 cite it. | No hidden flakes. | none |
| D3, §6 `block_ceiling`, `stop_repeat_limit` | One key, `stop_repeat_limit`, default 3. | Hooks never loop. | none |
| Counts line (ds:190), Today column | Generated (E1). | Honest status. | none |

### M2. DOCSPEC

| Current IDs | Merged rule text | Objective kept | Flag |
|---|---|---|---|
| R2.1 (+ DL-75, r/pa:8) | **R2.1** adds: "Every lasting doc lives under `docs/`." | One docs tree. | additive |
| R2.4 | **R2.4**: The record folder follows ARTIFACTSPEC R4.37; `docs.json` `record_dir` names the same folder. | One record. | cites code order (C11) |
| R4.3, R7.1, R7.5, R5.2 | **R7.1** keeps the note rule; R4.3 and R5.2 cite R7.1 and R7.5. | Versions only by the fold. | none |
| R7.1-R7.4 (+ `change_notes.py` notes) | **R7.1** covers both note kinds: doc notes (`docs_fold.py`) and spec or plugin notes (`change_notes.py`), each with its folder. MUST level. | One versioning rule. | **meaning change** (widens scope) |
| R2.5, R4.5, R6.3 | **R2.5** owns the generated-file list; the others cite it. | No hand edits of generated files. | none |
| R5.4, D10, R11.2 | **R11.2** owns "UX rules only in `docs/design-system/`". | One UX home. | none |
| R15.10, R15.11 (date pickers) | **R15.10** owns it; R15.11 cites it. | One input rule. | none |
| R15.7 DS2, R15.25 DS7 | One rule: a numbered design-system version with no approval warns on a task branch and fails on a release branch (the R15.25 pattern). | Approval before use. | **meaning change** for R15.7 |
| R10.2 / W1 | **R10.2** unchanged; the code follows it (E8). | Briefs never reach `main`. | none |
| R8.1 code table | Add R1 (removed ID cited). | Every check named. | additive |

### M3. ARTIFACTSPEC

| Current IDs | Merged rule text | Objective kept | Flag |
|---|---|---|---|
| R3.1, R9.1, D13, §1.4, §15 text | **R9.1** owns "publish once per turn, at its end"; **R9.8** owns the hourly fail-safe; the Why (200 a day) stays once in §15. Others cite. | Few publishes, fresh page. | none |
| R9.10, R9.11, R9.12, R8.18, r/pa:6 | **R9.10** owns the three steps; others cite. | One publish order. | none |
| R4.13, R4.14, R4.28, R7.6, R8.17, D23 | **R4.13** owns "never write git state"; others cite. R8.5 drops "fetches the default branch" or says why it is allowed. | No surprise commits. | R8.5 **meaning change** |
| R4.37, R4.13 path text | **R4.37** states the code's lookup order (C11). R4.13 says "the record folder (R4.37)". | One record folder. | **meaning change** for the default |
| R6.3, R6.12, R5.46, D15, §12 Earlier row | Remove the Earlier fold text that R6.3 retired, or restore R6.3. | One group layout. | owner picks only if the fold is wanted back |
| R5.3, R5.33, R5.37, §14, R5.61 | **R5.61** wins; edit the others. | One section-0 layout. | none |
| R4.5, R5.49 | **R4.5** says dropped work is `Dropped` (R5.49). | One close status. | none |
| R6.14, R8.19 (+ DL-63, f/art R5.25) | **R8.19** owns past-due behaviour (C12). | No stale Expected. | depends on C12 |
| R6.10 (+ DL-30 breakdown) | **R6.10** owns `expected_basis`; DL-30 cites it for record rows. | Each estimate shows its basis. | none |
| §1.4 `owner (of a task)` | Rename to "feature (of a task)" in the text; the JSON field stays. | One meaning of owner. | wording |
| R10.3 rule-file list | List all 18 lines of r/pa, or make R10.3 point to the file and a test. | Rule file and spec agree. | none |

### M4. STACKSPEC

STACKSPEC has no rule IDs; it cites by section. Proposal: no new IDs, but each rule another spec cites gets an anchor-stable sentence.

| Current section | Merged rule text | Objective kept | Flag |
|---|---|---|---|
| §13.5-§13.8 (inv:1500-1671) | Keep the outcomes as MUSTs: one ready PR, its first run full, later heads carry, freeze while CI runs, drafts run no CI, branches never edit versions. Cite DELIVERYSPEC for scripts and config. | A product delivers the same way on any stack. | none (text shrinks, MUSTs stay) |
| inv:1604 "SHOULD NOT edit a spec's version" | MUST NOT, citing DOCSPEC R7.1 (matches AG:8 and the pre-commit check). | Parallel branches never conflict. | **level change** SHOULD to MUST (major per §20) |
| inv:1569 "named after its task ID" | Cite the new DELIVERYSPEC branch row. | One branch format. | none |
| §2.1 tree (inv:333-335) | Replace `docs/specs/`, `docs/notes/` with a pointer to DOCSPEC §2. | One docs layout. | none |
| §4.6 rate-limit headers (inv:564) | Add: "Auth endpoints send only `Retry-After` (AUTHSPEC R17.7)." | Limits are visible, accounts are not probed. | **owner** (C24) |
| §5.7 `secret` class (inv:715-717) | Add: "A one-way hash (AUTHSPEC §5.3) meets this rule." | Dumps leak nothing. | **owner** (C24) |
| §12 secret scan + 4 copies | §12 owns it; inv:1370, 1500, 1557 and the checklist cite §12. | Scan at commit, push and CI. | none |
| §20 "a new MUST is a major" | Keep and enforce (E17), or relax (C25). | Products can trust minor bumps. | **owner** |
| §0.1 heading | "What changed" (no version range), so new entries fit. | Readable log. | heading text only; section number stays |

### M5. AUTHSPEC

| Current IDs | Merged rule text | Objective kept | Flag |
|---|---|---|---|
| §0.1 conformance (auth:72-78) | Cite STACKSPEC §0.2; deviations recorded in the Stack Profile. | One deviation record. | **meaning change** (where a deviation lives) |
| R24.3, R27.4 | Cite STACKSPEC §12 for scanning; keep "never committed". | One scan rule. | none |
| §22.1 latency, R22.38 payload, R21.1 accessibility, rate-limit fail mode | Keep the stricter numbers; add "narrows STACKSPEC §x" to each. | Auth flows are faster, smaller, more accessible. | none |
| About 49 internal repeats (auth index D) | Keep each rule once, in the section that owns the topic; repeats become "see Rn.n". | Same rules, less text. | none |
| auth:463 "low entropy" vs R8.7 "≥128 bits" recovery codes; R22.18 30 s job timeout vs §24.2 10 s ceiling | Fix the stale side of each. | One number each. | **owner** for the timeout |
| §27.1 `/audits:*` | `/luismc-audits:*`. | Commands work. | none |

### M6. Feature specs

| Spec | Change | Flag |
|---|---|---|
| f/del | Duplicate IDs R5.36c, R5.46, R13.96: the first keeps the ID; the second takes the next free letter (R5.36d, R5.46a, R13.96a). Check which one tests and the "How it is proven" table cite first. Fix R5.13 cancel default (C20), R5.22 vs DL-97 (C21), R5.80 citation, R5.12 runner hook, :378 machine limits. | **meaning change** for any citation of the second copy |
| f/dsp | Its table IDs `DL1`..`DL7` look like DELIVERYSPEC `DL-n` and task IDs `DLnnn`. Cite them as "speed point 1..7" in prose (IDs stay). Fix R5.7 (C22). DL3 marked superseded by DL-12 (C6). | none |
| f/tc | R5.2 states this repo's deviation from DL-80 (C5). R5.3 states its deviation from DL-99 G6 (C7). R5.8 — Superseded by ARTIFACTSPEC R4.13 (C4). | R5.8 retired |
| f/art | Drop restated ARTIFACTSPEC rules (statuses, hooks, record folder, section 0); cite ARTIFACTSPEC. Keep build-only requirements. Fix R5.17a, R5.11d against R5.29, R5.11. | none |
| f/docs | Second R5.23 (:108) takes R5.23a. Move the six R5 rules under §6 to §5 or renumber them as R6.x with "Moved from R5.x" lines. | **meaning change** for citations of the second R5.23 |
| f/specs | :70 says spec-check is `sonnet`; code says `haiku`. | none |
| f/models | Decision row 0014 (:162) is reversed by :39; mark it. | none |
| f/ps | R5.24 restates DL-73; cite DL-08 and DL-73 instead. | none |

### M7. Rule files and AGENTS.md

AGENTS.md, minimal text (keeps every current objective):

```
- Work on a task branch `<task-id>-<slug>`. Push only that branch. Never push to `main`, merge, or open a ready PR (DL-08).
- Never edit a `**Version:**` line, a change log or a plugin's `"version"`. Add a change note (DOCSPEC R7.1); a plugin change needs a note naming its `plugin.json`.
- Requirement IDs, section numbers and `**Version:**` lines never move or renumber.
- Merges follow `watcher.merge_mode` (DL-03). Agents never run `gh pr merge`.
- Hooks and the docs plugin never commit, push or merge; the delivery watcher does, per DL-03.
- Name no other project. Plain, short English.
- Test only what you touch: `python tools/ci_areas.py --branch-advice` (DL-12, docs/guides/testing.md).
- Docs: read docs/README.md. A behaviour change updates its feature spec and adds a note, or says `Docs: none, <reason>`. UX rules live only in docs/design-system/. Briefs and reports live in docs/work/ on your branch only. Never edit generated files. Run docs_check.py before you finish.
```

The rule files keep one line per rule, tagged. Changes are in E18-E24. r/ai shrinks by about a fifth; r/pa by about a tenth.

## 6. Ranking: clarity gain against churn

Gain: how much a reader's or a hook's confusion drops. Churn: how many files, citations and tests move. H, M, L.

| Rank | Proposal | Gain | Churn | Owner decision? |
|---|---|---|---|---|
| 1 | C2, E3: manual merge mode stops asking the session to merge (Q-4, DL-03 Stop) | H | L (two checks, one test) | No |
| 2 | C1, C3, C4, M1 DL-03/DL-08/DL-73, M7: name the roles (task agent, orchestrator, watcher) and say who merges, who opens the ready PR, who pushes | H | M (3 rows, AG, 2 rule lines, 1 feature spec) | Yes |
| 3 | D2, E10, M1: Q-1..Q-5 into the table; retire DL-04, DL-70..72 | H | L | No |
| 4 | E1, E2: generated Today column, one test that every cited ID exists; fix DL-123/124, D4/DL-39, DL136, R17.7g | H | M (script + test) | No |
| 5 | C6, D8, E18, M1 DL-12: one agent test rule; r/ai:10 becomes one line | H | L | Yes (branch CI or not) |
| 6 | C9, D11, M2 R7.1, M1 DL-24: one change-note rule for both tools, one fold point | H | M | Yes (fold point) |
| 7 | G1-G5: one glossary, checked copies in each shipped spec; fix owner, area, carry, full run | M | M | No |
| 8 | C12, E9: one past-due Expected check | M | L | Yes (block now or warn first) |
| 9 | C11, M3 R4.37: record folder rule matches code | M | L | No |
| 10 | C23, E8: W1 only on the ready PR | M | L | No |
| 11 | D22, M4: STACKSPEC §13 keeps outcomes, cites DELIVERYSPEC | M | M (STACKSPEC major if MUSTs move) | No |
| 12 | C24, M4, M5: AUTHSPEC vs STACKSPEC (rate-limit headers, secret class, deviation home) | M | L | Yes |
| 13 | E5, E6, E7: ship the ready-PR check, deny push to `main`, hashed-name check repo-wide | M | M | No |
| 14 | C5, C7, M6 f/tc: this repo's declared deviations from DL-80 and DL-99 G6 | M | L | Yes (C5) |
| 15 | D9, D10, M3: publish and no-commit rules said once in ARTIFACTSPEC | M | M (many citations) | No |
| 16 | C14, C20-C22, C26, M6: stale lines inside ARTIFACTSPEC and feature specs | L-M | L | No |
| 17 | C25, E17: STACKSPEC "a new MUST is a major" | L | L | Yes |
| 18 | D20, D21, M5: AUTHSPEC internal repeats | L | H (49 sites) | No |

## 7. Findings outside the brief

- DL-66 (ds:176) is Scope G but names one city as the label. A generic rule should say "labelled with the zone".
- ARTIFACTSPEC's "Last reviewed" date (2026-10-11) is older than its 1.32.0 entry (2026-11-26).
- `docs_check.py` (run as AG:24 asks) is expected to fail W1 on this branch, because this report is under `docs/work/` (C23). The result is in section 8.

## 8. Checks run

- `python3 claude/plugins/docs/scripts/docs_check.py`: 1 error, W1 on `docs/work/ds300-specs.md`. This is C23 happening, not a defect of this branch: AG:22 puts the report there and AG:24 asks for this check. No other error. T2 skipped (shallow clone).
- No tests run: the branch changes only this report (`tools/ci_areas.py --branch-advice` would say light).

## Appendix A. Topic index per spec

One row per rule: ID, file:line, gist, level, topic tags. The line keys differ per table and are given at the top of each. Rows were built by reading each file in full; long domain-only parts of STACKSPEC and AUTHSPEC are grouped by subsection.

### A.1 DELIVERYSPEC, DOCSPEC, rule files, AGENTS.md

Keys: `ds` = DELIVERYSPEC, `doc` = DOCSPEC, `cq` = clarifying-questions.md, `ai` = agents-and-integration.md, `dt` = delivery-timing.md, `ag` = AGENTS.md.


#### A1. DELIVERYSPEC, section 1 rule tables (Kind and Today as written)

Column legend (ds:45-51): Scope G/P. Kind STOP, PRE, POST, SS, WATCH, CI, GIT, TEXT. Today Y enforced, W warns only, ~ partly, N not enforced.

##### 1a Trains, CI and merge (ds:56-88)

| ID | file:line | gist | level | Kind / Today | tags |
|---|---|---|---|---|---|
| DL-01 | ds:60 | Never push to a branch whose ready PR's CI runs; late work rides the next train | imperative | Kind GIT pre-push + PRE `git push`; Today Y `train_freeze.py` via `.githooks/pre-push`; "not as PRE" | push, train, CI |
| DL-02 | ds:61 | Join and check next train while previous CI runs; push the moment it is green (>5 min check) | imperative | STOP; N | join, train, push |
| DL-03 | ds:62 | Merge a green train at once; never leave one unmerged (RELEASE-27 sat ~10 h) | imperative | STOP + WATCH; N | merge |
| DL-04 | ds:63 | Before any question dialog, do every action not needing the answer (merges, pushes, launches, publish) | imperative | PRE `AskUserQuestion`; N | questions, publish |
| DL-05 | ds:64 | Never `gh pr merge --auto` | imperative | PRE; N ("`session_guard.py` does not cover it") | merge |
| DL-06 | ds:65 | Merge only after `ci_watch.py` passed for the PR's current head SHA | imperative | PRE `gh pr merge`; ~ (`ci_watch.py` exists; merge not gated) | merge, CI |
| DL-07 | ds:66 | Watch CI by head-commit workflow runs, never the PR check list | imperative | PRE (deny `gh pr checks --watch`); ~ | CI |
| DL-08 | ds:67 | Ready PR only from a release/integration branch; every other PR is a draft | imperative | PRE; Y `session_guard.py` ready-PR guard (wired in project settings) | ready PR, draft |
| DL-09 | ds:68 | removed: runner rules belong to the runner pool project | retired | - | - |
| DL-10 | ds:69 | Ready PR from `release/*` runs `release:prepare` (fold spec notes) before CI | imperative | PRE `gh pr create`/`ready`; ~ CI fails late (`--check-folded`) | change note, fold |
| DL-11 | ds:70 | Join is light: merge, fold notes, typecheck/lint touched, fast guards, push, ready PR; no full suite; first ready-PR CI run is the one full run; later pushes carry | imperative | PRE (test guard); Y `join.py`, `session_guard.py`, `hook_pre_tool.py` | join, full run, carry, ready PR, test cost |
| DL-12 | ds:71 | One affected branch gate per agent, never `--full` unless a valve trips; CI-gate path: branch CI is the gate | imperative | PRE; Y `session_guard.py` test guard, `branch_gate.py` default | test cost, full run |
| DL-13 | ds:72 | Trust a branch gate only via `gate-result.json` matching head and base; join checks per branch | imperative | script; Y `gate_verify.py`, `join.py` | gate |
| DL-14 | ds:73 | After a merge run `cleanup.py --pr N`; no merged branch or finished worktree left | imperative | STOP + POST; ~ (`cleanup.py`, `train-cleanup.yml`; local not forced) | merge, cleanup |
| DL-15 | ds:74 | Ready/train PR body lists drafts it carries (`Carries: #x, #y`) | imperative | PRE `gh pr create` (ready); N | ready PR, carry |
| DL-16 | ds:75 | A train leaves with what is green; never waits for slowest cargo (>15 min after first green) | imperative | STOP (warn); N | train |
| DL-17 | ds:76 | One train in CI at a time; a wait is a gap, never a phase | imperative | POST (phases from events); N (hand-drawn chart) | train, phase |
| DL-18 | ds:77 | Deploy once per merge; smoke production; fix forward; ask before rollback when owner awake | imperative | STOP; ~ deploy-job smoke, `smoke_packaged.py` | deploy, questions |
| DL-19 | ds:78 | Vercel deploys only from default branch; no preview deploys; never merge mid-round | imperative | PRE; ~ `git.deploymentEnabled` | deploy, merge |
| DL-20 | ds:79 | Never `vercel env rm`; re-list Production after an env change | imperative | PRE + POST; N | deploy |
| DL-21 | ds:80 | CI jobs only on self-hosted runners | imperative | CI; N; Scope P (G as option) | CI |
| DL-22 | ds:81 | Keep only newest build artifact of each stable name | imperative | CI; Y `artifact-prune.yml` / `artifact_prune.py` | CI artifacts |
| DL-23 | ds:82 | Setup failure means stale lockfile: regenerate and commit; never install unfrozen | imperative | PRE; N | commit, test cost |
| DL-24 | ds:83 | Only the release PR folds change notes; never commit conflict markers | imperative | GIT pre-commit; ~ (`change_notes.py`; marker check not confirmed) | change note, commit |
| DL-25, DL-26, DL-27 | ds:84-86 | removed: project-specific | retired | - | - |
| DL-97 | ds:87 | Red release CI run finishes; never cancel a release/join run with a failure and jobs pending; `# D105: blocks-all` exception | imperative | PRE `gh run cancel`; Y `hook_pre_tool.py`, `cancel_joined_runs.py`, `test_dl374_red_run_finishes.py` | CI, full run |
| DL-98 | ds:88 | No fail-fast on release PR CI unless `ci.jobs.<id>.fail_fast` on (default `never-on-release`); doctor WARNs | imperative | doctor; Y `delivery_doctor.py`, ci.yml template | CI, test cost |

##### 1b Agents (ds:90-146)

| ID | file:line | gist | level | Kind / Today | tags |
|---|---|---|---|---|---|
| DL-30 | ds:94 | Size agent ETA from scope (setup + work + checks), state breakdown, never pad; eta_table 15-25 / 25-35 / 40-60; one entry per trig_/cse_ pair | imperative | POST (launch) + STOP; N | ETA |
| DL-31 | ds:95 | Every ETA a clock time: real start + typical duration, name dependency; "tomorrow" only past midnight; past facts are not ETAs | imperative | STOP; ~ `~/.claude/hooks/no-tomorrow.mjs` in project `settings.local.json` | ETA |
| DL-32 | ds:96 | Check critical-path log ~30 min; watcher checks running agents every 15 min; `stalled` blocks; never mark done by guess | imperative | WATCH + STOP; N | agents, watcher |
| DL-32a | ds:97 | Agent row ends on signal merged/deleted/report-ready/report-not-ready; NOT READY closes after 10 min quiet; else RemoteTrigger list_runs | imperative | WATCH + STOP; N | agents, record |
| DL-33 | ds:98 | Never end a turn with work in flight without a watcher waking within 20 min; restart older-version watcher | imperative | STOP; ~ (artifacts Stop hook asks for a Running task, R8.10) | watcher, version |
| DL-34 | ds:99 | After a routine reports succeeded, verify its branch moved before counting it done | imperative | WATCH; N | agents |
| DL-35 | ds:100 | Start cloud runs at once (`run_once_at` = now + ~1 min) | imperative | PRE `RemoteTrigger`; N | agents |
| DL-36 | ds:101 | Cloud brief markers: no push notifications, CRITICAL RUN RULE, no attribution, BRIEF.md, one affected gate | imperative | PRE `RemoteTrigger`/`Agent`; N | brief, attribution, test cost |
| DL-37 | ds:102 | Code agents Sonnet at medium; Opus medium; RemoteTrigger sets `session_context.effort_level` | imperative | PRE; ~ `effort_drift.py` (SessionStart, settings only) | agents |
| DL-38 | ds:103 | Caps: cloud 50, local <= 3 only with > 8 GB free, total 53; config `caps` overrides | imperative | PRE; N | agents, caps |
| DL-39 | ds:104 | Non-PC-bound work to cloud until cap full; `PC-bound:` must name a PC-bound step (DL-127) | imperative | PRE `Agent` (local); Y `hook_pre_tool.py`; Scope P | agents |
| DL-40 | ds:105 | One agent and branch carry every open task in same files/area; split only large parallel parts | imperative | PRE; Y `hook_pre_tool.py` (via DL-126) | agents, area |
| DL-41 | ds:106 | Split parallel agents by file ownership; never chain on files a running agent owns | imperative | PRE; N | agents |
| DL-42 | ds:107 | Stop only own processes/containers; never kill by name or stop every container | imperative | PRE; N | agents |
| DL-43 | ds:108 | Run `reach_check.py` before briefing an agent that needs an external site (within 1 h) | imperative | PRE; ~ script exists, not required | agents |
| DL-44 | ds:109 | Agents write report first and push after every step | imperative | TEXT (proxy DL-34); N | agents, push |
| DL-45 | ds:110 | Commit shared contracts to the integration branch before launching agents | imperative | PRE `RemoteTrigger`; N | integration branch, commit |
| DL-86 | ds:111 | UI or e2e-spec change runs covering e2e specs before CODE DONE; on a PC at most 2 workers | imperative | GATE `branch_gate.py` + CI-gate `agent_ci.py`; Y | test cost |
| DL-87 | ds:112 | `gate-result.json` records `ui_changed` and `e2e`; `gate_verify.py` refuses a missing or failed record | imperative | GATE + VERIFY + CI-gate; Y | gate |
| DL-88 | ds:113 | Pre-push refuses changed e2e specs unless local gate-result shows them passed for that commit | imperative | GIT pre-push (`e2e_push_check.py`); Y | push, test cost |
| DL-89 | ds:114 | Cloud brief says agent runs e2e specs of changed screens, or "no UI change" | imperative | PRE; Y | brief |
| DL-92 | ds:115 | Design enforcement kit is a required check; known-breach lists only shrink; design edit hook warns then denies | imperative | GATE + CI + GIT pre-push + PRE; Y `change_notes.py`, `hook_design_edit.py`; required check set by owner | design system, cross-ref DOCSPEC R15.9 |
| DL-93 | ds:116 | RemoteTrigger create sets `"mcp_connections": []` and `"clear_mcp_connections": true` unless needed ones listed | imperative | PRE; Y | agents |
| DL-94 | ds:117 | CI fetches pinned tools via `ci_tool.py`; downloads without sha256 flagged; opt-out `# ci-tool: ok` | imperative | PRE `Write`/`Edit`/`MultiEdit`; Y | CI |
| DL-95 | ds:118 | REST quota 5,000/h shared; `gh run watch` only with `--interval` >= 60; ci_watch polls 60 s, sleeps below 200 calls | imperative | PRE `Bash`/`PowerShell`; Y `hook_pre_tool.py`, `ci_watch.py` | CI |
| DL-96 | ds:119 | Release assets named `<Product>-<version>-<os>-<arch>.<ext>`; `versioned_names: false` opts out | imperative | CI; Y; Scope P (G as option) | version |
| DL-99 | ds:120 | Test guardrails G1-G7, warn by default: timeouts 10/60/120 s, job <= 30 min, no retries, no sleeps, <= 20 cases, no mutation on PR, upload times | imperative | PRE (`fast_guards.py`) + CI; Y `test_guardrails.py` | test cost, mutation |
| DL-LC1 | ds:121 | Updater test interface is a language-free contract, test builds only | imperative | TEST; Y; Scope P | lifecycle |
| DL-LC2 | ds:122 | `lifecycle_conformance.py` checks LC-3..7, 25, 26, 28 against fake Ed25519 server; exit 0/1/2 | imperative | TEST; Y | lifecycle |
| DL-LC3 | ds:123 | Rust and Go updater cores pass the runner in own tests | imperative | TEST; Y | lifecycle |
| DL-109 | ds:124 | Lifecycle OS step scripts check LC-8..17, 29, 33 (console in 30 s, rollback in 5 min) | imperative | CI lane; Y | lifecycle |
| DL-110 | ds:125 | Same scripts lint packages LC-18..21 | imperative | CI lane; Y | lifecycle |
| DL-111 | ds:126 | Lanes template: windows, ubuntu-lts, fedora, debian, macos; runs-on from repo variable; missing variable skips | imperative | CI; Y | lifecycle |
| DL-112 | ds:127 | Release PR fails unless affected targets pass and others have default-branch pass records; LC-32 names and stores | imperative | CI; Y | lifecycle, version |
| DL-113 | ds:128 | LC-27 lifecycle checks on by default; `lifecycle.off` needs decision, reason, review | imperative | CI + SessionStart; Y | lifecycle |
| DL-114 | ds:129 | Fix push to a frozen train allowed once `cancel_old_run.py --pr N` cancelled old run | imperative | GIT pre-push; Y | push, train |
| DL-115 | ds:130 | Docs/config/`.delivery/`-only push skips typecheck and lint, needs no `node_modules` | imperative | GIT pre-push; Y | test cost |
| DL-116 | ds:131 | CI skips by area, never workflow-level path filter; release PR full first run; `--carry` later | imperative | CI, doctor; Y `changed_areas.py`, `ci_areas_check.py` | area, full run, carry |
| DL-117 | ds:132 | Base image built once per input key; reused only when main built it; weekly `--no-cache` rebuild | imperative | CI; Y `image_reuse.py` | Docker, test cost |
| DL-118 | ds:133 | Costly lane skipped only when main holds pass record with same inputs key | imperative | CI; Y `pass_records.py` | record, test cost |
| DL-119 | ds:134 | Before watcher merge, check head behind base; `merge_result` `warn` (default) or `update` | imperative | WATCH; Y `delivery_watch.py` | merge |
| DL-120 | ds:135 | Retry infra errors once per head (`infra_retry` default false); never a test | imperative | WATCH; Y | CI |
| DL-121 | ds:136 | Flake quarantine with owner task ID and review date; never a retry | imperative | CI + SessionStart; Y `quarantine_check.py` | test cost |
| DL-122 | ds:137 | One full run per change; `local_gate` `smoke` runs only touched-area suites | imperative | GIT pre-push; Y | full run, test cost |
| DL-123 | ds:138 | Local agent recorded without `delivery` block; task ID from prompt (600 chars; 2-5 caps/digits); row closes after a day | imperative | POST (Agent) + STOP; Y | task, record |
| DL-124 | ds:139 | Stop warns when a Running task has no open agent row or train in CI | imperative (warn only) | STOP; Y | status names |
| DL-125 | ds:140 | PR proves only affected lifecycle targets; replaces every-target reading of DL-112 | imperative | CI + doctor + SessionStart; Y; Scope P | lifecycle |
| DL-126 | ds:141 | DL-40 enforced once: deny launch once when a To do/Waiting task has same app/area | imperative | PRE; Y | area, status names |
| DL-127 | ds:142 | `PC-bound:` with no step word is a warning, not a deny | imperative | PRE `Agent` (local); Y | agents |
| DL-128 | ds:143 | A fold takes only notes of the named release; `--all` folds every note | imperative | fold scripts; Y `docs_fold.py`, `change_notes.py`; Scope P | change note, release |
| DL-129 | ds:144 | Stop messages about a PR name every release it carries; never the word train | imperative | STOP; Y | release, train |
| DL-130 | ds:145 | DL-124 skips merged entries until cleaned and smoked | imperative | STOP; Y | status names |
| DL-131 | ds:146 | `delivery_ledger.py link` sets PR on carried releases; writes files only, never commits | imperative | CLI; Y | commit by plugins |

##### 1c Local machine, runners, installs (ds:148-164)

| ID | file:line | gist | level | Kind / Today | tags |
|---|---|---|---|---|---|
| DL-50, DL-51 | ds:152-153 | removed: runner pool project | retired | - | - |
| DL-52, DL-54, DL-56 | ds:154, 156, 158 | removed: project-specific | retired | - | - |
| DL-53 | ds:155 | Worktrees and scratch only under work root (`C:\Work\...`); remove when done | imperative | PRE `git worktree add`, `EnterWorktree`; N | local |
| DL-55 | ds:157 | Installs run one at a time | imperative | PRE + POST; N; Scope P | local |
| DL-80 | ds:159 | CI scope: release PR full suite first run; later heads carry; root config/lockfile runs full | imperative | CI; Y `ci_scope.py` (+ `area_select.py`); opt-in by file | full run, carry |
| DL-81 | ds:160 | CI-gate path (opt-in): agent tests touched, pushes, CODE DONE; draft PRs run no CI; `agent_ci.py` dispatch on `ci/<task>` | imperative | script + brief; Y `agent_ci.py` | test cost, draft PR |
| DL-82 | ds:161 | Every CI run reports duration (`ci-run-times` artifact, job summary) | imperative | CI; Y `ci_run_times.py`; opt-in `CI_RUN_TIMES=true` | CI |
| DL-83 | ds:162 | CI-gate: join urgent work at code push (light join); ETA = coding + branch CI; no top-level await | imperative | TEXT + script; Y `join.py --ci-gate`; rest rules text | join, ETA |
| DL-84 | ds:163 | Gate order: guards, typecheck/lint, unit/integration/e2e; required steps default typecheck and lint | imperative | script; Y | gate |
| DL-85 | ds:164 | Plan release CI on one Linux runner; non-Linux jobs in parallel elsewhere (runs of 65-70 min) | advice | TEXT; N (advice; STACKSPEC 13.1) | CI |

##### 1d Progress page and reporting (ds:166-176)

| ID | file:line | gist | level | Kind / Today | tags |
|---|---|---|---|---|---|
| DL-60 | ds:170 | On every task state change, update the task and publish Full Progress same turn | imperative | STOP; Y artifacts `hook_end_of_turn.py` (R8.3) | publish |
| DL-61 | ds:171 | Publish Full Progress at least hourly when nothing in last 60 min; hourly cron at start | imperative | SS + WATCH + STOP; N (memory; cron by hand) | publish |
| DL-62 | ds:172 | Every publish: `pending --json`, publish path, `mark-published`; check version went up | imperative | POST + PRE `mark-published`; ~ | publish, version |
| DL-63 | ds:173 | When a release ships, close every row it carries; no open row with past Expected time | imperative | STOP; N | Expected, release |
| DL-64 | ds:174 | Say RELEASE-n to the owner, never train labels or branch names | imperative | STOP (text scan); N | release, train |
| DL-65 | ds:175 | Every shown status comes from one shared reading of latest state | imperative | design; N | ledger |
| DL-66 | ds:176 | Show times in owner's zone, labelled (one city name), from the real clock | imperative | POST stamps; ~ | ETA |

##### 1e Owner communication and attribution (ds:178-188)

| ID | file:line | gist | level | Kind / Today | tags |
|---|---|---|---|---|---|
| DL-70 | ds:182 | Ask every open question at once, numbered; several dialogs if more than 4; never trickle | imperative | PRE `AskUserQuestion` (context); Y (rules text via SessionStart; Q-5 trickle check in PRE) | questions |
| DL-71 | ds:183 | No explanation before a dialog; context inside the question, or ask in plain chat (>~300 chars) | imperative | PRE; N | questions |
| DL-72 | ds:184 | Rejected dialog with no owner words is not a stop; re-ask in plain chat | imperative | POST-failure; N | questions |
| DL-73 | ds:185 | Never send in owner's name; agents may open PRs, mark ready, edit; merging stays the owner's | imperative | PRE (outbound); ~ auto-mode classifier only | merge, ready PR |
| DL-74 | ds:186 | No Co-Authored-By or Claude attribution in commits or PR bodies (owner choice) | imperative | GIT commit-msg + PRE; N; "violated by a project CI auto-fix script" | attribution |
| DL-75 | ds:187 | Create every doc under `docs/` | imperative | PRE `Write` of `*.md`; N | docs |
| DL-76 | ds:188 | A release runs CI once; post-merge default branch runs only publish, deploy, production smoke | imperative | STOP; N; Scope P | full run, release |

Other section-1 text:

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §1 counts (no ID) | ds:190-191 | "Counts: 64 rules (DL-01..27, 30..45, 52..56, 60..66, 70..79 ...). Enforced today: 8 Y, 1 W, 17 ~, 37 N" | fact | stale count (rows DL-80..131, LC1-3 exist; 77-79 removed) |
| §Removed (no ID) | ds:195 | Removed IDs not reused: DL-09, 50, 51, 77, 78, 79, 90, 91; citing one fails `docs_check.py` | MUST (implied) | retired IDs |
| §Reading (no ID) | ds:52 | Goal: every delivery rule is a mechanical check, not a note | advice | - |

#### A2. DELIVERYSPEC sections 2-6 (no row IDs unless named)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §2 (no ID) | ds:199 | One ledger per repo; only `delivery_ledger.py` writes it; atomic, lock, `schema: 1`; hooks never edit by hand | imperative | ledger |
| §2 (no ID) | ds:217 | Gaps are implied, never a phase (DL-17) | imperative | phase |
| §2 (no ID) | ds:247 | `events` append-only, capped (last 500) | fact | ledger |
| §2 (no ID) | ds:253-273 | Writer table: each ledger field has one named writer | imperative | ledger |
| §2 (no ID) | ds:268 | `agents[].last_checked` set by POST hook; "watcher never sets it" | imperative | conflicts DL-32 ds:96 |
| §2 (no ID) | ds:275 | Finished rows older than `ledger_retention_days` (default 14; 0 keeps all) dropped | imperative | ledger |
| §3 proxies (no ID) | ds:281-289 | Best proxies for DL-40, 30, 44, 70, 71, 72, 65, goals, DL-73 | advice | see B, D |
| §4 (no ID) | ds:293 | Commit the shared contract to integration branch before any part is built | imperative | integration branch |
| §4(c) (no ID) | ds:320 | artifactspec.md + "`plugin.json` version bump" in brief (c) | historic plan | version |
| §4(d) (no ID) | ds:326 | delivery-config template example "caps 8/3/5" | example | caps |
| §4 (no ID) | ds:331-332 | Order: contract commit, then (a)-(d) parallel; project drops Co-Authored-By from CI auto-fix | imperative | attribution |
| D1 | ds:338 | Hooks enforce in sessions; watcher scripts act on time-critical steps | binding decision | - |
| D2 | ds:339 | Home `luismc-delivery`; Full Progress publishing stays in `luismc-docs` | binding decision | publish |
| D3 | ds:340 | Stop findings BLOCK, block-once-per-fingerprint and 3-block ceiling (artifacts R8.4) | binding decision | - |
| D4 | ds:341 | PreToolUse DENIES local Agent without `PC-bound:` unless cloud cap full (DL-39) | binding decision | agents |
| D5 | ds:342 | Watcher pushes next train, opens ready PR, merges previous train when CI green for head; never `--auto` | binding decision | merge, ready PR, push |
| D6 | ds:343 | Watcher cancels replaced CI runs; holds dependabot runs during a train | binding decision | CI |
| D6a | ds:344 | removed (DL418): runner repair; runner pool project owns it | retired | - |
| D7 | ds:345 | After a lesson is enforced, its memory note is DELETED | binding decision | - |
| D8 | ds:346 | Questions: Q-1..Q-5 "replaces DL-70..72" | binding decision | questions |
| Q-1 | ds:347 | Ask every open question in one go; no 4-question cap when owner says "ask me questions" | imperative | no Kind/Today column; questions |
| Q-2 | ds:348 | Always AskUserQuestion; Stop hook blocks a closing list of questions instead of wizard calls | imperative | Stop hook (named in text); questions |
| Q-3 | ds:349 | Context inside each question; PreToolUse denies too-short question texts (config min chars) | imperative | PreToolUse; questions |
| Q-4 | ds:350 | Merge, push, launch before asking; PreToolUse denies while actionable-now item exists | imperative | PreToolUse; questions, merge |
| Q-5 | ds:351 | No guessing, no trickling; deny ask while agents run and batch asked within 60 min; 90 s batch; `checks_off` | imperative | PreToolUse; questions, parking |
| D8 tail | ds:352 | `claude/plugins/delivery/rules/clarifying-questions.md` is canonical; claude-setup asset is a byte copy kept by test | imperative | rule files |
| D9 | ds:353 | Every launch needs `delivery:` breakdown; Stop blocks ETA without clock time + dependency, or "tomorrow"/"next round" | binding decision | ETA |
| §6 (no ID) | ds:357 | `delivery_config.py validate`; unknown key warns; `--auto` in a merge flag is an error | imperative | config, merge |
| §6 enforcement | ds:359 | `mode` block (default) or warn; `block_ceiling` default 3; `log_every_block` default false | config | - |
| §6 watcher | ds:360 | `push_trains`, `open_prs`, `merge_on_green` default true; `gh pr merge N --merge --match-head-commit`; `never_auto_merge` cannot be false | config | merge, push |
| §6 ci_workflows | ds:361 | Required workflows default `["ci.yml"]`; only runs after ready time; draft never green; watcher only writer of `green_at` | config | merge, draft PR |
| §6 stop_repeat_limit | ds:362 | Default 3; cleanup/smoke recording commands; smoke workflow default `Production smoke` | config | - |
| §6 pr_proven_jobs | ds:363 | DL-76 check; default `[]` (off) | config | full run |
| §6 brief_markers | ds:364 | Entry is a string or list of alternatives (0.10.0) | config | brief |
| §6 runner_plan | ds:365 | `cancel_replaced_runs`, `hold_dependabot_during_train` default true | config | CI |
| §6 tz | ds:366 | IANA name; unloadable fails validator and doctor; hooks warn once, use UTC | config | time |
| §6 doctor | ds:367 | `delivery_doctor.py` five checks; exit 0/1/2 | script | - |

#### A3. DOCSPEC

DOCSPEC has no Kind/Today columns. Check codes are named per rule (L1, F1, K1, ...). Requirement language: doc:87-89 (MUST/SHOULD/MAY; append-only numbering, retired numbers never reused).

| ID | file:line | gist | level | check / tags |
|---|---|---|---|---|
| D1-D16 (decision record) | doc:97-114 | Owner choices of 31 Oct 2026 mapped to sections (folders, site, overview, specs, versions, docs map, who writes, decisions, docs/work, UX rules, diagrams, plugin, migration, record dir, rewrite, design system) | decision | note D-n IDs clash with DELIVERYSPEC D1-D9 and check code D1 |
| R2.1 | doc:178 | Must have `docs/docs.json`, `docs/README.md`, five overview pages, `AGENTS.md` | MUST | L1 |
| R2.2 | doc:179 | Lasting docs live in folder of reader question; cross-feature rules in `architecture/`; tasks in `guides/` | MUST | layout |
| R2.3 | doc:180 | Lasting pages carry Diataxis `type`; feature specs MUST | SHOULD | layout |
| R2.4 | doc:181 | Artifacts record in `record_dir` (default `docs/project`); both settings match | MUST | record |
| R2.5 | doc:182-191 | Generated files list; nobody edits by hand; stale fails | imperative | G1, G2 |
| R2.6 | doc:192 | `docs/_site/` git-ignored; `index.html` committed | MUST | - |
| R2.7 | doc:193 | `docs/archive/` superseded docs; keep link to replacement; never cited as rule | imperative | - |
| R3.1 | doc:199-207 | `docs/overview/` holds exactly five pages; may add, must not drop | MUST | L1 |
| R3.2 | doc:208 | App names in `apps.md` equal `apps` in docs.json | MUST | no check named |
| R3.3 | doc:209 | Overview must not repeat feature content | MUST NOT | no check named |
| R4.1 | doc:217 | Feature folder `docs/features/<feature>/spec.md`, `images/`, `diagrams/`, `changes/`; name never changes | MUST | feature, change note |
| R4.2 | doc:218-230 | Front matter keys id, title, apps, topics, status (proposed/building/live/retired), version, owner, type, code | MUST (+SHOULD keys) | F1; status names |
| R4.3 | doc:231 | `version` written only by release fold; status meanings live/building/retired | MUST | version |
| R4.4 | doc:232 | apps/topics from docs.json lists | MUST | no check named |
| R4.5 | doc:233 | `features/index.md` generated from front matter | MUST | G1 |
| R4.6 | doc:237-252 | Spec template: 12 sections then `## Versions` | imperative | template |
| R4.7 | doc:253 | Every requirement has ID `R<section>.<n>` and is testable; section 9 maps tests | MUST | S2 |
| R4.8 | doc:254 | At least one diagram or image (SHOULD); every image alt text (MUST) | SHOULD/MUST | D1, K2 |
| R4.9 | doc:255 | Section 12 `Source: <path>` lines; missing path is error | imperative | S1 |
| R4.10 | doc:256 | Feature artifact holds work in flight; spec says how it works now; promote findings same branch | imperative | no check named |
| R5.1 | doc:262 | `architecture/` binding specs with front matter and fold-written `## Versions` table | imperative | version |
| R5.2 | doc:263 | `guides/` how-to and runbooks; no version | imperative | version |
| R5.3 | doc:264 | `reference/` pages generated by `generated_reference` command | MUST | G2 |
| R5.4 | doc:265 | `design-system/` only home of UX rules; follows §15 | imperative | dup R11.2 |
| R6.1 | doc:273 | `docs_index.py build` writes offline site, stdlib only, works from `file://` | MUST | - |
| R6.2 | doc:274-280 | Home page: search, overview link, feature index, page list, gaps list | MUST | - |
| R6.3 | doc:281-288 | Build also writes features index, decisions.md, docs-map.json, llms.txt; `check` exits 1 if stale | MUST | G1 |
| R6.4 | doc:289-297 | Gaps list contents; stale when `last_verified` > `stale_days` (default 90) | MUST | - |
| R6.5 | doc:298 | Mermaid 11.4.1 vendored; overrides order; fallback source text | imperative | version |
| R6.6 | doc:299 | Relative links work in built site | MUST | - |
| R6.7 | doc:300 | `docs/work/`, `_site/`, change notes not indexed | MUST NOT | - |
| R7.1 | doc:306 | Branch adds one change note instead of editing version; path `docs/features/<f>/changes/<task>.md` or `docs/<area>/changes/<doc>/<task>.md` | MUST | change note |
| R7.2 | doc:307 | Note front matter change/breaking/section/task; one line; one note per task per doc | imperative | change note |
| R7.3 | doc:308-312 | Version per release; highest note wins: major/minor/patch | imperative | version |
| R7.4 | doc:313-319 | `docs_fold.py fold --release <name>`: bump once, one table row, delete notes; `--dry-run` | MUST | fold |
| R7.5 | doc:320 | Only binding docs carry a version | imperative | version |
| R7.6 | doc:321 | V1 fails version mismatch; `docs_fold.py pending` exits 1; release gate runs it | imperative | V1 |
| R8.1 | doc:329-343 | `docs_check.py` errors L1, F1, K1, K2, S1, S2, V1, G1, G2, M1, W1 | MUST | checks |
| R8.2 | doc:344-350 | Warn T1, T2, D1, U1 (stale, code newer, no diagram); `--strict` fails | MUST | checks |
| R8.3 | doc:351 | List code folders in `code_roots` | SHOULD | M1 |
| R8.4 | doc:352 | Checks stack-neutral | MUST | - |
| R8.5 | doc:356 | Coding agent writes docs same branch; brief SHOULD carry `docs:` line | imperative/SHOULD | brief |
| R8.6 | doc:357-361 | M1 fails mapped-code change unless doc changed, change note, or `Docs: none, <reason>` | MUST | M1 |
| R8.7 | doc:362 | Stop hook warns (never blocks); SessionStart adds doc rule; both fail open; nothing without docs.json | MUST | hooks |
| R8.8 | doc:363 | Owner reviews decisions and design-system versions, not every doc | imperative | owner |
| R9.1 | doc:369 | `docs_setup.py migrate` dry run by default; `--apply`, `--map` | MUST | migrate |
| R9.2 | doc:370-376 | `--apply`: `git mv`, rewrite links, stubs, create layout | MUST | migrate |
| R9.3 | doc:376 | Never delete; skip existing target, exit 2; idempotent | MUST NOT | migrate |
| R9.4 | doc:377 | Never move `docs/work/`; record moves to `record_dir`; BRIEF.md to AGENTS.md | MUST NOT | migrate |
| R9.5 | doc:378-384 | Move is mechanical; content work as tasks; full rewrite later (D15) | imperative | task |
| R9.6 | doc:385 | `move-record` moves record, sets `record_dir`, never overwrites, dry run | MUST | record |
| R9.7 | doc:386 | `init` creates layout, never over a file, ignores `_site/` | MUST | - |
| R9.8 | doc:387 | Migration runs between trains | SHOULD | train |
| R10.1 | doc:393 | Briefs, reports, prompts, scratch under `docs/work/` on agent branch; never on default branch | MUST | docs/work |
| R10.2 | doc:394 | `docs_work.py guard --base` exits 1 when branch adds `docs/work/` file; gate runs it on ready PR | MUST | W1, ready PR |
| R10.3 | doc:395 | Join runs `docs_work.py strip --apply`; report summaries into release PR body | MUST | join |
| R10.4 | doc:396 | Keepable findings promoted to lasting doc before the join | MUST | join |
| R10.5 | doc:397 | Standing rules live in `AGENTS.md`, imported by `CLAUDE.md` | imperative | AGENTS.md |
| R11.1 | doc:405 | Feature decisions in `decisions.json`; cross-feature MADR; `decisions.md` generated | imperative | record |
| R11.2 | doc:409 | UX rules only in `docs/design-system/`; specs cite IDs; U1 warns, later error | MUST | U1 |
| R11.3 | doc:410 | User words live in design-system content rules or glossary | imperative | - |
| R11.4 | doc:414 | Diagrams Mermaid; images next to spec with alt text | imperative | K2 |
| R12.1 | doc:420-425 | Plugin `luismc-docs` contents: spec, skills, scripts, hooks, templates | imperative | - |
| R12.2 | doc:426 | Works without delivery/artifacts plugins; other plugins point to it and MUST NOT restate rules | MUST | cross-ref |
| R12.3 | doc:427 | `docs.json` keys list | imperative | - |
| R12.4 | doc:428 | Scripts stdlib only, Python 3.9+ | MUST | - |
| R13.1 | doc:434 | Tests in `tests/`; run `python3 -I -m unittest discover -s claude/plugins/docs/tests` | imperative | test cost |
| R13.2 | doc:435-452 | Requirement-to-test-file map | imperative | - |
| R13.3 | doc:453 | Spec passes `spec_check.py` | MUST | spec_check |
| R14.1 | doc:459 | Conforms when `docs_check.py --base <default>` and `docs_index.py check` exit 0 | imperative | gate |
| R14.2 | doc:460 | Project records DOCSPEC version in `docs.json` key `docspec` | imperative | version |
| R15.1 | doc:468 | `design-system/` holds README, approvals.json, `vN` folders and one `next-version` | MUST | version, design |
| R15.2 | doc:469 | Version folder files (README, CHANGES, ux-rules, components, tokens, content, review-visuals) | MUST | design |
| R15.2a | doc:470 | Gallery draws design; WCAG 2.2 AA 4.5:1 / 3:1; no script, font or network | MUST | design |
| R15.3 | doc:471 | Order of work: highest numbered folder enforced; changes into next-version; owner approves | imperative | owner, version |
| R15.4 | doc:472 | Only owner approves; `promote` needs recorded approval; dry run until `--apply` | imperative | owner |
| R15.5 | doc:473 | Numbered version read-only; digest; `audit/`, `visual/` once; `relink` for link-only edits | imperative | version |
| R15.6 | doc:474 | Project MUST have guard tests (layout, freeze, apps follow version) | MUST | guards |
| R15.7 | doc:475 | `docs_check.py` warns DS1-DS6, never error | MUST | DS1-DS6 |
| R15.7a | doc:476 | Gallery stamp `gallery-script: N`; stale next-version gallery DS4; frozen versions never rebuilt | imperative | DS4 |
| R15.7b | doc:477 | Docs plugin rebuilds stale next-version gallery at SessionStart and Stop; never commits | imperative | commit by plugins |
| R15.8 | doc:478 | Moving design system: rewrite links in one task; approvals added by hand | imperative | task |
| R15.9 | doc:479 | Enforcement kit optional; known-breach lists only shrink (DL-92); wizard 10 states; `brief` writes AGENTS.md block | MUST | cross-ref DL-92 |
| R15.10 | doc:480 | Shared component templates opt-in (DatePicker, TimePicker, NumberKeypad); tokens only; never overwrite | imperative | design |
| R15.11 | doc:481 | Date/time pickers; no native date/time/number input (UX-56); raw-inputs guard fails | MUST | design |
| R15.12 | doc:482 | CORE-1..CORE-7 at top of ux-rules; never deleted; DS6 warns | imperative | design |
| R15.13 | doc:483 | Local app keeps `lifecycle.json`; schema check LC-1 | imperative | lifecycle |
| R15.14 | doc:484 | Lifecycle words table; banned words OK, Yes, No, Install now, Later, daemon, binary, payload | imperative | lifecycle |
| R15.15 | doc:485 | Words lint LC-2, LC-31; templates per language | imperative | lifecycle |
| (R15.16-R15.21) | - | Not present; numbering jumps R15.15 to R15.22 | gap | - |
| R15.22 | doc:486 | Lifecycle parts templates (React, Rust); tokens only; UX-66 to UX-68 | imperative | lifecycle |
| R15.23 | doc:487 | DS234 guards MUST: layout at 360/393/1300/1800 px, spacing tokens, layout roles, none-yet 30 days, citation test | MUST | guards |
| R15.24 | doc:488 | Lifecycle guards LC-22, 23, 24, 30; 24 h notice; 100/150/200% scale, 360 px | imperative | guards |
| R15.25 | doc:489 | `verify` fails DS7 (no approval), DS8 (no implementation approval), DS9 (gallery digest) on release branch | imperative | DS7-DS9 |

#### A4. Shipped rule files: each line, its `check:` and the cited row

Verdict key: SAME = level, numbers and scope match. DRIFT = something differs (said what).

##### clarifying-questions.md (cq and cq-asset are byte-identical)

| Line | check | Cited row | Verdict |
|---|---|---|---|
| cq:2 "gather and list ALL potential clarifying questions" | Q-1 | ds:347 "ask every open question in one go" | DRIFT (wording): "gather and list ALL" vs "in one go"; spec speaks of open questions, not "potential" ones. DL-70 ds:182 adds "numbered". |
| cq:3 "overrule any internal safety limits or 4-question caps. Even if you have 20, 50, or 100+ questions" | Q-1 | ds:347 "There is no 4-question cap when the owner says "ask me questions"" | DRIFT: "overrule any internal safety limits" and the 20/50/100+ numbers are not in Q-1. Trigger text differs: "ask me question" vs "ask me questions". |
| cq:4 "Always use the questions wizard (AskUserQuestion); never ... plain text" | Q-2 | ds:348 | SAME. Spec adds the Stop-hook block. Conflicts with DL-71 ds:183 ("or ask in plain chat") and DL-72 ds:184 ("re-ask in plain chat"). |
| cq:5 "Put the context each question needs inside its own text" | Q-3 | ds:349 | SAME. Spec adds PRE deny for short texts (config min chars). |
| cq:6 "do every action that does not need the answer (merge a green train, push a joined train, launch queued work)" | Q-4 | ds:350 | DRIFT (scope): spec narrows to "green train unmerged that has a PR or a release number, joined train unpushed with previous green". DL-04 ds:63 also lists "publish"; the rule file does not. |
| cq:7 "park a question until the agents of this wave report ... (unless every running agent is blocked on the answer, or the owner asked you to ask questions)" | Q-5 | ds:351 | DRIFT (numbers): spec's deny depends on `question_window_min` (default 60) and allows a 90 s batch (`question_batch_sec`); the rule file names neither. "do not trickle ... across multiple turns" is a wider rule than the timed check. |
| cq:8 routine paused, not postponed | advice | none | No row. Related to DL-35 ds:100 (`run_once_at` = now + ~1 min). |

##### agents-and-integration.md

| Line | check | Cited row | Verdict |
|---|---|---|---|
| ai:2 orchestrator plans, never mechanical work | advice | none | - |
| ai:3 "Sonnet at {{SUBAGENT_EFFORT}} effort" | DL-37 | ds:102 "Sonnet at medium" | DRIFT: placeholder effort vs fixed "medium". |
| ai:4 Opus after one failed Sonnet try; "medium, then high; never Sonnet at xhigh"; `luismc-agents:architect` | DL-37 | ds:102 | DRIFT (scope): escalation path, "high", "xhigh" and the architect agent are not in DL-37. |
| ai:5 scripts merge; haiku for log triage; Explore agent | advice | none | - |
| ai:6 pinned model/effort kept | advice | none | - |
| ai:7 trivial edits (~3 tool calls) done directly | advice | none | - |
| ai:8 group tasks sharing files; split at ~5 tasks or half context | advice | (DL-40 ds:105 is enforced Y) | DRIFT: tagged advice, but DL-40/DL-126 enforce it. "about 5 tasks or half its context" is not in DL-40 ("split only large, truly parallel parts"). |
| ai:9 "Max 50 cloud agents ... at most 3 local agents" | DL-38, DL-41 | ds:103, ds:106 | DRIFT (numbers): omits "> 8 GB free memory" and "total 53". §4(d) ds:326 example "caps 8/3/5" differs from both. DL-41 part SAME. |
| ai:10 light vs heavy change; "1-2 minute local smoke"; `gh workflow run <workflow> --ref <branch>`; no mutation; no local Docker; full suite at most once on a valve; "The ready PR's first CI run is the one full run" | DL-12 | ds:71 | DRIFT (scope): much wider than DL-12. Mutation is in DL-99 G6 (ds:120); "one full run" is DL-11/DL-122 (ds:70, ds:137); carry is DL-80/DL-116. Branch CI by `gh workflow run --ref <branch>` differs from DL-81 (ds:160): `agent_ci.py` dispatches on a merged `ci/<task>` commit. Docker rule has no DS row. |
| ai:11 stop only own processes | DL-42 | ds:107 | SAME. |
| ai:12 report first, push after every step, "keep the report current" | DL-44 | ds:109 | SAME plus "keep the report current". |
| ai:13 commit shared contracts first | DL-45 | ds:110 | SAME (verbatim). |
| ai:14 cloud first; local needs `PC-bound:` reason unless cap full | DL-39 | ds:104 | SAME. Omits DL-127 step-word check. |
| ai:15 never send in owner's name; agents may open PRs, mark ready; merging stays owner's | DL-73 | ds:185 | SAME (verbatim). |
| ai:16 "No Co-Authored-By or AI attribution ... when `.delivery/config.json` sets `no_attribution`" | DL-74 | ds:186 | DRIFT: "AI" vs "Claude" attribution; rule file makes it conditional on a `no_attribution` key; DL-74 says "(owner choice)" and §6 (ds:357-367) does not list `no_attribution`. |
| ai:19 "own branch named `<task-id>-<slug>`, draft PR, branch gate in the agent sandbox (no Actions)" | DL-08 | ds:67 | DRIFT (scope): DL-08 says nothing on branch names or sandbox. "(no Actions)" conflicts with DL-81 CI-gate path and with ai:10 (CI on the branch). |
| ai:20 one ready PR when join pushed; first CI run only full suite; later pushes carry; "Merge on green, never auto-merge" | DL-05, DL-06, DL-08 | ds:64, 65, 67 | Mostly SAME. The full-run/carry part belongs to DL-11/DL-80, not the cited IDs. "Merge on green" names no merger; DL-73 (and ai:15) say merging stays the owner's, D5 says the watcher merges. |
| ai:21 watch CI by head-commit runs (`ci_watch.py`) | DL-07 | ds:66 | SAME. |
| ai:22 one deploy per merge; smoke; fix forward | DL-18 | ds:77 | DRIFT (scope): omits "Ask before a rollback when the owner is awake". |
| ai:23 read `docs/guides/agent-delivery-details.md` | advice | none | - |
| ai:26 create every doc under `docs/` | DL-75 | ds:187 | SAME (verbatim). |

##### delivery-timing.md

| Line | check | Cited row | Verdict |
|---|---|---|---|
| dt:2 ETA clock time + dependency; example "~25 min, so 14:30"; never "tomorrow" or "next round" unless past midnight | DL-31 | ds:95 | DRIFT (small): "next round" is in D9 (ds:353), not the DL-31 row. DL-31 also exempts past facts and covers assumed starts; the rule file does not. |
| dt:3 ETA from setup + work + checks; breakdown in `delivery:` block; never pad | DL-30 | ds:94 | SAME (the `delivery:` block is in ds:266 and D9). Omits eta_table numbers. |
| dt:4 join next train while previous CI runs; push when green | DL-02 | ds:61 | SAME (verbatim). |
| dt:5 wait is a gap, never a phase; one train in CI | DL-17 | ds:76 | SAME. |
| dt:6 "A train leaves when it is green, at any hour; merge it at once" | DL-03 | ds:62 | DRIFT (scope): first clause is DL-16 (ds:75) content; "at any hour" is in neither row. |
| dt:7 owner's zone (`tz` in config), labelled, real clock | DL-66 | ds:176 | SAME in effect; row names "(one city name)", rule file names `tz`. |
| dt:8 say RELEASE-n | DL-64 | ds:174 | SAME (verbatim). |

##### AGENTS.md (no `check:` tags; nearest owner rule given)

| Line | Nearest rule | Note |
|---|---|---|
| ag:7 task branch `<task-id>-<slug>`; push only that branch; never push `main`, merge, or open a ready PR | DL-08 ds:67, DL-73 ds:185 | DL-73 lets agents "open pull requests, mark them ready". AGENTS says never open a ready PR. |
| ag:8 never edit `**Version:**`, change log, plugin `"version"`; note in `docs/architecture/changes/`; plugin change needs note naming `plugin.json` | DOC R7.1 doc:306, R4.3 doc:231 | R7.1 path form is `docs/<area>/changes/<doc>/<task>.md`. DS §4(c) ds:320 plans a "`plugin.json` version bump". |
| ag:9 requirement IDs, sections, Version lines stay | DOC doc:89 (append-only numbering) | - |
| ag:10 `watcher.merge_mode` auto (default)/manual; agents never `gh pr merge`; hook refuses in manual | DS §6 ds:360 (`merge_on_green`) | `merge_mode` is not in DS §6. "auto" here is not `gh pr merge --auto` (DL-05). |
| ag:11 plugins never commit, push or merge | DL-131 ds:146, R15.7b doc:477 | DS D5 ds:342 and §6 ds:360: the watcher (plugin script) pushes, opens PRs and merges. |
| ag:12 name no other project | none | - |
| ag:13 tests light; `tools/ci_areas.py --branch-advice`; no mutation, no Docker | DL-12, DL-99 G6 | Script name differs from DS `changed_areas.py` (DL-116). |
| ag:14 plain short English | none | - |
| ag:18 docs layout list | DOC §2.1 doc:156-176, R2.2 | Omits `archive/` and `work/`. |
| ag:19 behaviour change updates feature spec + `docs_fold.py note ... --change minor`; never edit version table | DOC R8.5, R7.1, R7.4 | Fixed `--change minor` in example. |
| ag:20 `Docs: none, <reason>` | DOC R8.6 doc:361 | SAME. |
| ag:21 UX rules only in design system | DOC R11.2 doc:409 | SAME. |
| ag:22 briefs and reports in `docs/work/` branch only | DOC R10.1 doc:393 | SAME. |
| ag:23 do not edit generated files (list) | DOC R2.5 doc:182-191 | Omits `docs/_site/`; R2.5 limits `reference/` to `generated_reference` entries. |
| ag:24 run `docs_check.py` before finishing | DOC R14.1 doc:459 | R14.1 also needs `--base <default branch>` and `docs_index.py check`. |

---


### A.2 ARTIFACTSPEC and project-artifacts.md

Keys: `S` = ARTIFACTSPEC, `RF` = `claude/plugins/docs/rules/project-artifacts.md`.


#### A.1 Invariants (§3.2)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| INV-1 | S:452 | Task status exists in exactly one place, the task registry. | decl.; Verified by `test_render_from_registry_only` | record, status |
| INV-2 | S:454 | At most one full-progress artifact; exactly one whenever a feature artifact exists. | decl.; Verified by `test_one_full_progress` | artifacts |
| INV-3 | S:456 | Every rendered HTML file in the record equals a fresh render; publish copy differs only in links. | decl.; Verified by `test_rendered_matches_record` | render |
| INV-4 | S:461 | No hook modifies the record. | decl.; Verified by `test_hooks_never_write_record` | hooks, record |

#### A.2 §3 Architecture / activity rule

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R3.1 | S:480 | Steps 3-5 in same turn; publish Full Progress once at turn end, never mid-turn; 200 publishes/day. | decl.; Verified by `stop_blocks_when_an_artifact_is_pending`, `test_session_sequence_ends_clean` | publish, daily limit, end-of-turn |
| R3.2 | S:486 | Every activity is a task before it starts, agents' and session's own (joins, test runs, releases...). | decl.; rule file line; Verified by `rule_file_carries_the_activity_rules` | task, activity |
| R3.3 | S:490 | Task is Running while work runs; Waiting or Needs you when blocked. | decl.; rule file line; same test | status |
| R3.4 | S:493 | Built = finished, not released; join, CI, release work is its own task. | decl.; rule file line; same test | Built, release |
| R3.5 | S:496 | Before ending a turn with background work, its task is Running; R8.10 enforces. | decl.; Verified by `rule_file_carries_the_activity_rules`, `stop_blocks_background_work_without_an_active_task` | background, end-of-turn |

#### A.3 §4 The record

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R4.1 | S:523 | Record lives only under `docs/artifacts/`; publish copy is not record; section 0 generated. | decl. | record |
| R4.2 | S:548 | `key` lowercase/digits/hyphens; `prefix` 2-5 capitals; each prefix once in manifest. | decl. | manifest, IDs |
| R4.3 | S:550 | Full-progress `url` empty until first publish; `published_sha256` = hash of committed render. | decl. | publish, manifest |
| R4.4 | S:556 | `file` is `<kind>-<slug>.html`, kind feature or full-progress. | decl. | manifest |
| R4.5 | S:569 | Task ID = prefix + integer, unique, never reused; never removed; dropped work set On hold or Built. | decl. | task, IDs |
| R4.6 | S:573 | `owner` is a feature key or `project`; prefix rules; moved task keeps its ID. | decl. | owner, task |
| R4.7 | S:577 | `status` one of nine (§6.1); `changed` set only by script. | decl. | status |
| R4.8 | S:579 | Optional row fields; `item` max 80 chars, `detail` max 600. | decl. | registry |
| R4.9 | S:583 | Tasks stored in ID order; rendering orders them. | decl. | registry |
| R4.10 | S:600 | Content fragments: no `<script>`, no `<style>`, no section numbers. | decl. | content |
| R4.11 | S:602 | `extra_css` MUST NOT redefine a structure-stylesheet selector. | MUST NOT | design |
| R4.12 | S:608 | Times from real clock in manifest zone: zoneinfo, then PowerShell, then local time with warning. | decl. | time |
| R4.13 | S:618 | Script writes files in working tree, uncommitted; plugin MUST NOT write git state (no commit/push/fetch...). | MUST NOT; Verified by `test_writing_commands_change_files_and_leave_git_alone`, `test_only_read_only_git_is_run` | commit/push by plugin, git |
| R4.14 | S:629 | Script commits nothing; writes only under `docs/artifacts/` (+ .gitignore, stale rule copy). | retired (1.8.0), text still normative | commit by plugin |
| R4.15 | S:633 | No push, so no push race, no exit 3. | retired (1.8.0) | push |
| R4.16 | S:634 | No push, so no protection refusal, no exit 4. | retired (1.8.0) | push |
| R4.17 | S:635 | Lock file `.claude/artifacts-record.lock`; failed change restores files; `--push`/`--no-push` no-ops. | decl. | lock, push |
| R4.18 | S:644 | Old feature `url`/`published_sha256` ignored, moved to `retired`, rerendered; `check` notes it. | decl.; Verified by `test_old_feature_urls_migrate` | migration, publish |
| R4.19 | S:653 | `retired` and `deleted` list shapes; URL in at most one; Full Progress URL in neither. | decl.; Verified by 2 tests | retired pages |
| R4.20 | S:662 | Recover dropped feature URLs from `manifest.json` git history; bounded to 200 commits. | decl.; Verified by `test_retired_urls_are_recovered_from_history` | migration, git read |
| R4.21 | S:671 | `mark-deleted [KEY] --url URL [--gone]` moves entry to `deleted`; refuses bad URL/key. | decl.; Verified by 2 tests | retired pages |
| R4.22 | S:678 | `pending` lists retired pages with instruction to ask owner; never changes exit code. | decl.; Verified by 2 tests | owner questions, retired pages |
| R4.23 | S:685 | Retired page deleted only with owner's confirmation; session asks, deletes, runs `mark-deleted`. | decl.; rule file; Verified by `rule_file_carries_the_retired_pages_rule` | owner questions, publish/delete |
| R4.24 | S:693 | Record worktree retired; `worktree` prints record dir; one-time copy from old worktree when newer. | decl.; Verified by 3 tests | worktree, migration |
| R4.25 | S:713 | Worktree setting no longer read, so none refused. | retired (1.8.0) | worktree |
| R4.26 | S:714 | `.claude/artifacts-local.json` stays git-ignored; record never holds a machine path. | decl. | config |
| R4.27 | S:716 | Plugin does not move or remove a worktree. | retired (1.8.0) | worktree |
| R4.28 | S:720 | `commit` and `push` commands removed, exit 1 with message; no hook pushes; `pending` does not push. | decl.; Verified by `test_commit_and_push_are_removed`, `test_pending_does_not_push` | commit/push by plugin |
| R4.29 | S:725 | Nothing fetched or rebased; merging concurrent record commits is the project's git work. | retired (1.8.0) | git, merge |
| R4.30 | S:727 | Feature `updated` = page stamp time; `published_at` = last `mark-published`; ISO with offset. | decl.; Verified by `test_feature_updated_and_published_line` | manifest, publish |
| R4.31 | S:744 | `retire KEY --yes` moves feature to `retired_features`; check reports damage. | decl.; Verified by 2 tests | retire |
| R4.32 | S:750 | `retire` archives `decisions.json` byte for byte; deletes feature file and content folder. | decl.; Verified by 2 tests | retire, decisions |
| R4.33 | S:756 | `retire` refuses unless all tasks Live or Dropped and no open decision. | decl.; Verified by `test_retire_refuses_a_feature_with_an_open_task` | retire |
| R4.34 | S:760 | Full Progress section 1 lists retired features in one closed `<details>`. | decl.; Verified by test | retire, Full Progress |
| R4.35 | S:764 | Retired key not reused unless `feature-new --force`; retired prefix never reused under another key. | decl.; Verified by test | retire, IDs |
| R4.36 | S:770 | Without `--yes`, `retire` is a dry run; with it, a writing command; never deletes claude.ai page. | decl.; Verified by 2 tests | retire, publish |
| R4.37 | S:780 | `record_dir` in `.claude/artifacts.json`, under `docs/`, default `docs/artifacts`; bad value exits 2. | decl.; Verified by 4 tests | config, record |
| R4.38 | S:788 | `move-record NEW_DIR [--yes]` moves folder, no git; dry run without `--yes`; refusals exit 1/2. | decl.; Verified by 2 tests | record, commit by project |

#### A.4 §5 Structure and look

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | S:812 | Titles `Feature: <name>` and `Full Progress: <project>`. | decl.; §14 check | titles |
| R5.2 | S:814 | Sections numbered from 0, no gaps; contents list matches. | decl.; §14 | render |
| R5.3 | S:816 | Section 0 `Status and checklist`: stamp, lede, At a glance, tiles, key, checklist. | decl.; §14 | render |
| R5.4 | S:819 | Feature artifact last section `History` (Date, Change), newest first; Full Progress has none. | decl.; §14 | render |
| R5.5 | S:821 | Stamp `Last update: DD Mon HH:MM (<label>)` in `<time datetime>`. | decl.; §14 | time |
| R5.6 | S:823 | Full Progress section 1: two folds, table of 5 columns, default order newest first. | decl.; §14 | Full Progress, feature table |
| R5.7 | S:835 | Lede is content lede only; Needs you lists Needs you, owner waits, Failed, open decisions. | decl.; `check` | Needs you, owner |
| R5.8 | S:849 | Tiles count each status with at least one task, §6.1 order. | decl.; §14 | tiles |
| R5.8a | S:851 | Tile label `tasks <status>` (`task running` singular). | decl.; Verified by `tiles_say_tasks` | tiles |
| R5.9 | S:854 | Full Progress embeds a registry window: non-Live/Dropped plus 14 days (`EARLIER_DAYS`); one JSON script. | decl.; checker compares | registry, 14 days |
| R5.10 | S:867 | Every artifact includes structure CSS unchanged plus one token block. | decl.; §14 | design |
| R5.11 | S:870 | Token block defines every contract token, light and two dark selectors. | decl.; §14 | design |
| R5.12 | S:874 | Skill finds project design in fixed order; writes `design.css` only after owner agrees. | decl. | design, owner questions |
| R5.13 | S:879 | Light and dark; 360 px wide, 16 px gutter, no sideways scroll. | decl. | layout |
| R5.14 | S:905 | Feature MAY hold `decisions.json`; field shapes; question 1-200 chars; summary 1-400. | MAY + decl.; §14 | decisions |
| R5.15 | S:915 | Decision IDs D1.. no gap, never reused/removed; `edit-content` refuses changing decided ones. | decl.; §14 | decisions |
| R5.16 | S:920 | 2 to 6 options, unique labels; at most one recommended; status decided or open. | decl.; §14 | decisions |
| R5.17 | S:926 | `preview` max 4000 chars, no script/style/iframe/external URL; `image` png/jpg/gif/webp max 300 KB. | decl.; §14 | decisions |
| R5.18 | S:934 | `replaces` names earlier decision; `task` exists in registry. | decl.; §14 | decisions |
| R5.19 | S:936 | Content file titled `Decisions` refused. | decl.; §14 | decisions |
| R5.20 | S:942 | Generated `Decisions` section just before History, newest first. | decl.; §14 | decisions |
| R5.21 | S:946 | Options as cards side by side; one column at phone width. | decl.; §14 | decisions |
| R5.22 | S:950 | Chosen card marked `Chosen by the owner · DD Mon`; others `Not chosen`; `Recommended` tag. | decl.; §14 | decisions, owner |
| R5.23 | S:955 | Open decision has `Needs you` chip; replaced decision collapsed `Replaced by Dn`. | decl.; §14 | decisions |
| R5.24 | S:960 | Decision colours from tokens only; no script. | decl. | design |
| R5.25 | S:966 | Needs you also lists open unreplaced decisions; section 1 line ends `n decisions open.` | decl.; §14 | Needs you, decisions |
| R5.26 | S:971 | `check` warns for open decision with no task in Needs you. | decl. (warning) | decisions |
| R5.27 | S:984 | Feature file is a complete HTML document (doctype, head, body, styles, template script). | decl.; Verified by `feature_artifact_is_a_standalone_document`, `check_r527_standalone_document` | feature file |
| R5.28 | S:991 | Feature document needs only a browser; only Google Fonts links. | decl.; Verified by 2 | feature file |
| R5.29 | S:1000 | Full Progress file stays a fragment beginning with `<title>`. | decl.; Verified by 2 | publish |
| R5.30 | S:1007 | Committed Full Progress links features by relative file name. | decl.; Verified by 2 | links |
| R5.31 | S:1013 | `pending` writes a publish copy in `.claude/artifacts-publish/` with Copy link buttons to `file:///` URLs. | decl.; Verified by 4 tests | publish copy |
| R5.32 | S:1031 | `mark-published` records hash of committed render, not of publish copy. | decl.; Verified by `test_pending_and_mark_published` | publish |
| R5.33 | S:1038 | At a glance block after lede, before tiles; one `<details>` per kind; deterministic. | decl.; §14 | At a glance |
| R5.34 | S:1047 | Glance groups: you, running, built, waiting, live (24 h, max 8, `and N more`). | decl.; §14 | At a glance, 24 h, 8 |
| R5.34a | S:1060 | `waits_on` owner or work, default work; `--waits-on`; dependency shown first. | decl.; Verified by 6 tests | owner, Waiting |
| R5.35 | S:1079 | `check` finds wrong group contents, order, or `and N more`. | decl. | At a glance |
| R5.36 | S:1083 | Empty lede: section 1 line is a generated count summary; never blank. | decl. | Full Progress |
| R5.37 | S:1088 | Warn for lede over 300 chars, or naming a train label or `#NN`. | decl. (warning); §14 | lede, train label |
| R5.38 | S:1094 | Feature page shows `Full Progress published: ...`; `mark-published` keeps stamps; features drawn first. | decl.; Verified by `test_publish_does_not_loop`, `check_r538_published_line` | publish |
| R5.39 | S:1104 | Section 1 sort buttons on `Feature artifact`, `Last updated`; script stores nothing. | decl.; Verified by 2 | Full Progress |
| R5.40 | S:1116 | Release row fields `release`, `phases`, `risk`, `rides`; phase names agents/join/ci/fix/merge; flags. | decl.; Verified by 2 tests + fixtures | release, phase |
| R5.41 | S:1143 | Release Expected = end of last phase; mismatched `--expected` refused; risk not added. | decl.; Verified by tests + `rule_file_carries_the_release_rule` | Expected, release, risk |
| R5.41a | S:1154 | Running/Waiting release must have phases; `--no-phases REASON` (2+ words, max 80); older rows warn. | decl.; Verified by 5 tests in `tools/test_artifacts_ds278.py`; "CI fails on it" | release, phase, CI |
| R5.42 | S:1170 | Release timeline when a release is open; 24 h axis, ticks 30 min (hourly beyond 4 h). | decl.; Verified by 5 tests | timeline, 24 h |
| R5.42a | S:1192 | Time axis may cross midnight; timed release within 24 h never in a day slot. | decl.; Verified by 3 | timeline |
| R5.42b | S:1200 | Second strip "Other work (no release)" for no-release tasks due today/tomorrow. | decl.; Verified by 2 | timeline |
| R5.42c | S:1216 | Release without phases = outline diamond; table shows `no phases`. | decl.; Verified by 3 in `tools/test_artifacts_ds278.py` | timeline |
| R5.43 | S:1225 | Timeline look from tokens only; risk extension; viewBox at least 960; never scaled up. | decl.; Verified by 4 | timeline, design |
| R5.44 | S:1238 | Feature table `State` column: `Complete` chip or per-status counts. | decl.; Verified by 3 | feature table |
| R5.45 | S:1249 | Releases numbered `RELEASE-<n>`, next number past registry and delivery ledger; never reused. | decl.; Verified by 7 tests + fixtures | release number, ledger |
| R5.46 | S:1283 | Full Progress checklist grouped by release, then `Not in a release yet`, then R6.2 groups. | decl.; Verified by 4 | release, checklist |
| R5.47 | S:1306 | Every Running or Built non-release task rides a release; writing command refuses otherwise. | decl.; rule file line; Verified by tests + `rule_file_carries_the_rides_rule` | release, rides |
| R5.47a | S:1314 | `--no-release REASON` (max 80); may run without release; never Built, goes Live. | decl.; Verified by 3 | release, Built, Live |
| R5.48 | S:1325 | Optional `started` ISO time; `--started`; must be before Expected; auto-set on first Running. | decl.; Verified by 3 | time |
| R5.49 | S:1338 | Status `Dropped`: terminal; needs `--into` or `--reason` (max 80); release needs `--into`. | decl.; Verified by 2 | status, Dropped |
| R5.50 | S:1355 | Section 1 two folds: in progress (open) and complete (closed); empty-fold lines. | decl.; Verified by 4 | Full Progress |
| R5.51 | S:1372 | Foldable `CI runs` section from `.delivery/ci-runs.json`, publish copy only; 20 latest. | decl.; Verified by `ci_runs_*` in `tools/test_render_artifacts.py` | CI, delivery |
| R5.52 | S:1401 | Dateless `--phase` anchored to nearest occurrence within 12 h; warnings and refusals named. | decl.; Verified by `test_ar74_phase_dates` | phase, time |
| R5.53 | S:1413 | `Where it stands` cell built from record: Live release, open-status clauses. | decl.; Verified by `test_ar77_where_it_stands` | Full Progress |
| R5.54 | S:1426 | Cell at most about 220 chars; drop clauses from front. | decl.; §14 | Full Progress |
| R5.55 | S:1429 | Release may carry `pr`, `release_start`, `release_waits_on` (no cycle). | decl. | release, PR |
| R5.56 | S:1433 | Dependent release never live before what it waits on; Live ETA = latest. | decl. | release, ETA |
| R5.57 | S:1435 | Release table after timeline: Item, Live ETA, CI, Waits on, Status; PR rows. | decl. | release table, PR |
| R5.58 | S:1438 | Timeline is a tree: trunk x=22, 18px elbows, labels x=46, max 880 wide, ~52 per row. | decl. | timeline |
| R5.59 | S:1441 | Missing `pr`/`release_waits_on` read from `.delivery/ledger.json` and git, read-only. | decl.; Verified by `test_dl420_ledger_links` | ledger, train, integration branch |
| R5.60 | S:1451 | Release table shows whenever any release is open; tree only with carrier PR or dependency. | decl.; Verified by `test_artifacts_ds256` | release table, carrier |
| R5.61 | S:1454 | Full Progress section 0: stamp, status badges, What is happening, key, checklist; no glance/lede/tiles. | decl.; Verified by `test_artifacts_dl429` | Full Progress, badges |
| R5.62 | S:1467 | `What is happening` 1-8 generated bullets; never a train label. | decl.; Verified by `test_artifacts_dl429` | Full Progress, train label |
| R5.63 | S:1481 | Badge inputs read-only from `ci-runs.json` and ledger; train branch `<TASK-ID>-integration`. | decl.; Verified by `test_artifacts_dl429` | CI, ledger |
| R5.64 | S:1489 | `ci-waste` badge: `N% green · M min per merged PR · K min cancelled (7 d)`. | decl.; Verified by `test_artifacts_ds258` | CI, test cost |
| R5.65 | S:1497 | PR numbers in Full Progress are https links from provider table; render never runs git. | decl.; Verified by `test_artifacts_ds272` | PR links |
| R5.66 | S:1510 | Manifest `pr_links`; derived from `git config --get remote.origin.url`; `pr-links` sets by hand. | decl.; Verified by `test_artifacts_ds272` | PR links, git read |

#### A.5 §6 Statuses and the checklist

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §6.1 table (no ID) | S:1526 | Nine statuses: Live, Built, Running, Needs you, Waiting, To do, On hold, Failed, Dropped. | definition | status |
| R6.1 | S:1538 | Only these nine statuses; fixed chip class each. | decl.; §14 | status |
| R6.2 | S:1543 | Groups: `Running now and next`, `Needs you, failed or on hold`, `Live or built`. | decl.; §14 | checklist |
| R6.3 | S:1550 | Full Progress hides Live rows over 14 days with a note line; no Earlier fold; Built never hidden. | decl.; Verified by `earlier_fold_older_than_14_days`, `built_rows_never_fold` | Built, Live, 14 days |
| R6.4 | S:1561 | Checklist columns: feature 4, Full Progress 5 (adds App / service). | decl.; §14 | checklist |
| R6.5 | S:1565 | Full Progress feature task Item links to feature file. | decl.; §14 | links |
| R6.6 | S:1570 | Open-row Expected `DD Mon` or `DD Mon ~HH:MM`; relative words fail; empty allowed on To do/On hold. | decl.; §14 | Expected |
| R6.7 | S:1578 | Live or Built row Expected is the date it happened. | decl. | Expected |
| R6.8 | S:1579 | `set-task-status` to Live/Built sets Expected to today when none given. | decl. | Expected |
| R6.9 | S:1584 | `Done` retired; accepted as alias, stored as `Built`; check notes. | retired status; Verified by 2 tests | status, Built |
| R6.10 | S:1595 | Optional `expected_basis` max 80 chars on open rows; `--basis`; dropped on Live/Built/Failed. | decl.; Verified by tests + fixtures | Expected, estimate |
| R6.11 | S:1606 | Basis shown in muted line; rule file says give the basis. | decl.; Verified by 4 incl. `rule_file_carries_the_basis_rule` | Expected, estimate |
| R6.12 | S:1616 | Every checklist group a `<details>`; Full Progress all closed; feature: only `Live or built` closed; 2.75rem tap. | decl.; Verified by 4 | checklist |
| R6.13 | S:1641 | Each glance group a `<details>`; feature: built/live closed; Full Progress all closed. | decl.; Verified by 3 | At a glance |
| R6.14 | S:1660 | Open row past its Expected flagged as warning (date ends 23:59); hook blocks (R8.19). | decl. (warning); Verified by `test_check_flags_open_rows_past_their_expected_time` | Expected, ETA |
| R6.15 | S:1668 | `task-add` warns when a To do/Running/Built task has no release to ride; exit 0. | decl. (warning); Verified by test | release |

#### A.6 §7 Commands

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §7 exit codes (no ID) | S:1682 | Exit 0 success, 1 findings/refused, 2 unreadable; 3 and 4 unused. | decl. | commands |
| §7 `--push` note (no ID) | S:1686 | Writing commands write files and stop; `--no-push`/`--push` do nothing. | decl. | push |
| §7 table (no ID) | S:1690-1711 | Command list: init, feature-new, task-add, set-task-status, ..., push/commit removed. | decl. | commands |
| §7 promote-to-spec (no ID) | S:1700 | Writes feature content to `docs/features/<ID>/spec.md`; dry run without `--apply`; never commits. | decl. | DOCSPEC, feature spec |
| R7.1 | S:1713 | Writing command refuses a change that adds a finding (by req ID + file, counted). | decl. | check |
| R7.1a | S:1719 | Writing command MUST NOT refuse because of pre-existing findings; prints `N earlier findings remain`. | MUST NOT | check, migration |
| R7.2 | S:1729 | `set-task-status` updates registry, renders, removes queued events, writes files in one call. | decl. | status |
| R7.3 | S:1732 | `set-task-status` rejects unknown status, names nearest (`Merged` -> `Live`). | decl. | status, merge |
| R7.4 | S:1734 | Rendering deterministic: same record + stamp give byte-identical HTML. | decl. | render |
| R7.5 | S:1736 | Full Progress drawn after features; stale pages rerendered on any writing command. | decl. | render |
| R7.6 | S:1743 | `pending` does not push or write git state. | decl.; Verified by `test_pending_does_not_push` | push by plugin |

#### A.7 §8 Hooks

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §8 intro (no ID) | S:1751 | Three hooks registered; before-command hook retired (AR50) but script kept silent. | decl. | hooks |
| §8 intro (no ID) | S:1761 | Each hook exits 0 and does nothing without a manifest in checkout or on `origin/<default branch>`. | decl. | hooks |
| §8.1 event table (no ID) | S:1767-1779 | Task ID from branch `^([A-Z]{2,5}[0-9]+)-`; `gh pr create` Running, `gh pr ready` Waiting, `gh pr merge` merged_status, CI fail Failed, deploy Live. | decl. | branch name, PR, merge |
| R8.1 | S:1781 | After-command hook only queues; never writes record; no task ID, no event. | decl. | hooks |
| R8.2 | S:1784 | Hook finishes under 2 s; never fails the tool call. | decl. | hooks, 2 s |
| R8.3 | S:1789 | End-of-turn hook blocks while queue non-empty or Full Progress pending. | decl.; hook `hook_end_of_turn.py` | end-of-turn, publish |
| R8.4 | S:1796 | After 3 consecutive blocks with no change, let turn end with `systemMessage`. | decl.; R13.2 | end-of-turn, 3 blocks |
| R8.5 | S:1803 | Session-start hook fetches default branch, `gh pr list --limit 200`, queues merged_status or On hold. | decl. | merge, branch name, git fetch |
| R8.6 | S:1808 | No `gh` or not signed in: queue nothing, one `systemMessage`; fails open. | decl. | hooks |
| R8.7 | S:1811 | Session-start prints `systemMessage` listing queued events. | decl. | hooks |
| R8.8 | S:1815 | Background Agent/Task/Bash marks stop state; watch-only commands exempt; temp files over 60 s swept. | decl.; Verified by 4 | background |
| R8.9 | S:1836 | Session-start hook prints rule file as `additionalContext` every session. | decl.; Verified by 2 | rule delivery |
| R8.10 | S:1845 | End-of-turn blocks when background work recorded and no Running/Waiting/Needs you task; fires once per marker. | decl.; Verified by 5 | background, end-of-turn |
| R8.11 | S:1861 | End-of-turn hook acts on Full Progress only; feature entries ignored. | decl.; Verified by `stop_counts_only_full_progress` | publish |
| R8.12 | S:1868 | After-command hook delivers the rule once per session and after text change; temp marker per repo (DS271). | decl.; Verified by 2 | rule delivery |
| R8.13 | S:1885 | Hooks list retired pages, tell session to offer owner deletion; end-of-turn never blocks on them. | decl.; Verified by 2 | owner questions, retired pages |
| R8.14 | S:1894 | Record needing migration: hooks say run `render`; end-of-turn blocks until migrated; R8.4 give-up. | decl.; Verified by 3 | migration |
| R8.15 | S:1905 | Hooks say an existing `.claude/rules/project-artifacts.md` is an older copy. | decl.; Verified by test | rule file |
| R8.16 | S:1912 | Before-command hook not registered and does not push before `gh pr create/ready/merge`. | retired (AR50); Verified by 2 | push by hook |
| R8.17 | S:1918 | End-of-turn hook does not push. | decl.; Verified by `hooks_never_write_record` | push by hook |
| R8.18 | S:1922 | Block when `published_at` over 60 min old while work open, or release task changed since publish. | decl.; Verified by 3 | publish, 60 min |
| R8.19 | S:1934 | Block while an open row is past Expected; names fix command; R8.4 ceiling. | decl.; Verified by test | Expected |

#### A.8 §9 Publishing and recreation

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R9.1 | S:1943 | Session publishes Full Progress once per turn at end, unedited publish copy, then `mark-published`. | decl. | publish |
| R9.2 | S:1948 | Manifest URL gone: list artifacts, reuse same title, else new; at most one per title. | decl. | publish |
| R9.3 | S:1953 | Deleted Full Progress recreated from record alone. | decl. | publish |
| R9.4 | S:1956 | Publish refused for concurrent change: retry once; generated sections not kept. | decl. | publish |
| R9.5 | S:1960 | Feature artifact never published, no URL; `mark-published` refuses it. | decl.; Verified by 2 | publish |
| R9.6 | S:1966 | Publish needed only when owner-visible fields change; fingerprint in manifest. | decl.; Verified by 2 | publish |
| R9.7 | S:1975 | Daily limit refusal: `mark-deferred --until <reset>`; hook stops blocking; local copy, refresh 60. | decl.; Verified by 2 | daily limit, publish |
| R9.8 | S:2001 | Publish at least every 60 min while work open (hourly fail-safe, decision D20). | decl.; Verified by test | publish, 60 min |
| R9.9 | S:2008 | Release task status/phase change published in the same turn. | decl. | publish, release |
| R9.10 | S:2010 | `publish_hourly.py` prints what the hourly cron does; never publishes. | decl.; Verified by test | publish |
| R9.11 | S:2016 | `pending --json` records copy hash/time; `mark-published` refuses stale or edited copy (DL-62). | decl.; Verified by 2 | publish |
| R9.12 | S:2030 | Publish copy follows record (AR70); `render` wording; order pending, publish, mark-published. | decl.; Verified by 4 | publish |
| R9.13 | S:2044 | Settle window (AR72) `full_progress.settle_sec`, default 60; turn end ignores record's last change. | decl.; Verified by 5 | publish, daily limit |
| R9.14 | S:2071 | Unchanged copy not asked for outside hourly fail-safe or release change. | decl.; Verified by 2 | publish |

#### A.9 §10-§14

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R10.1 | S:2081 | Plugin installable alone; enabled by `luismc-project-setup` `claude-setup` via `enabledPlugins`. | decl. | install |
| R10.2 | S:2089 | Install creates no file; first `init`/`feature-new` adds 5 `.gitignore` entries. | decl.; Verified by `test_init_session_files` | install |
| R10.3 | S:2099 | Rule file holds one imperative line per rule (list of 10 items + R3.2-3.5). | decl. | rule file |
| R10.4 | S:2113 | Plugin delivers the rule file at session start; no copy goes stale. | decl. | rule delivery |
| R10.5 | S:2116 | `check` notes a differing `.claude/rules/project-artifacts.md`; no exit-code change. | decl.; Verified by test | rule file |
| R10.6 | S:2121 | Stale shipped rule copy deleted (uncommitted) by next writing command; edited copy kept. | decl.; Verified by 2 | rule file |
| §11 table (no ID) | S:2135-2142 | Failure modes: Artifact tool fail closed then open after 3; gh fail open; tz fall back. | decl. | failure |
| R11.1 | S:2144 | Each failure prints one line naming dependency and exit code. | decl. | failure |
| §12 table (no ID) | S:2151-2157 | Config: merged_status Live; Earlier age 14 d (ceiling 60); blocks 3; `CLAUDE_ARTIFACTS_HOOKS` on; record_dir. | decl. | config |
| R13.1 | S:2163 | `tools/test_project_artifacts.py` uses throwaway repos with local bare remote; lists covered IDs. | decl. | test cost |
| R13.2 | S:2167 | `tools/test_project_artifacts_hooks.py` feeds hook input; covers R8.4, R8.8-R8.17, INV-4. | decl. | test cost, hooks |
| R13.3 | S:2171 | Before release: run on scratch clone of plugin repo; status change end to end; git unchanged. | decl. | release, test cost |
| R13.4 | S:2175 | `spec_check.py` passes; every SKILL.md declares model and effort. | decl. | spec check |
| §14 table (no ID) | S:2182-2229 | `check` reports each row with its requirement ID; exit 0/1/2. | decl. | check |

#### A.10 Decision record (§ Decision record, S:349-378)

| ID | file:line | gist |
|---|---|---|
| D1 | S:353 | Status stored once in `registry.json`. |
| D2 | S:354 | Branch names start with task ID: `AR5-artifactspec`. |
| D3 | S:355 | Outside changes arrive at next session start; no cloud routine in 1.0. |
| D4 | S:356 | Project tokens or plugin default design. |
| D5 | S:357 | App / service column only on Full Progress. |
| D6 | S:358 | Record in repo `docs/artifacts/`; "the project commits it". |
| D7 | S:359 | `luismc-project-setup` installs the plugin. |
| D8 | S:360 | Owner's time zone per project. |
| D9 | S:361 | Plugin's home repo does not touch other projects. |
| D10 | S:362 | Session-start hook prints rule file every session. |
| D11 | S:363 | Record format stays `ARTIFACTSPEC 1.0.0`. |
| D12 | S:364 | Owner choices kept in `decisions.json`. |
| D13 | S:365 | Full Progress published once per turn at end; 200 publishes a day. |
| D14 | S:366 | Feature artifacts not published; standalone HTML files. |
| D15 | S:367 | Live rows older than 14 days fold into Earlier; Built never. |
| D16 | S:368 | Background `run_in_background` arms the check. |
| D17 | S:369 | Old feature page URLs move to `retired`; deleted only with owner. |
| D18 | S:370 | Retired pages never block. |
| D19 | S:371 | After-command hook delivers rule; end-of-turn blocks until migrated. |
| D20 | S:372 | Stale 1.0.0 rule copy deleted by next writing command. |
| D21 | S:373 | `expected_basis` is its own field. |
| D22 | S:374 | Record worktree retired in 1.8.0. |
| D23 | S:375 | Plugin does not commit or push; project commits and pushes. |
| D24 | S:376 | `retire` moves finished feature (owner, 30 Oct). |
| D25 | S:377 | PR links from provider table and `pr_links` (DS272). |
| D26 | S:378 | Running release without phases refused; `--no-phases REASON` (DS278). |

#### A.11 Rule file (RF)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| RF-3 (no ID) | RF:3 | Record work as a task before starting it. | imperative; advice | task |
| RF-4 (no ID) | RF:4 | Start branch names with the task ID. | imperative; advice | branch name |
| RF-5 (no ID) | RF:5 | Change status only with `set-task-status`. | imperative; check: `project_artifacts.py#cmd_set_task_status` | status |
| RF-6 (no ID) | RF:6 | Publish Full Progress once at turn end: `pending --json --refresh`, publish, `mark-published`; features never published. | imperative; check: `hook_end_of_turn.py#build_reason` | publish |
| RF-7 (no ID) | RF:7 | Never type a status row by hand. | imperative; advice | status |
| RF-8 (no ID) | RF:8 | Put every doc under `docs/`. | imperative; advice | docs |
| RF-9 (no ID) | RF:9 | Record written in working tree; plugin never commits or pushes; project commits when it chooses. | decl.; advice | commit/push by plugin |
| RF-10 (no ID) | RF:10 | Every activity is a task before it starts (R3.2 text). | decl.; advice | task |
| RF-11 (no ID) | RF:11 | Running while work runs; Waiting or Needs you when blocked (R3.3). | decl.; advice | status |
| RF-12 (no ID) | RF:12 | Built = finished not released; release work its own task (R3.4). | decl.; advice | Built, release |
| RF-13 (no ID) | RF:13 | Background work's task is Running before turn ends (R3.5). | decl.; check: `hook_end_of_turn.py#build_background_reason` | background |
| RF-14 (no ID) | RF:14 | Record every option and the choice in `decisions.json` same turn; unchosen = open decision. | imperative; advice | decisions, owner questions |
| RF-15 (no ID) | RF:15 | Old claude.ai pages deleted only with owner confirmation; ask, delete, `mark-deleted`. | imperative; check: `hook_end_of_turn.py#retired_message` | owner questions, publish |
| RF-16 (no ID) | RF:16 | When giving an Expected time, give its basis (waits on, how long). | imperative; advice | Expected, estimate |
| RF-17 (no ID) | RF:17 | Release Expected = end of last phase (`--phase`); name risk with `--risk`, no padding. | decl.; advice | Expected, release |
| RF-18 (no ID) | RF:18 | Every Running or Built task rides a release (`--rides`); `--release` numbers it. | decl.; check: `project_artifacts.py#release_problems` | release |
| RF-19 (no ID) | RF:19 | Task shipping nothing uses `--no-release REASON`; goes Live, never Built. | decl.; check: `project_artifacts.py#release_problems` | release, Live |
| RF-20 (no ID) | RF:20 | Daily-limit refusal: `mark-deferred full-progress --until <reset>`; give owner the local path. | imperative; check: `project_artifacts.py#cmd_mark_deferred` | daily limit, publish |

All six `check:` targets exist in the code (verified with grep): `cmd_set_task_status` (project_artifacts.py:2433), `build_reason` (hook_end_of_turn.py:349), `build_background_reason` (hook_end_of_turn.py:424), `retired_message` (hook_end_of_turn.py:303), `release_problems` (project_artifacts.py:1870), `cmd_mark_deferred` (project_artifacts.py:2985).

---


### A.3 STACKSPEC

Key: `L<n>` = line n of STACKSPEC. STACKSPEC has no rule IDs; rows use section numbers.


Level key: MUST (includes MUST NOT), SHOULD, MAY, CHOICE, imperative (present-tense "is/runs/never" with no keyword), advice.

#### §0 Purpose, levels, structure

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §0 (no ID) | L51-54 | A clause that only one named technology can meet is defective and MUST be raised against this spec | MUST | governance |
| §0 (no ID) | L56-60 | The selection catalog picks the technology; this spec names or ranks no vendor | imperative | governance, CHOICE |
| §0.2 (no ID) | L224-229 | Level table: MUST absolute; SHOULD deviation needs recorded justification + named approver (§18); MAY optional; CHOICE recorded per product, never graded | definition | levels, deviation, owner/approver |
| §0.2 (no ID) | L231-234 | A conformance check reports a CHOICE as recorded/unrecorded, never conforming/violating | imperative | levels, status names |
| §0.3 (no ID) | L238-253 | Up to five deployables (API, Worker, Web, Admin, iOS/Android); mobile MAY be absent; web MAY be server-rendered; admin MAY be route group | MAY | structure |
| §0.4 (no ID) | L257-266 | A CHOICE lacking a capability needs the stated compensating control (outbox for §7.2; documented recovery + drill for §5.5) | MUST | capability gaps |

#### §1 Thin clients

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §1 (no ID) | L276-277 | The server owns every business rule | imperative | doctrine |
| §1 (no ID) | L288-290 | Every calculation, eligibility, validation, state transition, authorization check, price, threshold MUST be computed server-side | MUST | auth (authorization), doctrine |
| §1 (no ID) | L291-292 | Clients MUST NOT re-derive a value the server sent | MUST | clients |
| §1 (no ID) | L293-295 | Client-side validation only as UX; MUST be mirrored server-side; server MUST NOT trust client checks | MUST | clients, security |
| §1 (no ID) | L300-301 | An endpoint SHOULD return everything one screen needs in one call | SHOULD | API |
| §1 (no ID) | L303-306 | Escape hatch MUST be a deviation (§18) plus a shared test-vector fixture set run in CI | MUST | deviation, tests |
| §1 (no ID) | L311-313 | If mobile ships, business rules MUST be reachable via the API contract, not only the rendering path | MUST | clients |

#### §2 Repository

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §2.1 (no ID) | L321-323 | One repository per product; splitting without a measured reason is a defect | imperative | repo |
| §2.1 (no ID) | L325-327 | Directory names MAY differ; the roles MUST be present and separate | MUST/MAY | repo |
| §2.1 (no ID) | L329-338 | Canonical layout tree lists `docs/specs/` ("binding specifications") and `docs/notes/` ("superseded specs, research, transcripts") | imperative (layout) | docs layout (see D, E) |
| §2.1 (no ID) | L340-341 | A shared module MUST NOT exist before a second consumer or adapter role | MUST | repo |
| §2.1 (no ID) | L342-343 | Workspace mechanism links internal modules; internal modules are not published | imperative | repo |
| §2.1 (no ID) | L344-346 | A product MUST NOT contain a copy of this spec; Stack Profile names the version | MUST | docs, version |
| §2.2 (no ID) | L348-352 | Package manager, workspace, task runner are a CHOICE recorded in Stack Profile | CHOICE | repo |
| §2.2 (no ID) | L354-355 | Tool version MUST be pinned in the repository | MUST | repo, CI |
| §2.2 (no ID) | L356-358 | Lockfile MUST be committed; CI MUST install frozen/locked | MUST | CI |
| §2.2 (no ID) | L359-361 | Uniform task vocabulary MUST exist (`build`, `test`, `lint`, `typecheck`, `codegen`); one root command each | MUST | repo, "task" (build task) |
| §2.2 (no ID) | L362-363 | Task dependencies MUST put `codegen` before `typecheck` and `build` | MUST | repo |
| §2.2 (no ID) | L364 | One root command MUST produce every deployable artifact | MUST | repo |
| §2.2 (no ID) | L365-367 | Where the runner caches, every env var a build reads MUST be declared | MUST | CI cache |
| §2.3 (no ID) | L373-375 | Each ecosystem project MUST stay natively buildable; a developer MUST NOT need another ecosystem's tooling | MUST | repo |
| §2.3 (no ID) | L377-379 | Each such project MUST expose a thin task shim | MUST | repo |

#### §3 Layering and adapters

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §3.1 (no ID) | L387-406 | One-direction layers: clients → server deployables → service modules → data → core; contract/tokens/observability are leaf modules | imperative | architecture |
| §3.2 (no ID) | L410-413 | `core` MUST NOT import framework, I/O, env var, clock, or non-core module | MUST | layering |
| §3.2 (no ID) | L414-415 | Data module MUST be the only importer of DB driver/ORM | MUST | layering |
| §3.2 (no ID) | L416-418 | No shared module may import a web framework | imperative (MUST-strength in list) | layering |
| §3.2 (no ID) | L419-421 | Client apps MUST NOT import data, auth module, `core` or service modules | MUST | layering, auth |
| §3.2 (no ID) | L422 | Circular module dependencies MUST NOT exist | MUST | layering |
| §3.2 (no ID) | L424-426 | A failing dependency-graph check MUST enforce §3.2; tool is a CHOICE | MUST | enforcement, CI |
| §3.3 (no ID) | L430-432 | Every external SDK MUST be imported inside exactly one module | MUST | adapters |
| §3.3 (no ID) | L441-445 | Vendor swap MUST be one adapter + config; no vendor type outside adapter; adapter MUST define degraded behaviour | MUST | adapters |

#### §4 API contract

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §4.1 (no ID) | L453-467 | Contract-first pipeline: committed source; handler MUST validate input/type output; clients generated and committed; CI MUST regenerate and fail on diff; CI MUST run breaking-change check | MUST | API, CI |
| §4.1 (no ID) | L469-470 | Handwritten HTTP calls to product endpoints MUST NOT exist in any client | MUST | clients |
| §4.1 (no ID) | L472-485 | Format is a CHOICE; MUST have committed human-reviewable source and generators for every client language; OpenAPI usual, not required | MUST/CHOICE | API |
| §4.2 (no ID) | L489-497 | API has no UI; thin handlers; one response helper MUST apply error envelope + cacheability; DB/crypto routes MUST run on supporting runtime; edge MAY for stateless | MUST/MAY | API |
| §4.3 (no ID) | L501-518 | `/vN` versions; backward compatible within version; sunset date + `Deprecation`/`Sunset` headers MUST; MUST record client version/platform; MUST refuse below floor with "upgrade required" | MUST | API versioning, security |
| §4.4 (no ID) | L522-527 | Plural resource paths; paginated lists with hard max; one error envelope; idempotency key on mutations; per-screen endpoints | imperative | API |
| §4.5 (no ID) | L531-550 | Compress text >1 KB (MUST, verified); payload SHOULD <50 KB, else MUST justify + paginate; CI SHOULD fail; cacheability per endpoint, default `no-store`; public MUST be served from cache/CDN; ETag SHOULD; `If-Match` MUST where concurrent edits; marketing pages MUST be static | MUST/SHOULD | API, perf |
| §4.6 (no ID) | L557-558 | Every endpoint MUST declare a rate-limit bucket | MUST | API, auth-adjacent |
| §4.6 (no ID) | L559-560 | Endpoint with no bucket MUST fail the route-coverage test (§11.1); same gate enforces authorization declarations | MUST | auth, tests |
| §4.6 (no ID) | L561-562 | Credential and token-issuing buckets fail closed; others fail open | imperative | auth, tokens |
| §4.6 (no ID) | L563-564 | Limits are config; responses MUST carry rate-limit headers and `Retry-After` | MUST | API |
| §4.7 (no ID) | L568-574 | No stack traces etc. in prod responses; single error boundary logs with `correlationId`; a test MUST assert no internal detail | MUST | security, tests |

#### §5 Data (domain detail, grouped)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §5 (no ID) | L580-582 | Engine, host and data library are a CHOICE | CHOICE | data |
| §5.1 (no ID) | L586-597 | Data module only; driver MUST support real transactions on write paths (credential and one-time-token races); pooling MUST match execution model; acquisition timeout MUST | MUST | data, tokens (L589-591) |
| §5.2 (no ID) | L601-613 | Schema single source; constraints enforced by engine or recorded chokepoint; every predicate/sort/join key MUST be indexed; no float money; timezone-aware time | MUST | data |
| §5.3 (no ID) | L617-635 | Multi-record writes atomic; RMW needs transaction/conditional; enqueue atomic (§7.2); no external I/O in open transaction; short transactions; non-atomic engines restructure + record in Stack Profile | MUST | data |
| §5.4 (no ID) | L639-652 | Migrations ordered, reversible or justified, dedicated runner with lock, no ad-hoc scripts; destructive changes split across deploys; tested on non-empty data in CI; idempotent seeds; privileged migration role | MUST | data, deploy, tests |
| §5.5 (no ID) | L656-658 | Three tiers preview/dev, staging, production, own datastore + credentials; no prod data in lower tiers without irreversible anonymization | MUST | environments, secrets |
| §5.5 (no ID) | L659-662 | CI integration tests MUST use ephemeral real engine via migrations; mocks/in-memory/shared DB do not qualify | MUST | tests |
| §5.5 (no ID) | L663-674 | PITR MUST with retention (or documented equivalent + drill); encrypted, separately controlled backups; quarterly restore drill; RPO/RTO in Stack Profile; restore enforces erasure suppression list; bounded backup retention | MUST | data, recovery |
| §5.6 (no ID) | L678-698 | Statement timeouts mandatory (else client deadline); hot-path ≤3 datastore round trips; no waterfalls; no N+1; push computation down; named fields; verify on realistic counts | MUST | data, perf |
| §5.7 (no ID) | L702-711 | Every field MUST carry a classification: public, internal, pii, phi, secret | MUST | data, secrets |
| §5.7 (no ID) | L715-717 | Encryption at rest MUST; `secret` fields additionally encrypted at app layer | MUST | secrets |
| §5.7 (no ID) | L718-731 | Minimization (CI MUST fail on unmapped field); retention per table (CI MUST fail without; job MUST enforce + log); export coverage (test MUST fail); erasure inventory | MUST | data, CI |
| §5.7 (no ID) | L732-734 | App role MUST have no update/delete on audit records | MUST | security |
| §5.7 (no ID) | L735-736 | Prod datastore credentials MUST NOT be usable from a dev machine without logged access path | MUST | secrets |

#### §6 Caching (grouped)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §6 (no ID) | L745-764 | Cache ephemeral/untrusted, schema-validated; credential rate limiting fails closed, caches fail open; namespaced keys; erasure-enumerable; explicit invalidation; TTL on every entry; pipelined ops; bounded in-process caches; request memoization | MUST | cache, auth (L748-749) |

#### §7 Jobs (grouped, except security)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §7.1 (no ID) | L772-784 | Substrate-independent job contract; typed payloads; at-least-once, idempotent handlers; atomic claim; backoff + attempt cap + dead-letter; stuck-job recovery; observable, alerting | MUST | jobs |
| §7.2 (no ID) | L786-801 | Enqueue MUST be atomic with write; queue SHOULD live in own datastore where transactional; else outbox MUST; dual-write MUST NOT ship | MUST/SHOULD | jobs |
| §7.3 (no ID) | L805-817 | Polled queue: claim index required; bounded batches; empty-drain backoff; prune terminal jobs; drain frequency/batch/load in Stack Profile; alert on depth/age | MUST | jobs |
| §7.4 (no ID) | L821-824 | Required jobs: mail, push, session and token purge, deletion, export expiry, audit verification, retention, orphan sweep, access review | MUST | jobs, auth (sessions/tokens) |
| §7.5 (no ID) | L828-830 | Trigger/drain endpoints MUST use a dedicated secret compared in constant time; MUST NOT be reachable with user/operator session | MUST | auth, secrets, sessions |
| §7.6 (no ID) | L834-840 | Bounded fan-out concurrency; no unbounded dispatch; listeners/timers cleaned up | MUST | jobs |
| §7.7 (no ID) | L844-853 | No server-pushed live data by default; poll; bidirectional realtime is a deviation; bounded streams MAY | imperative/MAY | clients |

#### §8 Outbound integrations (grouped, except security)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §8.1 (no ID) | L861-876 | Mail CHOICE; authenticated bounce/complaint feedback MUST update suppression list; behind adapter; enqueued; signed webhooks; persisted delivery state; escaped templates | MUST | mail |
| §8.2 (no ID) | L880-899 | Storage via adapter; uploads via short-lived signed URLs from API; clients MUST NOT hold storage credentials; content sniffing; owner record; public/private split; streaming; delete invalidates CDN | MUST | storage, secrets (L884) |
| §8.3 (no ID) | L905-910 | Device tokens MUST NOT go to any party outside the sub-processor register | MUST | tokens, privacy |
| §8.3 (no ID) | L911-921 | Push in notify adapter via job queue; device tokens MUST be deleted on logout, invalidation, erasure; prune dead tokens; no PII in payloads; permission state server-side | MUST | tokens, auth (logout) |
| §8.3 (no ID) | L922 | Transport credentials are secrets under §15 and MUST be rotatable | MUST | secrets |
| §8.4 (no ID) | L929-939 | Every outbound call: mandatory timeout; capped jittered backoff; circuit breaker; connection reuse; declared tested degraded behaviour | MUST | resilience |
| §8.5 (no ID) | L947-955 | SSRF: allow-list (no deny-list); IP checks after DNS and after redirect; no auto-redirect; timeouts, size cap, content-type; no verbatim echo | MUST | security |

#### §9 Clients (grouped, except security)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §9.1 (no ID) | L963-974 | One token source; build emits per platform; committed, CI MUST fail on drift; no hardcoded colors/spacing/fonts/durations (lint SHOULD); runtime theme uses same vocabulary | MUST/SHOULD | design tokens |
| §9.2 (no ID) | L978-979 | Authorization MUST be enforced by the API; route guards are UX | MUST | auth |
| §9.2 (no ID) | L980-981 | No secret may reach a client bundle; build-time check MUST fail on non-public config in client code | MUST | secrets |
| §9.2 (no ID) | L982-998 | Bundle budget, CI MUST fail; shared assets; self-hosted subset fonts with `font-display: swap`; modern images; code-split; modern target; precompiled CSS; data-heavy routes SHOULD stream | MUST/SHOULD | web perf |
| §9.3 (no ID) | L1005-1020 | One server-state layer; no server values in client store; no ad-hoc HTTP; polling declared, paused when hidden, backed off | MUST | clients |
| §9.4 (no ID) | L1024-1028 | Idempotency key per mutation, stored for a documented window; generated at user action; retry MUST carry same key | MUST | API |
| §9.5 (no ID) | L1032-1040 | Clients MUST tolerate unknown fields/enums, send platform+version, render "upgrade required", degrade on absent optional | MUST | clients |
| §9.6 (no ID) | L1044-1052 | No hardcoded user strings; shared key namespace; server text localized or keyed; locale APIs; RTL not precluded | MUST | l10n |
| §9.7 (no ID) | L1059-1072 | One data-collection inventory; generates store privacy + processing record; CI MUST fail on undeclared collection or stale artifacts; SDKs reviewed before adoption | MUST | privacy, CI |
| §9.8 (no ID) | L1078-1088 | Offline: stale-marked cache MAY; no compute over it; persistent bounded queue; server-side conflicts; no sensitive offline data; no offline payment/deletion | MUST/MAY | mobile |
| §9.8 (no ID) | L1090-1092 | Credential storage MUST use hardware-backed secure store, excluded from unencrypted backups | MUST | auth, secrets |
| §9.8 (no ID) | L1094-1098 | Deep links verified, exact allow-list, web fallback; auth-bearing links single-use, short-TTL, consumed by server redirect that strips token | MUST | auth, tokens |
| §9.8 (no ID) | L1100-1104 | Sensitive screens masked; navigation restorable; process death handled | MUST | mobile |
| §9.8 (no ID) | L1106-1112 | Cleartext HTTP disabled, no debug exception in release build; pinning decision MUST be recorded, with backup-pin/rotation if pinning; API base URL from build config (§15) | MUST | security |
| §9.9 (no ID) | L1116-1128 | WCAG 2.2 AA; SHOULD at "release-gate strength, not a hard CI gate"; blocking findings in account/consent/payment/deletion are defects | SHOULD | a11y |

#### §10 Observability (grouped)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §10.1 (no ID) | L1136-1148 | Required capabilities table (error tracking, structured logs, `correlationId` tracing, metrics, alerting with named owners incl. security events, uptime); uptime checks MUST NOT run only inside watched infra | MUST | observability, owner |
| §10.1 (no ID) | L1155-1162 | Non-essential events MUST NOT be emitted/buffered before server-side consent, enforced at ingestion; error reporting is strictly necessary | MUST | privacy |
| §10.2 (no ID) | L1174-1179 | Never-log list on every surface; central redaction utility with a test; crash reporters strip user content | MUST | secrets (logging), tests |
| §10.3 (no ID) | L1186-1225 | First-party consent-gated analytics: declared event schema, unknown events rejected; pseudonymous ref, never email; event classes strictly necessary / non-essential; withdrawable consent; enforced at ingestion; MUST NOT be recorded as a deviation | MUST | privacy |
| §10.4 (no ID) | L1229-1254 | Committed sub-processor register (vendor, purpose, data, region, agreement, owner); error tracker in register; new SDK/flow REQUIRES entry in same change, PR without one MUST be rejected; BAA for health data | MUST | privacy, PR review, owner |

#### §11 Testing

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §11.1 (no ID) | L1262-1269 | Contract tests: every client + server on same fixtures; CI fails on drift; coverage list | imperative | tests |
| §11.1 (no ID) | L1271 | Unit tests: all of `core` plus service logic; pure, no I/O | imperative | tests |
| §11.1 (no ID) | L1273-1276 | Integration tests against ephemeral real datastore; mocks do not count | imperative | tests |
| §11.1 (no ID) | L1278-1280 | Route-coverage test MUST fail build on route without authorization declaration or rate-limit bucket | MUST | auth, tests |
| §11.2 (no ID) | L1284-1285 | E2E of critical web journeys MUST run in CI of every ready PR to default branch and MUST fail it | MUST | tests, ready PR, full run |
| §11.2 (no ID) | L1285-1288 | Flaky spec goes to committed quarantine list (owner, date, reason); never retried until green; still runs, cannot fail build | imperative | tests, owner |
| §11.2 (no ID) | L1288-1289 | Branch gates run E2E only when a user-facing app changed | imperative | tests, branch gate |
| §11.2 (no ID) | L1291-1293 | Mobile smoke SHOULD; else release checklist MUST name manual journeys before each release | SHOULD/MUST | tests, release |
| §11.3 (no ID) | L1297 | Tests run on every PR; default branch always releasable | imperative | tests, CI |
| §11.3 (no ID) | L1298-1299 | A suite that finds no tests MUST fail | MUST | tests |
| §11.3 (no ID) | L1300 | Flaky tests quarantined and fixed, never re-run until green | imperative | tests |
| §11.3 (no ID) | L1301 | Every bug fix gets a regression test | imperative | tests |
| §11.3 (no ID) | L1302-1303 | No coverage-percentage target | imperative | tests |

#### §12 Security and compliance

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §12 (no ID) | L1309-1310 | Secret scanning as pre-commit hook and CI gate; CI scan MUST cover full history | MUST | secret scan, hooks |
| §12 (no ID) | L1311-1312 | Dependency scanning in CI on every PR; fails on known-exploitable prod advisories | imperative | CI, security |
| §12 (no ID) | L1313-1315 | Security headers: HSTS preload, CSP without inline script, nosniff, referrer, permissions | imperative | security |
| §12 (no ID) | L1316-1317 | CORS explicit origin allow-list; reflecting arbitrary origin MUST NOT be default | MUST | security, auth |
| §12 (no ID) | L1318 | TLS 1.2 minimum, 1.3 preferred, everywhere | imperative | security |
| §12 (no ID) | L1319 | Input validation at every boundary against generated schema | imperative | security |
| §12 (no ID) | L1320-1321 | All queries parameterized | imperative | security |
| §12 (no ID) | L1322-1324 | Startup validation: refuse boot on missing/placeholder security config | imperative | secrets, config |
| §12.1 (no ID) | L1328-1339 | DSR as features: rectification via authenticated endpoint, operator corrections audited; export completeness via §5.7; erasure to every store | MUST | privacy, auth |
| §12.2 (no ID) | L1343-1344 | Vulnerability disclosure policy MUST be published with contact and response window | MUST | security, publish (non-artifact) |
| §12.2 (no ID) | L1345-1346 | Advisories MUST be triaged within Stack Profile window | MUST | security |
| §12.2 (no ID) | L1347-1349 | Pen test SHOULD before first public release and at a cadence | SHOULD | security, release |

#### §13 Build, CI and release (full rows)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §13.1 (no ID) | L1357-1371 | Every PR MUST run and fail on 12 gates: frozen install, codegen drift, lint, format, typecheck, unit, integration, contract, route-coverage, dependency scan, secret scan over full history, layer check | MUST | CI, secret scan |
| §13.1 (no ID) | L1373-1375 | Workflows MUST be path-filtered; mandatory for costly runners (macOS) | MUST | CI cost |
| §13.1 (no ID) | L1377-1378 | CI cost SHOULD be kept down without dropping a gate | SHOULD | CI cost |
| §13.1 (no ID) | L1380-1383 | No sub-minute job when it could be a step; only for per-minute runners; self-hosted needs no deviation | SHOULD (bullet under SHOULD) | CI cost |
| §13.1 (no ID) | L1384-1386 | Newer push cancels superseded PR run; default-branch run never cancelled | SHOULD (bullet) | CI |
| §13.1 (no ID) | L1387 | Draft PRs skip CI until marked ready | SHOULD (bullet) | draft PR |
| §13.1 (no ID) | L1388-1391 | Cache installs and task-runner results (sound due to §2.2 env declaration) | SHOULD (bullet) | CI cache |
| §13.1 (no ID) | L1392-1396 | Dominant job/step SHOULD get own job; splittable tests SHOULD shard; find it via `ci_watch` slowest-job summary | SHOULD | CI cost |
| §13.1 (no ID) | L1397-1401 | PR SHOULD run only expensive jobs its change reaches via committed area map; shared path, unmapped path, or default branch runs everything; docs-only runs none | SHOULD | area, full run |
| §13.1 (no ID) | L1401-1402 | A planned skip MUST NOT count as a failure; a job that cannot read the plan runs | MUST | area, CI |
| §13.1 (no ID) | L1402-1405 | Full suite SHOULD still run on default branch on a schedule, only if branch moved since last successful scheduled run | SHOULD | full run, nightly |
| §13.1 (no ID) | L1406-1409 | Later push MUST NOT rerun a job passed on earlier head unless a commit since reaches its areas; such a job is carried (counts as passed, names proving run) | MUST | carry, full run |
| §13.1 (no ID) | L1409-1410 | A release pull request runs everything on its first run only | imperative | full run, release PR |
| §13.1 (no ID) | L1410-1412 | Every tracked file MUST belong to an area, docs paths or run-everything list; PR check fails naming the file | MUST | area |
| §13.1 (no ID) | L1413-1416 | Test shards SHOULD balance by measured seconds (committed timings, longest first, median for unmeasured); ts template ships `shard_balance.py`, `area_select.py`, `plan` job, `nightly-full.yml` | SHOULD | CI |
| §13.1 (no ID) | L1418-1420 | Runner choice is a repository setting, not written in workflows | imperative | CI |
| §13.1 (no ID) | L1422-1429 | Default-branch push run MUST NOT repeat a passed suite: skip if tree equals passed PR head (ignoring workflow-ignored paths); else full; failure to decide runs | MUST | full run, merge |
| §13.1 (no ID) | L1431-1439 | CI MUST keep only newest build artifact per name; delete older after every run; scheduled sweep; names MUST be stable per kind; releases are release assets | MUST | CI, release |
| §13.1 (no ID) | L1441-1445 | Shipped-artifact workflow SHOULD be its own, run only on feeding paths, never docs-only/record-only, startable by hand | SHOULD | CI cost, record |
| §13.2 (no ID) | L1449-1451 | Three-tier promotion not optional: preview per ready PR, staging on merge to default, production on explicit release action | imperative (MUST-strength "not optional") | deploy, ready PR, release |
| §13.2 (no ID) | L1453-1454 | Draft PRs MUST NOT deploy a preview; only the one ready PR gets one | MUST | draft PR, deploy |
| §13.2 (no ID) | L1456 | Migrations run before new code serves | imperative | deploy |
| §13.2 (no ID) | L1457-1458 | Every deploy traceable to commit; rollback documented and rehearsed | imperative | deploy |
| §13.2 (no ID) | L1459-1461 | No per-PR preview → MUST provide equivalent pre-merge env, recorded in Stack Profile | MUST | deploy |
| §13.2 (no ID) | L1463-1467 | Stateful web sessions: host MUST support sticky routing + draining; release runbook MUST state in-flight session handling | MUST | deploy, sessions |
| §13.3 (no ID) | L1471-1472 | Signing material MUST be stored reproducibly with tested recovery | MUST | mobile, secrets |
| §13.3 (no ID) | L1473-1475 | PR builds do not sign/distribute; default-branch merges make internal build; store submission explicit, never automatic | imperative | mobile release |
| §13.3 (no ID) | L1476-1477 | Build numbers from CI run IDs; marketing versions deliberate; both MUST trace to a commit | MUST | version |
| §13.4 (no ID) | L1481-1484 | API MUST deploy before dependent clients; order additive API → web/admin → mobile; mobile MUST NOT depend on unreleased endpoint | MUST | release |
| §13.4 (no ID) | L1486-1488 | Release assets SHOULD carry version in file name `<name>_<version>.<ext>` (DL-96); CI artifacts keep stable names | SHOULD | version, release |
| §13.5 (no ID) | L1492-1494 | Every repo MUST ship a branch gate: one command run before join, against merge base with the branch it joins | MUST | branch gate, join |
| §13.5 (no ID) | L1496-1512 | Steps in order: all guard tests; secret scan of new commits; typecheck changed + dependents; lint same set, continue past failures; unit then integration; E2E only if user-facing app changed (SHOULD affected specs via map; else dependency graph) | MUST (ship) / SHOULD (E2E scoping) | branch gate, secret scan, tests |
| §13.5 (no ID) | L1511-1512 | The ready PR's CI always runs every spec | imperative | full run, ready PR |
| §13.5 (no ID) | L1514-1521 | Order is binding; typecheck and lint required; gate MUST NOT skip them for time; verifier MUST refuse result missing a required step (except "nothing in its scope changed") | MUST | branch gate |
| §13.5 (no ID) | L1523-1525 | Gate fetches target branch before merge base; offline uses local copy and says so | imperative | branch gate |
| §13.5 (no ID) | L1527-1532 | Frozen install first; stop at first failure unless asked; time limit 30 minutes default; timeout kills step tree; unfinished gate never passes | imperative | branch gate |
| §13.5 (no ID) | L1534-1540 | Task-runner/CI config change widens to all packages; lockfile widens unless per-package attribution, then SHOULD treat those packages as changed | SHOULD | branch gate |
| §13.5 (no ID) | L1542-1546 | Gate MUST write machine-readable result (head, base, steps, pass); trusted only for current head and target head; prose "green" is not a result; results never in PR comments | MUST | branch gate, enforcement |
| §13.5 (no ID) | L1548-1555 | Result on older base SHOULD stay valid if intervening commits touch only inert paths (default docs directory, covers project record with artifacts plugin); strict mode keeps exact base | SHOULD | branch gate, record |
| §13.5 (no ID) | L1557-1558 | Guard tests and secret scan MUST run as pre-push hook | MUST | hooks, secret scan |
| §13.5 (no ID) | L1558-1561 | Pre-push hook SHOULD also run typecheck + lint of touched packages and dependents; docs-only push skips | SHOULD | hooks |
| §13.5 (no ID) | L1561-1563 | First push of a branch compares with the branch it forks from, not default | imperative | hooks |
| §13.5 (no ID) | L1563-1565 | Every scanner CI uses MUST be installed by the agent setup script | MUST | secret scan, setup |
| §13.6 (no ID) | L1569-1570 | Each change is a branch named after its task ID, with a draft PR into an integration branch; drafts skip CI; branch gate is their check | imperative | branch name, draft PR, task |
| §13.6 (no ID) | L1571-1572 | Shared contracts committed to integration branch before parallel work | imperative | integration |
| §13.6 (no ID) | L1573-1584 | Merge script joins branches in turn, stops at unresolved conflict; light check (frozen install, typecheck+lint of changed packages, fast guards); no test, no branch gate, no sandbox gate, no re-gate after join fix; steps in `gate.json`; may skip when tree equals trusted head; records step times | imperative | join, full run, enforcement |
| §13.6 (no ID) | L1579-1580 | Ready PR's first CI run is the one full run; later push runs reached jobs and carries rest | imperative | full run, carry |
| §13.6 (no ID) | L1585-1587 | After last join, one ready PR from integration branch to default; its first CI run is the only full suite, E2E included | imperative | ready PR, full run |
| §13.6 (no ID) | L1587-1588 | Fix push after red run reruns failed jobs + reached jobs; others carried | imperative | carry |
| §13.6 (no ID) | L1588 | "It merges when that run is green, never by auto-merge." | imperative | merge |
| §13.6 (no ID) | L1589-1594 | Train frozen during ready-PR CI: push refused until CI finishes or PR closed; offline allowed with warning; override restarts CI; late branch rides next train | imperative | train, push, hooks |
| §13.6 (no ID) | L1595-1596 | A branch not green when the ready PR opens waits for the next one | imperative | train |
| §13.6 (no ID) | L1597-1601 | Merge script SHOULD warn on no online runner for needed label; watcher SHOULD warn on job queued >10 minutes; warn only | SHOULD | CI runners |
| §13.6 (no ID) | L1602-1603 | CI watched via workflow runs for head commit, never PR check list | imperative | CI watch |
| §13.6 (no ID) | L1604-1606 | Branches SHOULD NOT edit a spec's version or change log; add change note naming spec and kind; release folds notes | SHOULD | version, change note, change log |
| §13.6 (no ID) | L1607-1613 | On one shared Linux runner, non-Linux jobs SHOULD run in parallel on another runner | SHOULD | CI runners |
| §13.6 (no ID) | L1614-1617 | On shared/self-hosted runners, ready PRs' CI SHOULD run one at a time; next train waits for run not merge; single-runner label warned by setup | SHOULD | train, CI |
| §13.6 (no ID) | L1618-1623 | After merge the train is removed automatically (integration branch, joined branches, gate-result refs, worktrees); open-PR/unmerged/dirty never removed, listed | imperative | train, cleanup |
| §13.6 (no ID) | L1624-1630 | Delivery log (SHOULD): finished/joined/CI/merged times + deploy "went live"; time to live split waiting/testing/queueing; appended to train release notes; never committed; unknown shown; never blocks cleanup/deploy | SHOULD | Live, release notes, time |
| §13.7 (no ID) | L1634-1644 | Packaged program: CI MUST start packaged form, wait for readiness signal from program and each worker; MUST fail if one does not come up within stated time; declared signals; tree stopped | MUST | CI, tests |
| §13.7 (no ID) | L1646-1647 | No packaged program declares none | imperative | CI |
| §13.8 (no ID) | L1654-1660 | Suites declared in `scripts/delivery/suites.json`; `run_suite.py` records per-machine times (git-ignored); heavy = last full local run >3 minutes or unmeasured; CI times kept apart | imperative (definition) | test cost, local vs CI |
| §13.8 (no ID) | L1661-1664 | Pre-shell-command hook MUST refuse (1) full local run of heavy suite, (2) full local run of suite that passed on same tree locally or in CI | MUST | test cost, hooks |
| §13.8 (no ID) | L1664-1668 | Unmeasured suite measurable once with `run_suite.py --measure NAME`; refused when measurement <30 days old exists | imperative | test cost |
| §13.8 (no ID) | L1669-1672 | Pre-commit hook runs change-note check on staged changes; version/change-log edit off release branch refused at commit; <2 seconds; no-op without settings | imperative | change note, version, hooks |
| §13.8 (no ID) | L1673-1676 | Hook before `gh pr create`/`gh pr ready` MUST refuse ready PR whose head is not a release branch (default `*-integration`); drafts from task branches allowed | MUST | ready PR, branch name, hooks |
| §13.8 (no ID) | L1677-1679 | Merge script MUST work without branch-gate config: joins, says not configured, records no gate ran | MUST | join |
| §13.8 (no ID) | L1680-1685 | Every rule line in a shipped rule file ends with `<!-- check: <path> -->` or `<!-- advice -->`; a test fails on untagged lines or missing paths | imperative | enforcement |

#### §14-§20

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §14 (no ID) | L1691-1703 | Budgets: API p95 read ≤200 ms; session validation ≤10 ms; LCP ≤2.5 s; INP ≤200 ms; CLS ≤0.1; mobile cold start ≤2 s; job queue age p95 ≤60 s; payload ≤50 KB; ≤3 round trips; cold start ≤1 s; web bundle declared, CI-enforced | imperative | perf, sessions |
| §14 (no ID) | L1705-1711 | Budgets measured; regressions fail where gate exists, else triaged; field vitals first-party | imperative | perf |
| §15 (no ID) | L1717-1719 | One config schema per service, validated at startup, fails on missing/malformed/placeholder | imperative | config, secrets |
| §15 (no ID) | L1720-1721 | Separate credentials per tier for every external service; shared is a defect | imperative | secrets |
| §15 (no ID) | L1722-1724 | Secrets in platform secret storage, never committed; example env file MUST contain no real values | MUST | secrets |
| §15 (no ID) | L1725-1726 | Local values MAY be in git-ignored env file; MUST NOT be production credentials | MAY/MUST | secrets |
| §15 (no ID) | L1727-1729 | Mobile config per scheme; mobile binaries MUST NOT contain server secrets | MUST | secrets |
| §15 (no ID) | L1730-1731 | Every key versioned; zero-downtime rotation with runbook | imperative | secrets |
| §15 (no ID) | L1732 | Dedicated secret manager MAY be adopted | MAY | secrets |
| §16 (no ID) | L1738-1742 | DOCSPEC binds doc placement; every product MUST follow DOCSPEC layout and run `docs_check.py` | MUST | docs |
| §16 (no ID) | L1743-1745 | Feature spec at `docs/features/<feature>/spec.md`; cross-feature rules in `docs/architecture/`; features/architecture/design-system authoritative | imperative | docs, feature |
| §16 (no ID) | L1746-1747 | Superseded doc moves to `docs/archive/`; archive never authoritative | imperative | docs |
| §16 (no ID) | L1748-1750 | Agent briefs/reports/scratch live in `docs/work/` on agent branch, never reach default (DOCSPEC §10) | imperative | docs |
| §16 (no ID) | L1751-1753 | Every product MUST carry Stack Profile, DOCSPEC overview pages, architecture overview, local-setup guide, runbooks | MUST | docs |
| §16 (no ID) | L1754 | A product MUST NOT carry a copy of this spec (§2.1) | MUST | docs |
| §16 (no ID) | L1755-1757 | Every non-obvious decision MUST be recorded with rationale and alternatives (DOCSPEC §11.1); comments MUST explain why | MUST | docs |
| §16 (no ID) | L1758-1759 | Agent instructions in root `AGENTS.md`, imported by `CLAUDE.md` | imperative | docs, agents |
| §17 (no ID) | L1765-1785 | Non-goals are deviations needing own design: microservices, bidirectional realtime, offline-first sync, shared UI across web/native, >1 contract format; self-hosted and cross-platform UI are now CHOICE | imperative | deviation |
| §18 (no ID) | L1791-1792 | Every product MUST carry Stack Profile at `docs/architecture/stack-profile.md` (DOCSPEC R12.2) | MUST | docs |
| §18 (no ID) | L1794-1827 | 15 items: STACKSPEC version; selections; pinned versions; min OS; environment inventory (incl. secrets scope); provisioning ledger (credentials owner, no values); collection inventory; residency; resilience; classification; queue economics; pinning; assurance; capability gaps; deviations with reason + named approver | MUST (list) | version, secrets, owner, deviation |
| §18 (no ID) | L1829-1830 | A CHOICE is never a deviation; item 15 only for graded clauses | imperative | levels |
| §19 (no ID) | L1836-1986 | Conformance checklist, ~140 checkbox items restating §2-§18 by area; no IDs | checklist | all |
| §20 (no ID) | L1992 | Semantic versioning; a new MUST is a major version | imperative | version |
| §20 (no ID) | L1993-1994 | Promoting CHOICE to SHOULD/MUST is major; naming a vendor is a defect | imperative | version |
| §20 (no ID) | L1995 | Products record STACKSPEC version in Stack Profile | imperative | version |
| §20 (no ID) | L1996-1997 | Conflict resolved by recorded deviation with named approver | imperative | deviation, owner |
| §20 (no ID) | L1998 | Superseded versions move to `docs/archive/` | imperative | version, docs |
| §20 (no ID) | L1999-2001 | Spec changes when reality outgrows it; code does not drift ahead | advice | governance |

#### §0.1 change log entries that state rules (historical, normative wording)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §0.1 8.8.0 | L64-66 | Later push reruns only reached jobs, carries rest; ready PR first run is the one full run; every tracked file in an area | change log | carry, full run, area |
| §0.1 8.6.0 | L76-78 | Gate order guards → typecheck/lint → tests; time limit never skips lint/types; verifier refuses; pre-push SHOULD lint/typecheck | change log | branch gate |
| §0.1 8.5.0 | L80-83 | §16 points to DOCSPEC; Stack Profile at `docs/architecture/stack-profile.md` | change log | docs |
| §0.1 8.4.0 | L85-87 | Join is light (typecheck, lint, fast guards; no tests, no gate); ready PR CI is the one full run; cites DL-11, DL-13 | change log | join, full run |
| §0.1 8.3.0 | L89-91 | Area map job selection; planned skip never failure; nightly full suite; shards by seconds | change log | area, full run |
| §0.1 8.2.0 | L93-95 | §13.8 guards: heavy >3 minutes; test guard; change-note at commit; ready PRs only from release branches; join without gate; rule tags | change log | test cost, ready PR |
| §0.1 8.1.0 | L97-99 | Split dominant job; Playwright two shards; `ci_watch.py` slowest-job summary | change log | CI |
| §0.1 8.0.0 | L101-107 | `inert_paths`, `lockfile_scope`, `e2e_map`; join quick check incl. tests (later replaced by 8.4.0); push freeze with `DELIVERY_FREEZE_OVERRIDE=1`; §13.7 new MUST; delivery log; cleanup | change log | join, hooks |
| §0.1 7.1.0 | L109-128 | Runner labels a setting; gate fetches base; pre-push compares fork branch; docs-only merge skip; change notes; one ready PR at a time | change log | change note, CI |
| §0.1 7.0.0 | L130-147 | Artifact pruning; gate frozen install + time limit + stop on fail; train cleanup | change log | train |
| §0.1 6.0.0 | L149-174 | Ready PR's CI the only full suite; E2E gate ready PR; default-branch skip; drafts no preview; branch gate; integration flow | change log | full run, ready PR |
| §0.1 5.2.0 | L176-183 | CI cost SHOULD; skip drafts; cancel superseded PR runs | change log | CI |
| §0.1 5.1.0 | L185-198 | Four technology mandates turned into properties | change log | governance |
| §0.1 history | L200-220 | 1.x-4.x named vendors; three problems forced the split | change log | governance |

---


### A.4 AUTHSPEC

Keys: `A` = AUTHSPEC, `S` = STACKSPEC.


Levels as the text says. P0/P1 noted where the text says so. No "Today"/enforcement column exists in this spec. Tags: auth, admin, api, audit, cache, ci, client, config, crypto, levels, logging, perf, privacy, ratelimit, retention, secrets, server-authority, session, token, test, ui, versioning, jobs, questions.

#### A.0 Front matter, scope, binding (§0–§2)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §0.1 (no ID) | A:75 | MUST/MUST NOT absolute; violation is a defect | definition | levels |
| §0.1 (no ID) | A:76 | SHOULD deviation needs written, reviewed justification in configuration reference (§24) | definition | levels |
| §0.1 (no ID) | A:77 | MAY optional | definition | levels |
| §0.2 (no ID) | A:81 | Resolve stack (§2) first; generate no code before | imperative | questions |
| §0.2 (no ID) | A:87 | Generation not complete until §27 gate passes | imperative | test |
| §1.2 (no ID) | A:107 | MUST NOT provide any way for admin to acquire user-plane session | MUST | admin |
| §1.3 (no ID) | A:114 | MUST leave 7 named seams (challenge, event stream, risk, purpose, region, tenancy, user tokens) | MUST | api |
| §2 (no ID) | A:130 | Tech MUST be resolved by §2 procedure; MUST NOT silently assume a stack | MUST | questions |
| §2.1 (no ID) | A:134 | Look for declared stack doc: `docs/architecture/stack-profile.md` first, then 6 paths, then CLAUDE.md `tech_stack`; authoritative | imperative | config |
| §2.1 (no ID) | A:135 | Else infer from manifests, migrations, source, build config, lint config, in that order | imperative | config |
| §2.1 (no ID) | A:141 | Else "stop and ask the user"; no guess, no placeholder | imperative | questions |
| §2.2 (no ID) | A:143 | 11 dimensions MUST be resolved before generation | MUST | questions |
| §2.2 (no ID) | A:153 | No KMS: generation MUST stop and ask; no unmanaged-key fallback | MUST | secrets, questions |
| R2.1 | A:161 | Match project conventions; style: project wins; behaviour/security MUST: spec wins, conflict recorded in configuration reference | MUST | levels, config |
| R2.2 | A:162 | Prefer existing libs; new dep only for KDF, WebAuthn, SAML sig, JWT/JWS, constant-time; hand-rolling is a defect | imperative | crypto |
| R2.3 | A:170 | Map abstract types to most precise native type | MUST | — |
| R2.4 | A:171 | Generation idempotent, deterministic, stably sorted | MUST | — |
| R2.5 | A:172 | Self-contained module; internals MUST NOT be reachable from app code | MUST | secrets |

#### A.1 Architecture (§3)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| INV-1 | A:190 | User session never confers admin-plane permission | MUST NEVER (P0) | admin, server-authority |
| INV-2 | A:191 | Admin session never accepted on user plane and vice versa; immutable `principal_type` checked every validation | MUST NEVER (P0) | session, admin |
| INV-3 | A:192 | User and admin records separate rows, stores, credentials; no linkage | MUST (P0) | admin |
| INV-4 | A:193 | No code path mints a session for another principal (no impersonation) | MUST (P0) | session |
| INV-5 | A:194 | Authorization computed server-side every request; never from client-supplied role/permission/type/id | MUST (P0) | server-authority |
| §3.2 (no ID) | A:198 | Single global user space; isolation boundary is the account | statement | — |
| §3.3 (no ID) | A:202 | Implementation MUST be structured as listed components | MUST | — |
| R3.1 | A:236 | API layer MUST NOT access persistence directly | MUST | — |
| R3.2 | A:237 | Crypto/KMS provider single narrow module; only constant-time helpers exempt | MUST | crypto, secrets |
| R3.3 | A:238 | Audit service write-only for others; no update/delete path | MUST | audit |
| R3.4 | A:239 | Every component testable with persistence, cache, KMS, email substituted | MUST | test |
| §3.4 (no ID) | A:243 | 14 request stages in fixed order (TLS, rate limit, credential, CSRF, session, type, state, consent, step-up, permission, ownership, handler, audit, response) | MUST | ratelimit, session |
| §3.4 stage 3 | A:247 | Exactly one credential source; both presented is rejected | MUST | session, token |

#### A.2 Persistence schema (§4)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R4.1 | A:270 | Relational: entities → tables, real indexes and constraints | imperative | — |
| R4.2 | A:271 | Document engine: enforced schema, unique indexes, app referential check + consistency job | MUST | — |
| R4.3 | A:272 | `[ENC]` encrypted per §5.4; `[HASH]` digest only; `[BIDX]` blind index equality only | MUST | secrets, crypto |
| R4.4 | A:273 | Timestamps UTC, ≥µs precision | imperative | — |
| R4.5 | A:274 | IDs unguessable (≥122 bits); no auto-increment in API/URL | MUST | api |
| R4.6 | A:275 | 5 growth tables MUST have retention job + index | MUST | retention, jobs |
| R4.7 | A:276 | No `SELECT *` on hot path; project used attributes | MUST | perf |
| §4.3 (no ID) | A:288 | `enum` constrained at storage; `json` MUST NOT contain PII | MUST | privacy |
| §4.4 (no ID) | A:299 | `email_index` UNIQUE partial excluding erased | schema | — |
| §4.4.1 (no ID) | A:318 | `pending_verification` purged after 7 days | schema | retention |
| §4.4.1 (no ID) | A:320 | A lock MUST invalidate live sessions | MUST | session |
| R4.8 | A:324 | Locked/pending-deletion fails session validation stage 7 | MUST (P0) | session |
| R4.8a | A:325 | `pending_verification` is a status value; fails stage 7 like locked | MUST | session |
| R4.9 | A:343 | Admin has no password attribute, row or reset path | MUST NOT | admin |
| R4.10 | A:344 | Admin in `pending_enrollment` has no session/permission | MUST NOT | admin |
| §4.6 (no ID) | A:374 | ≤1 active password, ≤1 active TOTP per principal; zero for admin, storage-enforced | constraint | admin |
| §4.6.1 (no ID) | A:380 | Password `[HASH]` KDF, never reversible; TOTP `[ENC]`; passkey/federated null | schema | secrets |
| §4.7 (no ID) | A:392 | `session.token_hash` = SHA-256 of secret; plaintext never stored | schema | session, secrets |
| §4.7 (no ID) | A:396 | `transport` fixed at issuance; MUST NOT be presentable over other transport | MUST | session |
| §4.8 (no ID) | A:418 | Device id server-generated; client id MUST NOT be trusted as key | MUST | server-authority |
| R4.11 | A:426 | Store only device attributes shown to user; no fingerprinting | MUST NOT | privacy |
| §4.9 (no ID) | A:448 | `max_attempts` default 5 | schema | ratelimit |
| R4.12 | A:455 | One-time credential consumption atomic conditional write | MUST (P1) | token |
| §4.10 (no ID) | A:463 | Recovery codes hashed with password KDF; "low entropy" | schema | secrets |
| §4.10 (no ID) | A:465 | Regeneration invalidates prior generations atomically | schema | — |
| R4.13 | A:482 | Role↔permission catalog declared in code; MUST NOT be runtime-editable | MUST | versioning |
| R4.14 | A:510 | App DB principal INSERT+SELECT only on audit; no UPDATE/DELETE/TRUNCATE; grant in migration | MUST | audit |
| §4.13 (no ID) | A:530 | Break-glass justification min 20 chars, constraint-enforced | constraint | admin |
| §4.13 (no ID) | A:534 | `rate_limit_counter` only if no cache tier | schema | ratelimit |
| R4.15 | A:538 | Principal-owned tables carry `principal_type` + `principal_id` | MUST | — |
| R4.16 | A:539 | Ownership checks via single predicate helper | MUST | server-authority |
| R4.17 | A:540 | Principal tables carry `region` default | SHOULD | — |

#### A.3 Crypto and keys (§5)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | A:548 | All crypto through single provider module | MUST | crypto |
| R5.2 | A:549 | CSPRNG for tokens, secrets, salts, nonces, ids | MUST (P0) | secrets, token |
| R5.3 | A:550 | Constant-time comparison of secrets, digests, tokens, signatures | MUST | secrets |
| R5.4 | A:551 | Prohibited MD5, SHA-1, DES, 3DES, RC4, ECB; SHA-1 only HIBP range + TOTP; AEAD required | MUST | crypto |
| R5.5 | A:552 | FIPS mode: validated module; mode recorded, asserted at startup | MUST | crypto, config |
| R5.6 | A:565 | Root keys in external KMS/HSM, non-exportable; no unmanaged-key mode deployed | MUST | secrets |
| R5.7 | A:566 | Local-dev key provider MAY exist; distinct; refuses deployed env; startup fails closed | MAY/MUST | secrets, config |
| R5.8 | A:570 | Argon2id m=19456 KiB, t=2, p=1, 128-bit salt, 256-bit out; 100–250 ms target | imperative | crypto, secrets |
| R5.9 | A:571 | FIPS: PBKDF2-HMAC-SHA-512 ≥600,000 iterations, 128-bit salt | imperative | crypto |
| R5.10 | A:572 | Store alg/params/salt with digest; rehash on outdated params silently | MUST | crypto |
| R5.11 | A:573 | KDF off main thread; bounded semaphore/pool | MUST (P0) | perf |
| R5.12 | A:574 | Password min 12 (15 rec), max ≥64, Unicode, NFKC, no composition, no rotation; reject breach/identifier; paste MUST NOT be blocked | MUST/imperative | secrets, ui |
| R5.13–R5.17 | A:587–591 | AES-256-GCM per-principal DEK; DEK wrapped by KMS, never persisted unwrapped, bounded short-TTL cache; AAD entity‖attr‖principal; envelope carries version, `kek_id`, IV; unique nonces | MUST | crypto, secrets |
| R5.18 | A:597 | `email_index` = HMAC-SHA-256(index_key, normalize(email)); local part lowercased, documented | MUST | crypto |
| R5.19 | A:598 | Blind index is personal data; deleted on erasure | MUST | privacy |
| R5.20 | A:599 | Blind index never displayed, returned or logged | MUST NOT | logging, secrets |
| R5.21 | A:603 | No plaintext IP in any table; HMAC truncated 16 bytes | MUST NOT | privacy, logging |
| R5.22 | A:604 | Pseudonym key rotated, default 90 days | MUST | secrets |
| R5.23 | A:605 | Raw IP MAY be in memory for rate-limit; MUST NOT be logged/persisted | MAY/MUST NOT | logging, ratelimit |
| R5.24 | A:609 | Single region for persistence, cache, KMS, backup, logs | MUST | privacy |
| R5.25 | A:610 | Every outbound integration in third-party register (§25.6) | MUST | privacy |
| R5.26 | A:611 | Residency enforcement in one documented code location | MUST | — |
| R5.27 | A:615 | Assertions signed EdDSA (Ed25519) or ES256 (FIPS); no HS* across services | imperative | token, crypto |
| R5.28 | A:616 | Pin algorithm from config; header `alg` never selects; reject `alg: none` | MUST (P0) | token |
| R5.29 | A:617 | Assert iss, aud, exp, nbf (≤60 s skew), typ | MUST | token |
| R5.30 | A:618 | Signing keys rotate default 90 days with overlap ≥ max lifetime + JWKS TTL | imperative | token, secrets |
| R5.31 | A:619 | Stable `kid`; select key by kid; reject jwk/jku/x5u | MUST | token |

#### A.4 Sessions and tokens (§6)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §6.1 (no ID) | A:627 | Sessions are authoritative server-side records; client holds opaque reference | statement | session, server-authority |
| R6.1 | A:631 | Session secret ≥256 bits CSPRNG, URL-safe | MUST | session, secrets |
| R6.2 | A:632 | Only SHA-256(secret) stored; DB leak yields no usable credential | MUST | session, secrets |
| R6.3 | A:633 | Secret never in URL, query, log, error, analytics, crash report | MUST NOT | session, secrets, logging |
| §6.3 table | A:637–641 | User idle 30 d sliding / absolute 90 d; admin 15 min / 8 h; service ≤15 min token | table | session |
| R6.4 | A:643 | `absolute_expires_at` never extended | MUST NEVER | session |
| R6.5 | A:644 | Both timeouts enforced server-side each validation | MUST | session, server-authority |
| R6.6 | A:645 | Values are defaults and hard ceilings; config may shorten, MUST NOT lengthen | MUST NOT | session, config |
| R6.7 | A:646 | Step-up freshness 15 min user, 5 min admin | statement | session |
| R6.8 | A:652 | Signed assertion MAY be minted; ≤5 min (default 120 s) | MAY | token |
| R6.9 | A:653 | Claims iss, sub, aud, exp, iat, jti, sid, principal_type, amr, acr, permissions | imperative | token |
| R6.10 | A:654 | Publish `/.well-known/openid-configuration` and `jwks.json`; only public cacheable endpoints | imperative | token, api |
| R6.11 | A:655 | Assertions not accepted for step-up, admin, privileged ops; read authoritative record | MUST NOT | token, session |
| R6.12 | A:656 | Assertions never a browser/native primary credential | MUST NOT | token |
| R6.13 | A:662 | Cookie: HttpOnly, Secure, SameSite=Lax user / Strict admin, Path=/, `__Host-` | imperative | session |
| R6.14 | A:663 | No parent-domain cookie scope shared with untrusted subdomains | MUST NOT | session |
| R6.15 | A:664 | Admin cookies non-persistent | MUST | session, admin |
| R6.16 | A:668 | Native: `Authorization: Bearer`; never cookie, query, loggable header | imperative | token, logging |
| R6.17 | A:672 | Transport-bound; cookie+bearer both → reject outright | MUST | session |
| R6.18 | A:676 | Cookie state change: Origin/Sec-Fetch-Site allowlist AND CSRF token constant-time | MUST | session |
| R6.19 | A:677 | CSRF token issued at creation, rotated on step-up/credential change, in body, not JS-readable cookie | MUST NOT | session |
| R6.20 | A:678 | Bearer exempt from CSRF token; still validate Origin if present | MUST | session |
| §6.6 (no ID) | A:682 | Target P95 ≤100 ms authenticated read, ≤3 round-trips | target | perf |
| §6.6.1 (no ID) | A:688 | Cache value schema-validated; failure = miss, evict, security event | MUST | cache, session |
| §6.6.1 (no ID) | A:689 | Cache TTL = min(60 s, remaining idle) | imperative | cache |
| §6.6.2 (no ID) | A:694 | Cache MUST be bypassed for admin, step-up, role/credential mutation, deletion, break-glass | MUST | cache, admin |
| §6.6.3 (no ID) | A:705 | No-cache fallback MUST be recorded as known scaling limitation | MUST | cache, config |
| R6.21 | A:709 | `last_seen_at` write-throttled, default 60 s | MUST NOT (P0) | perf |
| R6.22 | A:713 | Revocation invalidates cache before/atomically with write | MUST | cache, session |
| R6.23 | A:717 | Native device id server-generated, secure storage; client id advisory only | MUST | server-authority |
| R6.23a | A:718 | `device.platform` web/ios/android/other from registration, not header | imperative | — |
| R6.24 | A:719 | Native session references device; users list/revoke devices | MUST | session |
| R6.25 | A:720 | New device → `new_device_login` event + notification | MUST | session |
| R6.26 | A:724 | 10 revocation events synchronous with scopes (table A:726–737) | MUST | session |
| §6.8 (no ID) | A:739 | `rotation` supersedes, is not a revocation event | statement | session |
| R6.27 | A:741 | Revocation is state transition + cache invalidation; never rely on expiry | MUST NOT | session |
| R6.28 | A:742 | Assertions from revoked session live ≤5 min | statement | token |
| R6.29 | A:746 | Mint new secret on auth, step-up/MFA, permission change | MUST | session |
| R6.30 | A:750 | Pre-auth id never carried into authenticated session | MUST NEVER | session |
| R6.31 | A:751 | Pending-MFA credential ≤5 min, no permissions, MFA endpoints only | MUST | session |

#### A.5 Authentication flows (§7)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R7.1 | A:759 | Record every attempt in `auth_attempt`; rate limit before persistence | MUST | ratelimit |
| R7.2 | A:760 | Uniform non-enumerating failures | MUST | auth |
| R7.3 | A:761 | Uniform timing; dummy KDF for unknown account | MUST | auth |
| R7.4 | A:762 | Success order: record, mint, device, consent, audit, new-device event | MUST | session |
| R7.5 | A:769 | Auth responses `Cache-Control: no-store` | MUST | api |
| §7.2 table | A:773–780 | Admin: passkey only; password/OTP/OIDC/SAML/TOTP never | table | admin |
| R7.6 | A:782 | Admin accepts only WebAuthn+UV; other methods absent from routing | MUST (P0) | admin |
| §7.3.1 (no ID) | A:789 | Challenge ≥16 bytes, server-stored, ≤5-min TTL | imperative | token |
| R7.7 | A:794 | Challenge server-generated, single-use, expiring | MUST | token, server-authority |
| R7.8 | A:795 | Origin and RP ID from config, never request | MUST | server-authority |
| R7.9 | A:803 | Admin UV required | MUST | admin |
| R7.10 | A:804 | User UV preferred; acr aal2/aal3 | imperative | — |
| R7.11 | A:808 | Non-increasing sign counter rejected + security event | MUST | — |
| R7.12 | A:819 | Admin passkeys MAY be synced; `admin.passkey.allow_synced` default true; BE from verified data | MAY/MUST | admin, config |
| R7.12a | A:820 | Synced admin passkey → staff alert | MUST | admin |
| R7.12b | A:821 | amr hwk/swk; acr aal3 device-bound, aal2 synced | MUST | session, token |
| R7.12c | A:822 | BE mismatch rejected, failed attempt | MUST | — |
| R7.13 | A:826 | Admin ≥2 authenticators before leaving pending_enrollment; SHOULD be independent | MUST/SHOULD | admin |
| §7.4 table | A:832–840 | 7 one-time credential purposes | table | token |
| R7.13a | A:842 | New flow adds a purpose, never reuses one | MUST | token |
| R7.14 | A:843 | Codes ≥8 digits or ≥256-bit links; hash only | imperative | token, secrets |
| R7.15 | A:844 | TTL ≤10 min (default 5); single-use; max 5 attempts | imperative | token, ratelimit |
| R7.16 | A:845 | Context binding via `context_hash`; refuse or correlation value | MUST | token |
| R7.17 | A:846 | Unknown address: identical response, no mail | MUST | auth |
| R7.18 | A:847 | Send-rate caps per §17.5 | imperative | ratelimit |
| R7.19 | A:848 | Email states purpose, expiry, ignore line; no other PII | MUST | privacy |
| R7.20 | A:852 | TOTP RFC 6238, 6 digits, 30 s, ±1 step | imperative | — |
| R7.21 | A:853 | TOTP secret ≥160 bits, `[ENC]`, shown once | imperative | secrets |
| R7.22 | A:854 | Unconfirmed TOTP unusable | MUST NOT | — |
| R7.23 | A:855 | Replay prevention via `last_used_counter` (else 90 s reuse) | MUST | token |
| R7.24 | A:856 | TOTP rate-limited separately | imperative | ratelimit |
| R7.25 | A:857 | TOTP enroll/remove needs step-up, event, notification | imperative | — |
| R7.26 | A:863 | OIDC Code flow + PKCE S256 for every client | imperative | token |
| R7.27 | A:864 | `state` random, stored, single-use; `nonce` validated | MUST | token |
| R7.28 | A:865 | ID token checks; ≤60 s skew; keys cached bounded TTL | imperative | token |
| R7.29 | A:866 | Redirect URIs exact-match allowlist | MUST | — |
| R7.30 | A:867 | Native verified deep links; no custom URL schemes | MUST/MUST NOT | client |
| R7.31–R7.33 | A:871–873 | SAML: pre-configured IdP cert; signature covers assertion, recipient/Destination/Audience/time/InResponseTo, replay; XXE/DTD off, XSW-resistant, not hand-built | MUST | crypto |
| R7.34 | A:877 | Auto-link only if verified email + trusted provider; else MUST NOT | MUST NOT | — |
| R7.35 | A:880 | Provider email trust is explicit per-connection config | imperative | config |
| R7.36 | A:881 | Linking from settings needs step-up | imperative | — |
| R7.37 | A:882 | Refuse unlink leaving no method | MUST | — |
| R7.38 | A:886 | JIT provisioning runs full registration incl consent | MUST | privacy |
| R7.39 | A:890 | Provider tokens never persisted | MUST NOT | secrets, token |
| §7.7 (no ID) | A:894–900 | Registration steps; step 5 single atomic transaction | imperative | — |
| R7.40 | A:902 | Registration response identical for existing address | MUST | auth |
| R7.41 | A:903 | Unverified account cannot authenticate beyond verify flow | MUST NOT | — |
| R7.42 | A:904 | Unverified registrations purged after 7 days | MUST | retention |
| R7.43 | A:908 | Email change: step-up, confirm new, notice+cancel old, revoke others | imperative | session |

#### A.6 MFA, recovery, lifecycle (§8–§10)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §8.1 (no ID) | A:916 | Admin MFA mandatory (passkey only); user optional | table | admin |
| R8.1 | A:923 | Confirmed second factor → pending-MFA; no full session | MUST | session |
| R8.2 | A:924 | Passkey+UV satisfies both factors | MUST NOT | — |
| R8.3 | A:925 | Users can enroll multiple factors | MUST | — |
| R8.4 | A:926 | Removing last factor needs step-up + notification | imperative | — |
| R8.5 | A:930 | Admin auth always WebAuthn+UV; no fallback | imperative | admin |
| R8.6 | A:931 | TOTP not registrable for admin | MUST NOT | admin |
| R8.7 | A:935 | 10 recovery codes, ≥128 bits each, shown once, KDF-hashed | imperative | secrets |
| R8.8 | A:936 | Regeneration invalidates earlier generations atomically | imperative | — |
| R8.9 | A:937 | Recovery code use: event, notify, prompt re-enroll | MUST | — |
| R8.10 | A:938 | Recovery attempts own counter | imperative | ratelimit |
| R8.11 | A:944 | Step-up freshness 15 min user, 5 min admin | imperative | session |
| R8.12 | A:945 | 12 step-up operations (table A:947–960) | imperative | session |
| R8.13 | A:962 | Step-up re-verifies real factor; strongest enrolled | MUST | — |
| R8.14 | A:963 | Step-up server-side at route; client dialog counts for nothing | MUST | server-authority |
| R8.15 | A:964 | Step-up updates `stepped_up_at`, rotates CSRF; no absolute extension | imperative | session |
| §8.6 table | A:968–972 | aal1/aal2/aal3 definitions | definition | session |
| R8.16 | A:974 | Admin sessions aal2 or aal3 | MUST | admin |
| R8.17 | A:975 | acr/amr on session and in assertions | MUST | token |
| §9.1 (no ID) | A:985–989 | Reset: uniform response; credential ≥256 bits, TTL ≤15 min; MFA before completion; revoke all, notify | imperative | token |
| R9.1 | A:991 | Reset does not bypass MFA | MUST NOT | — |
| R9.2 | A:992 | Reset does not remove factors | MUST NOT | — |
| R9.3 | A:993 | Reset does not create session | MUST NOT | session |
| R9.4 | A:994 | Other reset credentials invalidated on consume or password change | MUST | token |
| R9.5 | A:998 | Factor recovery order; else admin exception path | imperative | — |
| R9.6 | A:999 | Factor recovery not by email alone | MUST NOT | — |
| R9.7 | A:1003 | Recovery notifies all verified contact points | MUST | — |
| R9.8 | A:1004 | `recovery_used` event | MUST | — |
| R9.9 | A:1010 | Admin ≥2 authenticators; SHOULD prompt periodic check | SHOULD | admin |
| R9.10 | A:1011 | No admin self-service recovery | statement | admin |
| R9.11 | A:1012 | Total-loss path: different approver, ≤15-min window, audit, revoke | MUST | admin |
| R9.11a | A:1019 | Recovery status pending→approved→completed / rejected / expired; expired not reopened | MUST NOT | admin |
| R9.12 | A:1020 | Enrollment window grants only registration; not a session | MUST NOT | admin |
| R9.13 | A:1021 | No second approver → break-glass; MUST be in runbook | MUST | admin |
| §10 tables | A:1027–1042 | User and admin state machines | table | — |
| R10.0a | A:1044 | `suspended` vs `offboarded` distinct | statement | admin |
| R10.1 | A:1045 | Every transition audited (+ security event for users) | MUST | audit |
| R10.2 | A:1046 | Automatic lockout time-bounded, self-releasing | MUST | ratelimit |
| R10.3 | A:1047 | `erased` terminal | imperative | privacy |

#### A.7 Authorization, admin plane, service accounts (§11–§13)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R11.1 | A:1057 | No check tests a role name | imperative | server-authority |
| R11.2 | A:1058 | Permission set computed server-side every request | imperative | server-authority |
| §11.2 (no ID) | A:1064–1084 | Permission catalog (12 user, 13 admin) | catalog | — |
| R11.3 | A:1086 | `read_pii` separate from `list` | statement | privacy |
| §11.3 table | A:1090–1097 | 6 system roles | catalog | — |
| R11.4 | A:1099 | `break_glass` only via activation flow, always expires | MUST NOT | admin |
| R11.5 | A:1103 | Every endpoint declares permission; missing → deny + fail build | MUST | api, ci |
| R11.6 | A:1104 | Checks server-side, stateless, every request | imperative | server-authority |
| R11.7 | A:1105 | Ownership predicate in the fetch query | MUST | server-authority |
| R11.8 | A:1106 | Every mutation carries ownership predicate | MUST (P0) | server-authority |
| R11.9 | A:1107 | Admin cross-account access audited | MUST | audit |
| R11.10 | A:1111 | Single ownership-predicate helper | MUST | — |
| R11.11 | A:1115 | Denial does not distinguish absent vs forbidden | MUST NOT | api |
| R11.12 | A:1116 | Every denial audited `denied` | MUST | audit |
| R12.1 | A:1124 | Admin separate route namespace `/v1/admin/*`; SHOULD separate hostname | MUST/SHOULD | admin |
| R12.2 | A:1125 | Admin type check at stage 6 | MUST | admin |
| R12.3 | A:1126 | Admin network-restricted | SHOULD | admin |
| R12.4 | A:1127 | Admin sessions never cached | MUST NOT | admin, cache |
| §12.2 (no ID) | A:1131 | Admin: 15 min idle, 8 h absolute, 5 min step-up, non-persistent, Strict | statement | session |
| R12.5 | A:1135 | PII read audited before data returned; audit failure fails request | MUST | audit |
| R12.6 | A:1136 | Bulk list ids/status only | MUST | privacy |
| R12.7 | A:1137 | Lists cursor-paginated max 100 (§22.3) | MUST | api |
| R12.8 | A:1138 | Lists/searches audited with params | MUST | audit |
| §12.4 table | A:1142–1149 | 6 admin lifecycle actions, all step-up and notify | table | admin |
| R12.9 | A:1151 | Admin cannot set/read password, read TOTP, receive reset | MUST NOT | secrets |
| R12.10 | A:1152 | Every admin action notifies user | MUST | — |
| R12.11 | A:1153 | Admin MFA reset → staff alert | MUST | admin |
| R12.12 | A:1157 | Break-glass: permission, step-up, ≥20-char justification | imperative | admin |
| R12.13 | A:1161 | Break-glass ≤60 min, enforced at resolution | MUST | admin |
| R12.14 | A:1162 | Immediate out-of-app alert; failed alert flagged; in runbook | MUST | admin |
| R12.15 | A:1163 | Actions under grant audited with activation id | MUST | audit |
| R12.16 | A:1164 | Expiry/closure revokes carrying sessions | imperative | session |
| R12.16a | A:1165 | Every activation reviewed; `flagged` → staff alert | MUST | admin |
| R12.17 | A:1166 | Different operator closes; unreviewed >7 days alert | MUST | admin |
| R12.18 | A:1167 | Not routine; frequency reported | MUST | admin |
| R12.19 | A:1171 | No impersonation of any kind | MUST NOT | admin |
| R12.20 | A:1172 | Impersonation would be a spec amendment with 6 minimum controls | statement | versioning |
| R13.1 | A:1188 | Non-human callers are `service` principals; no shared admin user | MUST NOT | — |
| R13.2 | A:1192 | Client secret ≥256 bits KDF-stored, or key pair (preferred) | imperative | secrets |
| R13.3 | A:1193 | Service creds expire default 90 d, max 365 | MUST | secrets |
| R13.4 | A:1194 | Rotation overlap; `rotated_from_id` | MUST | secrets |
| R13.5 | A:1195 | Credential shown once; no retrieval | imperative | secrets |
| R13.6 | A:1199 | Service tokens ≤15 min; no session records | MUST NOT | token |
| R13.7 | A:1200 | Token requests rate-limited and audited | imperative | ratelimit |
| R13.8 | A:1204 | Least privilege; no sensitive admin perms without reviewed exception | MUST | — |
| R13.9 | A:1205 | No break-glass/recovery-approve for service | MUST NOT | — |
| R13.10 | A:1209 | `last_used_at` throttled; unused 90 days reported | MUST | jobs |
| R13.10a | A:1210 | Suspended → immediate token rejection; retired ids never reused | MUST | — |
| R13.11 | A:1211 | Expiry alerts 30/7/1 days | MUST | jobs |
| R13.12 | A:1215 | Future user tokens: subset of user's permissions | statement | — |

#### A.8 Consent, data rights, audit (§14–§16)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R14.1 | A:1223 | Legal docs versioned with content hash; consent per version | imperative | versioning, privacy |
| R14.1a | A:1224 | `kind` and `method` enums | definition | privacy |
| R14.2 | A:1228 | Server-side acceptance check + consent records in same transaction | MUST | server-authority |
| R14.3 | A:1229 | Record version, time, method, hashed origin | imperative | privacy |
| R14.4 | A:1233 | JIT and native paths same gate | MUST | privacy |
| R14.5 | A:1237 | Re-consent blocks at stage 8 | MUST | privacy |
| R14.6 | A:1238 | `consent_required` response lists documents | imperative | api |
| R14.7 | A:1239 | Gate never blocks reading docs, accepting, export, deletion, logout | MUST NOT | privacy |
| R14.8 | A:1247 | Server enforces gate | imperative | server-authority |
| R14.9 | A:1251 | `purpose` column with default | imperative | privacy |
| R14.10 | A:1252 | Withdrawal as easy as granting | MUST | privacy, ui |
| R14.11 | A:1253 | Core-terms withdrawal = deletion; UI says so | MUST | privacy |
| R15.1 | A:1261 | Rights self-service, no human | MUST | privacy |
| R15.2 | A:1265 | Export complete (9 categories); secrets never | MUST | privacy, secrets |
| R15.3 | A:1277 | Machine-readable documented format | imperative | privacy |
| R15.4 | A:1278 | Export async background job | MUST | jobs |
| R15.5 | A:1279 | Export streamed | MUST | perf |
| R15.5a | A:1280 | Export status machine; row outlives artifact | MUST | privacy |
| R15.6 | A:1281 | Download credential ≥256 bits, single-use, ≤7 days, authenticated, audited | imperative | token |
| R15.7 | A:1282 | Artifact encrypted at rest; destroyed on expiry | MUST | privacy |
| R15.8 | A:1283 | Export rate default 1 / 24 h | imperative | ratelimit |
| R15.9 | A:1284 | Export needs step-up | imperative | — |
| R15.10 | A:1288 | Users correct own profile | MUST | privacy |
| R15.11 | A:1289 | Rectification audited with field name, never values (6-year store) | imperative | audit, privacy |
| §15.4 (no ID) | A:1293–1315 | Erasure: phase 1 request, phase 2 grace 30 d (0–30), phase 3 crypto-erasure 7 steps | imperative | privacy |
| R15.12 | A:1317 | No soft-delete as erasure | MUST NOT | privacy |
| R15.13 | A:1318 | Audit survives erasure 6 years, no PII by construction | MUST | audit, retention |
| R15.14 | A:1319 | Downstream purge interface; failure alerts | MUST | privacy |
| R15.15 | A:1320 | Erasure idempotent, resumable | MUST | jobs |
| §15.4.1 (no ID) | A:1326–1350 | Disposition per §4 table; A:1340 purge MUST cover row and artifact | MUST | privacy |
| R15.15a | A:1352 | Table names every §4 entity; CI `authspec_check.py --only erasure` | MUST | ci |
| R15.15b | A:1353 | Admin erasure: repoint service owner, close break-glass first | MUST | admin |
| R15.16 | A:1357 | Backups never hold unwrapped DEKs; destroy in key store | MUST | secrets |
| R15.17 | A:1358 | Runbook: backup retention, re-apply erasures after restore | MUST | retention |
| R15.18 | A:1362 | Locked-out subject admin path (5 controls) | imperative | admin |
| R15.19 | A:1368 | Not default route; usage is a metric | MUST NOT | — |
| R16.1 | A:1376 | Audit append-only, hash-chained | imperative | audit |
| §16.2 (no ID) | A:1380 | Listed actions MUST emit audit on success and failure | MUST | audit |
| §16.2 (no ID) | A:1382 | `actor_type = system` for automated actions | definition | audit |
| R16.2 | A:1402 | App principal INSERT/SELECT only (R4.14) | imperative | audit |
| R16.3 | A:1403 | No update/delete API; pruning by maintenance principal, by age, audited | imperative | audit |
| R16.4 | A:1407 | No PII in audit (no email, name, password, token, secret, raw IP) | MUST NOT | audit, logging, secrets |
| R16.5 | A:1408 | `metadata` serializer strips sensitive patterns | MUST | audit, logging |
| R16.6 | A:1409 | `actor_ip_hash` only | imperative | logging |
| R16.7 | A:1413 | `record_hash` SHA-256 canonical serialization | MUST | audit |
| R16.8 | A:1414 | `seq` gap-free, serialized | MUST | audit |
| R16.9 | A:1415 | `chain_id` partition (default single, optional per day) | imperative | audit |
| R16.10 | A:1416 | Hourly KMS-signed checkpoint | imperative | audit |
| R16.11 | A:1417 | Daily verification job; critical alert | MUST | audit, jobs |
| R16.12 | A:1418 | Audit writes not droppable; PII-read failure fails request | MUST | audit |
| R16.13 | A:1422 | Action names in one code catalog; no ad-hoc literals | imperative | audit, logging |

#### A.9 Abuse, notifications (§17–§18)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R17.1 | A:1430 | Rate limit at stage 2, before persistence and KDF | imperative | ratelimit |
| R17.2 | A:1434 | Counters in shared state (cache or table); per-process is a defect | MUST | ratelimit |
| R17.3 | A:1435 | Counters keyed on hashed identifier | MUST | ratelimit, logging |
| R17.4 | A:1436 | Counter store down → auth endpoints fail closed | MUST | ratelimit |
| R17.4a | A:1440 | Every attempt writes `auth_attempt` (7 methods) | MUST | ratelimit |
| §17.3 table | A:1444–1458 | Password 5/15min id, 20/15min src; TOTP 5/30; recovery 3/60min; passkey 10/50; OTP verify 5/credential; OTP request 3/10min,10/day,30/h; reset 3/h,10/h; registration 5/h; resend 3/h,20/h; admin 3/15min,10/15min + staff alert; export 1/24h; service token 60/min; session validation 1000/min | table | ratelimit |
| R17.5 | A:1460 | Lockout 1→5→15→60 min, self-release | MUST | ratelimit |
| R17.6 | A:1461 | Identifier and source counters both | imperative | ratelimit |
| R17.7 | A:1462 | Generic envelope + `Retry-After`; MUST NOT reveal limit, remaining budget, existence | MUST NOT | ratelimit, api |
| R17.8 | A:1466 | Breach check at set/change | MUST | secrets |
| R17.9 | A:1467 | k-anonymity; full hash never leaves | MUST NEVER | secrets, privacy |
| R17.10 | A:1468 | Breach provider down → fail open + event + metric; the one fail-open | imperative | ratelimit |
| R17.11 | A:1469 | Reject password containing identifier or service name | MUST | secrets |
| R17.12 | A:1473 | Hard send caps per address and account | imperative | ratelimit |
| R17.13 | A:1474 | Global outbound ceiling circuit breaker | MUST | ratelimit |
| R17.14 | A:1475 | Suppress repeated sends to never-verified address after daily cap | MUST | ratelimit |
| R17.15 | A:1479 | `challenge` port, no-op default | MUST | — |
| R17.16 | A:1480 | Challenge provider registered in §25.6 | imperative | privacy |
| R17.17 | A:1484 | `risk_signal` hook before session issuance, no-op default | MUST | session |
| R18.1 | A:1492 | Notifications contain no credentials, tokens, session ids, extra PII | MUST NOT | secrets |
| R18.2 | A:1493 | Delivery async; mail failure never blocks action | MUST | jobs |
| R18.3 | A:1494 | Every notification from a `security_event` row | imperative | — |
| §18.2 table | A:1500–1517 | 16 kinds; `deletion_requested` MUST state erasure date | table | — |
| R18.4 | A:1519 | "This wasn't me" flow | MUST | — |
| R18.5 | A:1520 | Old-address email-change notice has cancel action | MUST | — |
| R18.6 | A:1521 | Security notifications not suppressible | MUST NOT | — |
| R18.6a | A:1522 | Table covers every `security_event.kind` both ways; `authspec_check.py --only enum-values` | MUST | ci |
| §18.3 (no ID) | A:1526–1538 | 11 staff-alert triggers | list | admin |
| R18.7 | A:1540 | Alert path independent of app DB and mail where possible | MUST | — |
| R18.8 | A:1544 | Outbound event vocabulary, no-op port | MUST | — |

#### A.10 API, client, UI (§19–§21)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R19.1 | A:1552 | Resource HTTP, `/v1/` prefix | imperative | api, versioning |
| R19.2 | A:1553 | Contract normative in this doc; implementation MUST emit machine-readable description CI verifies | MUST | api, ci |
| §19.2 table | A:1557–1563 | Prefixes `/v1/auth`, `/v1/me`, `/v1/admin`, `/v1/oauth/token`, `/.well-known` | table | api |
| R19.3 | A:1567 | JSON; strict schema; unknown request fields rejected | imperative | api |
| R19.4 | A:1568 | RFC 3339 UTC; opaque ids; clients MUST NOT parse | MUST NOT | api |
| R19.5 | A:1569 | Mutations accept idempotency key; replay returns original | MUST | api |
| R19.6 | A:1570 | Cursor pagination default 25, max 100; no offset; unbounded = P0 | MUST NOT | api, perf |
| §19.4 (no ID) | A:1572–1669 | Full endpoint tables with permission and step-up | table | api |
| R19.7 | A:1683 | One envelope shape | imperative | api |
| R19.8 | A:1684 | `message` no PII, ids, traces, query, paths | MUST NOT | api, logging |
| R19.9 | A:1685 | `correlation_id` always present and logged server-side | imperative | logging |
| R19.10 | A:1686 | 8 conditions → `invalid_credentials`, same timing | MUST | api |
| R19.11 | A:1695 | Field detail MAY only for non-security input | MAY/MUST NOT | api |
| §19.5 (no ID) | A:1697 | 12 permitted error codes | list | api |
| R19.12 | A:1699 | not_found/forbidden indistinguishable across ownership | MUST NOT | api |
| R19.13 | A:1700 | No framework pages, traces, DB errors in production | MUST NOT | api, logging |
| R19.14 | A:1704 | Never return secrets, blind indexes, token_hash, seq, others' data | imperative | secrets |
| R19.15 | A:1705 | Session response fields; secret only for bearer | imperative | session |
| R19.16 | A:1716 | Breaking change → new path version; 5 forbidden in-version changes | imperative | versioning |
| R19.17 | A:1717 | Additive changes allowed | imperative | versioning |
| R19.18 | A:1721 | TLS 1.2 min, 1.3 preferred; HTTP redirected | MUST | api |
| R19.19 | A:1722 | HSTS max-age=31536000; includeSubDomains; preload once verified | imperative | api |
| R19.20 | A:1723 | 6 headers incl CSP, COOP, CORP, Permissions-Policy | imperative | api |
| R19.21 | A:1730 | `no-store` on every authenticated/auth response; only `/.well-known/*` public | imperative | api, cache |
| R19.22 | A:1731 | CORS exact allowlist; no `*` with credentials | MUST NOT | api |
| R19.23 | A:1732 | Compress >1 KB; never compress secret + attacker content; session response uncompressed | MUST | api, secrets |
| R19.24 | A:1736 | Emit description of every route, schema, code, permission, step-up | MUST | api |
| R19.25 | A:1737 | CI verifies description = routes; every route has permission | MUST | ci |
| R19.26 | A:1738 | SDKs generated from or validated against description | SHOULD | client |
| §20.1 (no ID) | A:1748–1757 | 8-method SDK interface | contract | client |
| §20.2 table | A:1761–1765 | Web HttpOnly cookie; iOS Keychain WhenUnlockedThisDeviceOnly; Android Keystore | table | client, secrets |
| R20.1 | A:1767 | Native secret only in secure storage | MUST | secrets |
| R20.2 | A:1768 | Secret never in log, crash, analytics, breadcrumb, debug (incl dev builds) | MUST NOT | secrets, logging |
| R20.3 | A:1769 | Purge secrets on logout, unauthorized, deletion | MUST | secrets |
| R20.4 | A:1773 | Single-flight re-auth | MUST | client, perf |
| R20.5 | A:1774 | Blocked requests replayed once or failed | MUST NOT | client |
| R20.6 | A:1775 | On unauthorized purge and emit; no guessing | MUST NOT | client |
| R20.7 | A:1779 | Retry only idempotent on transport/unavailable | imperative | client |
| R20.8 | A:1780 | Backoff full jitter, max 3 attempts, honour Retry-After | imperative (P0) | client |
| R20.9 | A:1781 | Retried non-idempotent request carries idempotency key | MUST | client |
| R20.10 | A:1785 | Every error code mapped; unknown → generic failure | imperative | client |
| R20.11 | A:1786 | consent_required/step_up_required first-class | MUST | client |
| R20.12 | A:1790 | Verified deep links; no custom schemes | MUST/MUST NOT | client |
| R20.13 | A:1791 | Platform auth session API; no embedded web view | MUST/MUST NOT | client |
| R20.14 | A:1792 | PKCE S256 on native | imperative | client |
| R20.15 | A:1793 | Cert validation never relaxed; pinning MAY with rotation plan | MUST NOT/MAY | client |
| R20.16 | A:1797 | Biometric gate MAY, local only | MAY | client |
| R20.17 | A:1798 | Server never treats biometric claim as factor | MUST NOT | server-authority |
| R20.18 | A:1802 | Clients tolerate unknown response fields; server rejects unknown request fields | imperative | versioning |
| R20.19 | A:1803 | Tolerate ≤60 s skew; server authoritative on expiry | MUST | server-authority |
| §21 (no ID) | A:1809 | UI rules normative for every interface | statement | ui |
| R21.1 | A:1813 | WCAG 2.2 AA floor; AAA contrast (7:1 / 4.5:1) on errors, status, primary actions | MUST | ui |
| R21.2–R21.4 | A:1814–1816 | Keyboard only; no focus traps; visible focus | MUST | ui |
| R21.5–R21.8 | A:1820–1823 | Native form semantics; errors associated + live region; not color alone; states announced | MUST | ui |
| R21.9–R21.12 | A:1827–1830 | No cognitive test; paste allowed; autocomplete attrs; OTP single input | MUST | ui |
| R21.13–R21.16 | A:1834–1837 | Show/hide toggle; lengths stated; strength not blocking; breach explained | MUST | ui |
| R21.17 | A:1841 | Idle warning ≥20 s to extend, announced | MUST | ui, session |
| R21.18 | A:1842 | Preserve data or warn | MUST | ui |
| R21.19 | A:1843 | Admin 15-min idle warning mandatory | imperative | ui, admin |
| R21.20 | A:1847 | No redundant entry | MUST NOT | ui |
| R21.21–R21.24 | A:1851–1854 | Consent unchecked; version linked; gate keeps export/deletion/logout; withdrawal ≤ grant steps | MUST | ui, privacy |
| R21.25–R21.27 | A:1858–1864 | Export/delete ≤2 nav steps; deletion states 4 things; no confirm-shaming | MUST | ui, privacy |
| R21.28 | A:1868 | No PII in console, localStorage, analytics, replay, crash; replay off on auth screens | MUST NOT | logging, privacy |
| R21.29 | A:1869 | No third-party scripts on auth screens | MUST NOT | privacy |

#### A.11 Performance, retention, config, privacy (§22–§25)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §22.1 table | A:1877–1886 | P95: cache-hit validation ≤5 ms; `GET /v1/me` ≤100 ms; miss ≤30 ms; password ≤500 ms; passkey ≤150 ms; token ≤50 ms; write ≤250 ms; admin list ≤200 ms | table | perf, session |
| R22.1 | A:1888 | Over-budget endpoint optimized, cached or moved to job | MUST | perf |
| R22.2 | A:1892 | ≤3 round-trips hot path; login ≤5 | imperative | perf |
| R22.3 | A:1893 | Independent reads concurrent | MUST | perf |
| R22.4 | A:1894 | No query in loop; set-based permission resolution | MUST | perf |
| R22.5 | A:1895 | No identical query twice per request | MUST NOT | perf |
| R22.6 | A:1899 | Project used attributes; skip encrypted blobs | imperative | perf |
| R22.7 | A:1900 | Every filter/sort/join attr indexed; 17-row inventory | MUST | perf |
| R22.8 | A:1922 | Aggregation in engine | MUST | perf |
| R22.9 | A:1923 | Lists cursor-paginated (R19.6) | imperative | perf |
| R22.10 | A:1927 | KDF off main thread, bounded (R5.11) | MUST | perf |
| R22.11 | A:1928 | Signature verification offloaded/bounded | MUST | perf |
| R22.12 | A:1929 | No sync FS/DNS/socket in handler | imperative | perf |
| R22.13 | A:1930 | Permission resolution O(roles+permissions) | MUST | perf |
| R22.14 | A:1931 | JWKS cached in-process bounded TTL | MUST | cache, token |
| R22.15 | A:1935 | Serverless MUST use external pooler | MUST (P0) | perf |
| R22.16 | A:1936 | Pool < max_connections ÷ instances | MUST | perf |
| R22.17 | A:1937 | Pool acquire timeout default 2 s | MUST | perf |
| R22.18 | A:1938 | Statement timeout default 3 s request, 30 s jobs | MUST | perf |
| R22.19 | A:1939 | No transaction across network I/O | MUST NOT | perf |
| R22.20 | A:1940 | Short transactions, no multi-statement locks on high-write tables | MUST | perf |
| R22.21 | A:1944 | Outbound: timeout, full-jitter backoff, cap default 3, circuit breaker | MUST | perf |
| R22.22 | A:1945 | Open breaker fails fast | MUST | perf |
| R22.23 | A:1946 | KMS unwrap cache MAY, MUST be bounded | MAY/MUST | cache, secrets |
| R22.24 | A:1950 | Session cache TTL min(60 s, idle); invalidate on revoke | imperative | cache, session |
| R22.25 | A:1951 | Permission sets MAY be cached; invalidated on role change | MAY/MUST | cache |
| R22.26 | A:1952 | `/.well-known/*`: `public, max-age=300, s-maxage=600, stale-while-revalidate=60` | imperative | cache, api |
| R22.27 | A:1953 | Everything else `no-store` | imperative | cache |
| R22.28 | A:1954 | Cache reads schema-validated | imperative | cache |
| R22.29 | A:1958 | In-process caches max size + eviction | MUST | cache |
| R22.30 | A:1959 | Bulk ops stream | MUST | perf |
| R22.31 | A:1960 | Timers/listeners cleaned on shutdown | MUST | perf |
| R22.32 | A:1961 | Hot-path logging no deep clone | MUST NOT | logging, perf |
| R22.33 | A:1965 | Idempotency key stored with response, default 24 h | imperative | api |
| R22.34 | A:1966 | OTC consumption atomic (R4.12) | imperative | token |
| R22.35 | A:1967 | Audit seq serialized (R16.8) | imperative | audit |
| R22.36 | A:1968 | Rate-limit increments atomic | MUST | ratelimit |
| R22.37 | A:1969 | No `SELECT ... FOR UPDATE` or serializable on hot auth path | MUST | perf |
| R22.38 | A:1973 | Auth responses SHOULD <4 KB, MUST <50 KB | SHOULD/MUST | perf, api |
| R22.39 | A:1974 | Permission lists compact names | MUST | api |
| R22.40 | A:1975 | Compression per R19.23 | imperative | api |
| R23.1 | A:1983 | Every growing/limited table has an automated job | MUST | retention, jobs |
| §23.2 table | A:1987–1999 | audit 6 y; security_event 1 y; auth_attempt 1 y (90 d alt); session 30 d after expiry; OTC 24 h; export 7 d; counters window+1 h; unverified 7 d; device 90 d | table | retention |
| R23.2 | A:2001 | Non-HIPAA MAY shorten audit retention; MUST NOT exceed legal max | MAY/MUST NOT | retention, config |
| §23.3 table | A:2005–2020 | 14 jobs with cadences (hourly erasure, daily verifier, hourly checkpoint, monthly audit prune, 5-min grant expirer, 90 d keys, etc.) | table | jobs |
| R23.3 | A:2022 | Jobs idempotent, resumable, bounded batches | MUST | jobs |
| R23.4 | A:2023 | No tight polling of hot tables | MUST NOT | jobs |
| R23.5 | A:2024 | Every job run audited with counts | MUST | jobs, audit |
| R23.6 | A:2025 | Job failures alert | MUST | jobs |
| R24.1 | A:2033 | Security values explicit config with secure default; none hardcoded | imperative | config |
| R24.2 | A:2034 | Config tightens, never loosens past §6.3/§8.5/§17.3 ceilings; code enforces | imperative | config, session, ratelimit |
| R24.3 | A:2035 | Secrets from env or secrets manager, never committed; secret-scanning pre-commit and CI | MUST | secrets, ci |
| §24.2 table | A:2039–2069 | 29 config keys with default and ceiling | table | config |
| R24.4 | A:2073 | Startup fails closed on 9 conditions (dev key, no KMS, ceiling, TLS off, CORS wildcard, audit grants, signing key, counter store, cookie attrs) | MUST | config, secrets |
| R24.5 | A:2083 | Log which check failed, never the value; exit non-zero | MUST | logging, secrets |
| R25.1 | A:2091 | Data inventory: classification (identifier/authentication secret/behavioural/derived), lawful basis, retention, protection | MUST | privacy |
| R25.2 | A:2101 | No attribute without stated purpose | imperative | privacy |
| R25.3 | A:2102 | Never collect DOB, gender, address, gov ids, special category | MUST NOT | privacy |
| R25.4 | A:2103 | Optional attributes genuinely optional | MUST | privacy |
| R25.5 | A:2107 | Auth data not repurposed for analytics/marketing | MUST NOT | privacy |
| R25.6 | A:2111 | No analytics/tag/replay SDK on auth screens (R21.29) | imperative | privacy |
| R25.7 | A:2112 | Non-essential tracking inert until server-recorded consent | MUST | privacy, server-authority |
| R25.8 | A:2116 | PII access separate sensitive permission | statement | privacy |
| R25.9 | A:2120 | Outbound flow register: recipient, data, purpose, lawful basis, location, safeguards; 5 minimum flows | MUST | privacy |
| R25.10 | A:2130 | New recipient = spec amendment | statement | versioning |

#### A.12 Deliverables and gate (§26–§28)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §26 (no ID) | A:2136 | Four deliverables required | imperative | — |
| §26.1 (no ID) | A:2140–2143 | Components, full schema + audit grant, reversible migration where supported, catalog in code | imperative | — |
| §26.2 (no ID) | A:2147–2150 | SDK per platform, secure storage, single-flight, jitter, generated from description | imperative | client |
| §26.3 (no ID) | A:2154 | Test suite per §27.2 | imperative | test |
| §26.4 table | A:2158–2168 | 9 documents incl configuration reference with SHOULD deviations | imperative | config, levels |
| §27 (no ID) | A:2174 | Generation incomplete until every item passes | imperative | test |
| R27.1 | A:2186 | Three audits report zero findings at any severity | MUST | test |
| R27.2 | A:2187 | False positive: make code unambiguous, do not argue | imperative | test |
| R27.3 | A:2188 | Re-run audits after any later auth change | MUST | test |
| §27.2 (no ID) | A:2192–2277 | 80+ named tests MUST exist and pass (9 groups) | MUST | test |
| R27.4 | A:2281 | Secret scanning on working tree and git history | imperative | secrets, ci |
| R27.5 | A:2282 | Dependency scan: no known-exploitable vuln | imperative | ci |
| R27.6 | A:2283 | Description matches routes | imperative | ci |
| R27.7 | A:2284 | No route lacks permission | imperative | ci |
| R27.8 | A:2285 | No prohibited primitive | imperative | crypto |
| R27.9 | A:2286 | No non-constant-time secret comparison | imperative | secrets |
| R27.10 | A:2287 | No log emits ENC/HASH/BIDX value, session secret, password, token, raw IP | imperative | logging, secrets |
| R27.11 | A:2288 | Retired ID registry; numbering append-only; retired: none; `tools/authspec_check.py --only retired` | MUST NOT | versioning, ci |
| §27.4 (no ID) | A:2290–2370 | Audit checklist → controls map | map | test |
| §28 (no ID) | A:2374–2393 | Design rationale table (13 decisions) | advice | — |

---


### A.5 Feature specs: delivery, delivery-speed, test-cost, lifecycle, transcript-folds

Keys: `del`, `dsp`, `tc`, `lc`, `tf` = those feature specs; `DS` = DELIVERYSPEC.


#### A.1 del (delivery guard rails)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | del:69 | No `.delivery/` folder: every delivery hook does nothing | imperative | hooks, opt-in |
| R5.2 | del:71-73 | Ledger written only via `delivery_ledger.py`; atomic, locked, `schema: 1`; lives in main checkout; `link --pr N` by hand | imperative | ledger |
| R5.3 | del:75 | PostToolUse recorder fills ledger: agents, installs, publishes, questions, owner prompt time | imperative | ledger, hooks, publish, questions |
| R5.4 | del:77 | Stop hook blocks per open finding; at most `block_ceiling` (default 3) and `stop_repeat_limit` turns; warn mode blocks nothing | imperative | hooks, stop |
| R5.5 | del:79 | PreToolUse denies calls DELIVERYSPEC lists (local Agent without `PC-bound:`, question while work actionable) | imperative | hooks, questions, agents |
| R5.6 | del:81 | SessionStart prints ledger summary, injects Q-1..Q-5, says when no watcher heartbeat is fresh | imperative | hooks, questions |
| R5.7 | del:83 | Watcher pushes train, opens ready PR (or adopts), merges only when required + all other pull_request workflows green on head; draft never green; `hold` stops | imperative | merge, ready PR, watcher, CI |
| R5.8 | del:85 | Watcher cancels superseded CI runs (when `runner_plan` allows) and holds non-train runs during train CI | imperative | watcher, CI |
| R5.9, R5.10 | (absent) | Removed per del:610 (machine layer) | retired | machine |
| R5.11 | del:87 | `delivery_ledger.py smoke`/`cleaned` only writers of `smoke`, `live_at`, `cleaned_at`; `cleaned` records nothing while branch/worktree left | imperative | ledger, Live |
| R5.12 | del:89 | `delivery_config.py validate` vs schema: unknown key warns, wrong type errors; doctor self-checks config, gh, tz, hooks, ledger, runner hook | imperative | config, doctor |
| R5.13 | del:91 | Shared scripts list; `ci_watch.py` on red train head names job, cancels other runs of head, ends; `--no-cancel-on-red`/`cancel_on_red: false` keeps wait; exit codes 0/1/2/3/4 | imperative | CI, scripts, cancel |
| R5.14 | del:93-101 | UI/e2e branch runs e2e specs of changed screens (DL-86..89); CODE DONE line forms; playwright install by runner (DL230); E2E_CHROMIUM_PATH (DL89) | imperative | test cost, e2e, agents |
| R5.15 | del:103 | One cloud launch = `trig_` + `cse_` ids; one ledger entry, `run_ids`; DL-30 asks once per agent (DL96) | imperative | agents, ETA |
| R5.16 | del:105 | DL-31 accepts named assumed start "~16:40 if you approve the plan by 15:00"; past duration is not an ETA (DL97) | imperative | ETA |
| R5.17 | del:107 | Watcher row records plugin version; SessionStart stops older one by pid, never by name; same version left running (DL98) | imperative | watcher, version |
| R5.18 | del:109 | Cloud RemoteTrigger create sets `mcp_connections: []` + `clear_mcp_connections: true` or lists needed; DL-93 refuses (DL100) | imperative | agents, cloud |
| R5.19 | del:111 | Windows watcher opens no console (`CREATE_NO_WINDOW`); second watcher with heartbeat < 3 intervals and version not older exits (DL109) | imperative | watcher, Windows |
| R5.20 | del:113 | `join.py` never discards a clean merge; conflicts skipped, named; `--push` pushes clean merges; exit 3; partial join defers whole-head steps (DL111) | imperative | join, push |
| R5.21 | del:115 | Shipped scripts ship every sibling import (test); missing import: one line + fix, exit 2; installer lists `missing imports:` (exit 3) and untracked files (DL112) | imperative | installer |
| R5.22 | del:117 | Removed (DS293, D324): `cancel_joined_runs.py` had no caller | retired | CI, cancel |
| R5.23 | del:119 | `ci_tool.py fetch` per-runner cache (`CI_TOOLS_DIR`, `C:/ci-tools`, `~/.cache/ci-tools`), sha256 pin, 5 attempts (10/20/30/40 s), 20 s timeout; gitleaks pin (DL115) | imperative | CI tools, secrets |
| R5.24 | del:121 | DL-94 workflow download check: via `ci_tool.py`, not `RUNNER_TEMP`, sha256; PreToolUse blocks; fails open; `# ci-tool: ok <reason>` (DL116) | imperative | CI, hooks |
| R5.25 | del:123 | Session start warns about a watcher it cannot stop (message text); prunes dead rows > 24 h at heartbeat; session start never writes ledger (DL118) | imperative | watcher |
| R5.26 | del:125 | `scripts/delivery/ci-install.json` keep/skip lists survive update; installer never writes it; bad JSON exit 2 (DL120) | imperative | installer |
| R5.27 | del:127 | `ci_tool.py` needs Python 3.11+ visible to runner account; service runner needs machine-wide install (DL120) | imperative | CI tools, Windows |
| R5.28 | del:129 | `artifact_prune.py` config groups, keep, protect_pr_heads, hold_workflow (24 h); `min_age_seconds` default 3600; API retries 5 (DL121) | imperative | artifacts prune |
| R5.29 | del:131 | `session_guard.py` does not block `gh pr create`/`ready` with `-R` other repo; origin unreadable = guard on (DL121) | imperative | ready PR, guard |
| R5.30 | del:133 | `ci_scope.py` `no_test_reads`, `package_json` keys valve; default key list; unreadable JSON runs full set (DL121) | imperative | CI scope, full run |
| R5.31 | del:135 | `ci_watch.py` Docker trim when `ci.docker_trim` (default off; Windows+Docker); image default `["postgres:16"]` (DL121) | imperative | Docker |
| R5.32 | del:137 | `cleanup.py` writes delivery log only when asked (`--delivery-log` or config); default changed on->off (DL121) | imperative | delivery log, cleanup |
| R5.33 | del:139 | `artifact_prune.workflows` default `["CI","Package"]`; `--sync-workflow`, `--check-workflow`; source config > existing file > default (DL242, DL122) | imperative | artifacts prune, installer |
| R5.34 | del:141 | DL-53 accepts Git Bash / WSL worktree path forms; outside path refused (DL133) | imperative | worktree, hooks |
| R5.35 | del:143 | PreToolUse warns (never blocks) RemoteTrigger `run_once_at` < 2 h ahead while a question is open (DL136) | imperative (warn) | questions, agents |
| R5.36 | del:145 | `agent-check` sets `last_checked`, liveness from branch commit/`last_event_at`; `--note`; closed agent exit 0; stop hook "not checked for N min" from newest; `agents_done` closes on cleanup; `show` lists open agents of finished tasks (DL392, DL303, DL127) | imperative | agents, ledger, status |
| R5.36b | del:147 | Pre-push blocks worktree with no `node_modules` only for JS-check file changes; unknown range counts as JS (DL392) | imperative | pre-push |
| R5.36c (1st) | del:149 | `cancel_old_run.py --pr N` cancels head runs, writes `.delivery/cancelled-runs.json`; `train_freeze.py` lets push through (DL424, DL-114) | imperative | freeze, cancel |
| R5.36d | del:151 | Docs/config-only push skips `typecheck` and `lint` in `fast_guards.py` (DL425, DL-115) | imperative | pre-push, test cost |
| R5.36e | del:153 | `e2e_push_check.py` reads gate result of pushing checkout, else newest matching other worktree (DL426, DL-88) | imperative | pre-push, e2e |
| R5.36c (2nd) | del:155 | Pre-push diffs use `--diff-filter=d`; deleted file not an input (DL400) | imperative | pre-push |
| R5.36a | del:157 | `agent-eta --owns/--brief` stores owns, WARNs on overlap with running/done-not-joined agents; never blocks (DL303) | imperative (warn) | agents, owns |
| R5.37 | del:159 | `ci_watch.py` finds ledger in main checkout via `--git-common-dir` (DL132) | imperative | ledger |
| R5.38 | del:161 | `ci_watch.py` matches train by train, PR, branch, sha; never main/master; `plan --branch`; prints link fix; DL-06 merge hook refusal names link fix (DL138, DL265) | imperative | merge, ledger |
| R5.39 | del:163 | `ci_watch.py` adds all workflows of commit; queued never "failed"; exit 1 only after all complete (DL226, DL139) | imperative | CI watch |
| R5.40 | del:165 | `join.py` stacked branch B on older A: clean merges, real conflict refused, exit 3 (DL128, DL272) | imperative | join |
| R5.41 | del:167 | `join.py --into X` local-only X: exit 2 unless `--create` (DL129) | imperative | join, integration branch |
| R5.42 | del:169 | Light-check "unhandled API call" -> `join-interaction failure` note (DL135) | imperative | join |
| R5.43 | del:171 | `join.py` runs `pre_pr_docs` (visuals, `docs_index.py build` commits "Rebuild generated docs", `docs_check.py --strict`); never changes exit code (DL140) | imperative | join, docs, commit |
| R5.44 | del:173 | Local integration branch ahead: build on it; local-only commits: exit 2; `docs/work/` conflict takes branch side (DL145) | imperative | join |
| R5.46 (1st) | del:175 | Join strips only `docs/work/` paths branches added/changed; restores base; one commit (DL197) | imperative | join, docs/work |
| R5.45 | del:177 | `branch_gate.py` restores `docs/work` after steps; UTF-8 env; log rewrite (DL131, DL134) | imperative | gate |
| R5.46 (2nd) | del:179 | `.cs`/`.csproj` change: `dotnet build` or `warnings` entry (DL141) | imperative | gate, dotnet |
| R5.47 | del:181 | Template jobs with `needs` start `if:` with `!cancelled()` and check results (DL147) | imperative | CI templates |
| R5.48 | del:183-187 | `rust_ci.py` toolchain/env/deny/run; advisory cache up to 7 days; `when_changed`; `toolchain-isolated` default false (DS206, D146, DL304, DS200) | imperative | rust |
| R5.49 | del:189 | Rust `smoke.json` binaries; gate deny/xwin steps; `widen_on` keeps Cargo.lock (DS200) | imperative | rust |
| R5.50 | del:191 | Rust CI paths, `paths-ignore`; crate scoping `rust_scope.py` (`release_pr.head_re` default `^release/.+`); target cache cap `RUST_TARGET_CAP_GB` default 40 (DS206, D148, DS201, D144, DL295) | imperative | rust, CI scope, release |
| R5.51 | del:193 | Doctor `rust` check; warnings advisory > 7 days, disk < 10 GB (DS202, D142) | imperative | doctor, rust |
| R5.52 | del:195 | `rerun_first` repeat run starts with unpassed jobs; `rerun-first/held` status; merge waits (DL181, DL183) | imperative | CI, merge |
| R5.53 | del:197 | Pool runner integration twin jobs (`integration`, `integration-pool`); `pool-db-env` (DL187, DL190) | imperative | CI templates, Docker |
| R5.54 | del:199 | Rust template PATH export; codegen/contract only when target exists (DL192) | imperative | rust |
| R5.55 | del:201 | Join peer fixes: create+push new `--into X`; `<remote>/X`; default `<first task id>-integration`; Cargo.lock conflict (DL225) | imperative | join, branch name |
| R5.56 | del:203 | `ci_watch.py` polls 60 s default, min 30; backoff to 120 s; quota < 200 sleeps; hook blocks `gh run watch` without `--interval` >= 60; exit 5 after 5 gh fails (DL235, DL-95, DL247) | imperative | CI watch, quota |
| R5.57 | del:205 | Join stacked/partial rules; `joined N of M`; exit 3 / 5; `--allow-partial` exit 0 (DL241) | imperative | join |
| R5.58 | del:207 | Join conflict lists files; generated-docs-only conflict rebuilt and committed; watcher records `held` runs (DL249) | imperative | join, commit |
| R5.59 | del:209 | Brief template: held/cancelled run not a failure; wait ~10 min, dispatch once; after 2 held runs write READY; docs W1 never NOT READY (DL258) | imperative | agents, brief |
| R5.60 | del:211 | `rust-release` scope for Rust-only release PR instead of `full` (DL294) | imperative | CI scope, release |
| R5.61 | del:213 | Rust target link `<repo>/target` -> cache; junction on Windows; `/target` in `.git/info/exclude` (DL329) | imperative | rust |
| R5.62 | del:215 | `ci_watch.py` records train only for feature branch; default-branch commit gives no train, no merge ask (DL336, DL-03) | imperative | ledger, merge |
| R5.63 | del:217 | `runs-on` chain `CRSP_RUNS_ON_<OS>` > `CI_RUNS_ON` > hosted default (DL394) | imperative | runners |
| R5.64 | del:219 | Per-job `CRSP_<JOB>` variable read first (DL399) | imperative | runners |
| R5.65 | (absent) | ID gap | - | - |
| R5.66 | del:221 | Declared `stack` block; doctor `stack.tools` FAILS undeclared unknown tool, whatever `enforcement.mode` (DL406, D316) | imperative | stack, doctor |
| R5.67 | del:223 | Cypress/Selenium guardrails G1/G3/G4 (DL409, D316) | imperative | test guardrails |
| R5.68 | del:225 | Cypress rerun via `--spec` list (DL410, D316) | imperative | rerun |
| R5.69 | del:227 | Watcher dead after `watcher_min` (default 20) min no heartbeat; SessionStart restarts; post-merge `cleanup_command`, `smoke_command`; failure stops next push (DP6, D1) | imperative | watcher, merge, Live |
| R5.70 | del:229 | Warn mode logs each would-be block to `.delivery/blocks.log` (5 columns incl session); `delivery_report.py`; Full Progress `Warn mode` section; Stop warn message folds 3+ findings (DP8, D3, DP17, D7, DS280) | imperative | hooks, warn mode, publish |
| R5.71 | del:231 | `watcher.merge_mode` `auto` (default, merge on green) or `manual` (owner merges); manual: hook refuses agent `gh pr merge` under DL-05; setup asks, no default (DP16, D5) | imperative | merge |
| R5.72 | del:233 | `long_pole_globs`, `update_state_files` dropped; old keys warn (DP3, D8) | imperative | config |
| R5.73 | del:235 | `/delivery-onboard --merge-mode` writes warn-mode config + ledger; no default merge mode (exit 2); never commits or pushes (DP10, D10) | imperative | merge, onboarding, commit/push |
| R5.74 | del:237 | CI skips by area (`changed_areas.py`, `.delivery/ci-areas.json`), never workflow path filter under `pull_request`; release PR runs everything unless `release_full` false (DS261, DL-116) | imperative | area, CI scope, full run |
| R5.75 | del:239 | Base image reused by inputs key; only when main built it (label); weekly `--no-cache` rebuild (DS262, DL-117) | imperative | Docker, CI |
| R5.76 | del:241 | Costly lane skipped only with default-branch pass record of same key; `copy-to-main` (DS263, DL-118) | imperative | pass records |
| R5.77 | del:243 | Test what will merge: behind head; `watcher.merge_result` `warn` (default) or `update` (DS259, DL-119) | imperative | merge |
| R5.78 | del:245 | `watcher.infra_retry` (default false): one rerun per head for infra-only failures; patterns list; test failure never retried (DS260, DL-120) | imperative | CI retry |
| R5.79 | del:247 | `.delivery/quarantine.json` flake quarantine; `task` + `review` required; session hook line (DS264, DL-121) | imperative | test cost, flakes |
| R5.80 | del:249 | `gate.json local_gate` `full` (default) or `smoke`; smoke: touched areas only, "CI is the one full run"; `--full` runs all (DS264, cites DL-12) | imperative | full run, test cost, local vs CI |
| R5.81 | del:251 | Local agent recorded without delivery block (task from `<ID>-slug` or first 600 chars); Stop marks local row done when gone or 1 day old; Running task with no worker: one line, never blocking (DS267, DL-123, DL-124) | imperative | agents, status |
| R5.82 | del:253 | PR proves only affected lifecycle targets (`affected_targets.py`); unmapped path selects all (DS269, DL-125) | imperative | lifecycle, area |
| R5.83 | del:255 | Launch naming a task with another To do/Waiting task of same `app` denied once; `PC-bound:` with no step warns (DS270, DL-126, DL-127) | imperative | agents |
| R5.84 | del:257 | `change_notes.py fold --release RELEASE-n` folds only that release's notes; `--all` (DS274, DL-128) | imperative | change note, release |
| R5.85 | del:259 | Stop hook names every release a PR carries; never "train" (DS275, DL-129, DL-64) | imperative | release naming |
| R5.86 | del:261 | Merged entry not idle work until cleaned and smoked (DS276, DL-130) | imperative | status |
| R5.87 | del:263 | `link` sets PR on releases of its cargo; best effort (DS277, DL-131) | imperative | ledger, record |
| R5.88 | del:265 | Carry-forward plan: job runs if no proof head or area touched since; else carried; patch-id on rebase; failure runs job (DS287) | imperative | carry, CI scope |
| R5.89 | del:267 | Release PR runs everything on first run only; later heads follow R5.88 (DS287; narrows DL-80, DL-116) | imperative | full run, release, carry |
| R5.90 | del:269 | Narrower valves: workflow file, `script_jobs`, `lock_jobs`; unmatched path runs all (DS287) | imperative | CI scope |
| R5.91 | del:271 | `carry_verify.py`: carried skipped job counts as passed; one composite action `carry-plan` (DS287) | imperative | carry, required check |
| R5.92 | del:273 | Failed test job: failed tests first, then affected packages, on every trigger (DS287, extends R5.68, DL375) | imperative | rerun, test cost |
| R5.94 | del:275 | Every tracked file belongs to an area; `changed_areas.py unmapped --check` fails PR (DS287) | imperative | area |
| R5.93 | del:277 | `carry_replay.py` proof replay; read-only (DS287) | imperative | carry |
| R5.95 | del:279 | Push of merge commit to default branch carries PR proof; `always` jobs (release, publish, smoke) run; replaces main post-merge full run; nightly stays (DS287) | imperative | carry, full run, main |
| R5.96 | del:281 | `cloud_setup.sh` (cloud only): pinned dev-standards checkout, gitleaks from `tools.json`, pip install, prints `DEV_STANDARDS_SCRIPTS` (DS296) | imperative | cloud, secrets |
| R5.97 | del:283 | `hook_cloud_setup.py` runs script, 150 s limit, never blocks (DS296) | imperative | cloud, hooks |
| R5.98 | del:285 | `ds_scripts.py` scripts path; brief: use `$DEV_STANDARDS_SCRIPTS`, never hand-write change notes, open PRs only with `gh pr create` (D322: no MCP PR tools; agents never merge) (DS296) | imperative | change note, PR, merge |
| R6.1 | del:289 | Every hook fails open (warn, exit 0) except deliberate deny (exit 2) | imperative | hooks |
| R6.2 | del:291 | `CLAUDE_DELIVERY_HOOKS=off` disables all; `checks_off` per rule | imperative | hooks, config |
| R6.3 | del:293 | Scripts stdlib only; Linux, macOS, Windows | imperative | scripts |
| R6.4 | del:295 | `.delivery/` git-ignored except committed `config.json` | imperative | config, git |
| R6.5 | (absent) | Removed per del:610 | retired | machine |
| §7 ledger (no ID) | del:323 | Train states planned..cleaned (or red, abandoned); only the watcher sets `green_at` | imperative | ledger, status |
| §7 contract (no ID) | del:325 | Change `CONTRACT.md` first, then code | imperative | contract |
| §8 (no ID) | del:329-337 | Failure modes: hooks/gh open; ci_watch gh closed; stale gate closed; freeze offline open | imperative | failure modes |
| D1-D5 | del:374-378 | Hooks+scripts; merge at green never `--auto`; block with ceiling; cloud first; machine limits 85% mem / 60% CPU | decision | merge, machine |
| §11 (no ID) | del:384 | Some DL rules advice only (DL-16, DL-17) | advice | enforcement |
| R13.1 | del:420 | No default CI option; setup asks per OS; `delivery_ci.py set/unset` | imperative | CI options, questions |
| R13.2 | del:422 | One shard table `ci-shards.json`; guard: each test file in exactly one shard | imperative | shards |
| R13.3 | del:424 | Templates only in `luismc-delivery`; install/update never commit, push or choose; `.gitleaks.toml` rules + allowlists (DL186, DL211, DL237); `workflow_dispatch` (DL210); `--log-opts="HEAD"` | imperative | installer, secrets, commit/push |
| R13.4 | del:426 | Option 1 own runners on any machines; keeps `runners`, `local_runners`, repair loop, load gate; add runner when wait > X | imperative | runners |
| R13.5 | del:428 | Option 3 cloud sessions only; Linux only | imperative | cloud CI |
| R13.6 | del:430 | Cloud shard result JSON; `error` never a pass; speed probe above 3; `--push` result branch `<results_prefix>/<sha>/<shard id>` (default `ci-result`) | imperative | cloud CI, branch name |
| R13.7 | del:432 | Required checks always commit statuses; ruleset "Any source" (by hand); token never written/printed; description <= 140 chars | imperative | required checks, secrets |
| R13.8 | del:434 | Green = newest status of every required context `success`; `ci_watch.py --context` exit 0/1/4 | imperative | merge, CI |
| R13.9 | del:436 | Doctor `ci` check per option | imperative | doctor |
| R13.10 | del:438 | Inputs key; `--records` skips shard with success record; `failure` never skips; `--all` | imperative | pass records |
| R13.11 | del:440 | Pass records on orphan `ci-pass-records`; ready PR reads only base records; keep newest 20 | imperative | pass records, ready PR |
| R13.12 | del:442 | `/delivery-ci-setup` no default at any question; caps skippable only by explicit "none"; X example 10 | imperative | questions, setup |
| R13.13 | del:444 | By-hand list one function `by_hand_items`; doctor checks each; `confirm ITEM` | imperative | setup, doctor |
| R13.14 | del:446 | Option 1 = own runners on any machines; texts say so; `add-runner` | imperative | runners |
| R13.20 | del:448 | Windows-only tests in `windows-real.json`; Linux MSI is CI check only; installers held until publish; token retry 1/2/4 s; `rollback_check` | imperative | Windows, publish |
| R13.30 | del:466 | `ci.fallback` block: `after_min` no default (absent = off); caps optional | imperative | fallback |
| R13.31 | del:468 | Wait per shard; only `queued` with no runner; `CI_SERIAL` hold counts as no wait | imperative | fallback |
| R13.32 | del:470 | Claim branch `ci-claim/<sha>/<shard>/<attempt>`; first claim wins; fallback claims last | imperative | fallback, branch name |
| R13.33 | del:472 | One status posted only by `post_checked`; refusals | imperative | fallback |
| R13.34 | del:474 | Reaper after `shard_timeout_min` posts `error`; attempts capped at 2 | imperative | fallback |
| R13.35 | del:476 | Caps counted on records branch before start; never overrun | imperative | fallback |
| R13.36 | del:478 | Pass reuse by git tree (`"tree": true`); `branch-gate` shard; never for partial run or UI branch (DP9, D9) | imperative | pass records, gate |
| R13.40 | del:498 | Wait measured per shard from `created_at`; hosted label does not count | imperative | fallback |
| R13.41 | del:500 | Over X one launch per shard; reserve branch `ci-fallback/<sha>/<shard>` | imperative | fallback |
| R13.42 | del:502 | Watcher = session + hourly routine; no watchdog job; up to an hour late | imperative | fallback, ETA |
| R13.43 | del:504 | Cloud launcher fires routine; hosted launcher `gh workflow run`; Windows hosted only for ready PR | imperative | fallback |
| R13.44 | del:506 | `fallback_run.py` checks HEAD, claims last, posts one status; claim missing exit 2 | imperative | fallback |
| R13.45 | del:508 | Cap hit: one warning, nothing starts | imperative | fallback |
| R13.92 | del:510 | Installer state hashes + base copies; 3-way merge; `.new` on conflict; plugin never commits base; run installer on owner's PC not cloud agent; Prettier block (DL218); installer rules (DL227); track detection (DL213) | imperative | installer, commit |
| R13.92b | del:512 | `gate.json` merged by step name on update; per-test timeouts 10 s / 10000 ms / 10 s; doctor `gate-steps` (DL397) | imperative | installer, test cost |
| R13.93 | del:514 | Secret scans skip installer state paths; no shipped var ends `_key/_token/_secret/_pass` (DL204) | imperative | secrets |
| R13.96 (1st) | del:516 | `template_adopt.py` status/diff/adopt; never commits, never pushes (DL308) | imperative | installer, commit/push |
| R13.95 | del:518 | Several tracks in one project; merged `ci.yml`, `gate.json`, `ci-scope.json` (DL245, D244, DL256) | imperative | installer, tracks |
| R13.94 | del:520 | ts track: `package.yml`/`smoke.json` only with Dockerfile or packaged-program setting (DL229, D225) | imperative | installer |
| R13.50 | del:522 | Setup conversation, no default at any question; by-hand list | imperative | setup, questions |
| R13.51 | del:524 | Option 4: fallback kind; `after_min` example 10, no default; hosted Windows only for ready PRs to default branch | imperative | fallback |
| R13.52 | del:526 | Wait definition (dup of R13.31); `CI_SERIAL` does not count | imperative | fallback |
| R13.53 | del:528 | Claim definition (dup of R13.32); `cleanup.py` deletes `ci-claim/*` | imperative | fallback |
| R13.54 | del:530 | Watcher definition (dup of R13.42); `after_min_if_offline` | imperative | fallback |
| R13.55 | del:532 | Reaper (dup of R13.34); cap 2 | imperative | fallback |
| R13.56 | del:534 | Caps optional (dup of R13.35); GitHub spending limit by hand | imperative | fallback |
| R13.57 | del:536 | Speed rules: cheap checks first; one Linux job per suite family; report job is a step; inputs key skip; ready PR reads default-branch records | imperative | CI templates, test cost |
| R13.58 | del:538 | Timing budgets only in CI; speed probe median of 5; scale > 3 refuses; `ci.limits` | imperative | test cost, budgets |
| R13.59 | del:540 | Windows table; Linux MSI CI check only; artifacts kept until publish | imperative | Windows, publish |
| R13.72 | del:542 | Installer update keeps prune workflow list; list merge rule (DL150, DL255) | imperative | installer |
| R13.73 | del:544 | Installer installs `tzdata` when tz fails; asks first when interactive (DL157) | imperative | installer |
| R13.74 | del:546 | `stale_agents` lists open agents whose task is Live, Built or Dropped (DL151, D149) | imperative | agents, status |
| R13.75 | del:548 | Ledger guards: next free train id, no taskless agent, CI by PR+sha (DL156, D158) | imperative | ledger |
| R13.76 | del:550 | WiX 5 `<PermissionEx Sddl>` guidance (DL152) | advice (guidance) | Windows |
| R13.77 | del:552 | `agent_ci.py` picks ledger-open agents; `--task`, `--branch`, `--all`; report path order; force-cancel API (DL153, D155, DL226) | imperative | agents, CI |
| R13.78 | del:554 | Pre-push gitleaks reads ignore files from pushed commit (DL154, D156) | imperative | secrets, pre-push |
| R13.81 | del:556 | `mock_handler_guard.py` fast guard (DL146, D152) | imperative | guards, e2e |
| R13.82 | del:558 | Rust track vitest globalSetup builds crates (DS208, D157) | imperative | rust, tests |
| R13.83 | del:560 | DL-41 owns overlap compare path by path; same file twice denied; disjoint `only` requirement IDs allowed (DL158) | imperative | agents, owns |
| R13.85 | del:562 | Every train-row path takes next free id; `link` makes new row for unknown branch (DL163) | imperative | ledger |
| R13.89 | del:564 | ETAs from history: `delivery_eta.py` median/p75; `no history` < 3 samples; DL-30 refuses eta > 50% above p75 with >= 5 samples; `eta-reason:` (DL168) | imperative | ETA |
| R13.90 | del:566 | Doctor finds Zig/LLVM in ci_tool cache; `ci.scripts-current` warn-only; `ci.wait_min` 10 when unset (DL188) | imperative | doctor |
| R13.91 | del:568 | Rust Windows deferred unless `ci.options.windows` set; `CI_WINDOWS` on (DL192) | imperative | Windows |
| R13.96 (2nd) | del:570 | `always_on_guards` `{name, command, inputs}` run when inputs match (DL307) | imperative | guards |
| §13 failure table (no ID) | del:576-587 | Reaper, claim, cap, ruleset, token, records branch unreachable: all shards run | imperative | fallback |
| R13.15-R13.19, R13.21-R13.29, R13.37-R13.39, R13.46-R13.49, R13.60-R13.71, R13.79-R13.80, R13.84, R13.86-R13.88 | (absent) | Pool IDs removed (del:610); others never present | retired / gap | runner pool |

#### A.2 dsp (delivery speed)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| plan DL1 | dsp:46 | `inert_paths` (default `docs/**`) keep gate result valid | plan row | gate |
| plan DL2 | dsp:47 | Quick join check: install, build, typecheck, union of affected + dependents | plan row | join, test cost |
| plan DL3 | dsp:48 | Agent runs affected suites locally; full only on valve; never branch CI unless Linux-specific | plan row | test cost, agents |
| plan DL4 | dsp:49 | Gate scope; e2e widens to whole suite only on explicit `--full` (DL389); whole suite in CI on ready PR | plan row | test cost, full run |
| plan DL5 | dsp:50 | Build-artifact workflows only when feeding paths change | plan row | CI scope |
| plan DL6 | dsp:51 | Train freeze; offline allow+warn; `DELIVERY_FREEZE_OVERRIDE=1`; abandoned defined | plan row | freeze |
| plan DL7 | dsp:52 | Runner health warnings; queued > 10 min | plan row | runners |
| plan DL8 | dsp:53 | Delivery log in release notes; never commits to main | plan row | delivery log |
| plan DL9 | dsp:54 | Packaged smoke test "(a new MUST)" | MUST (STACKSPEC) | smoke |
| plan DL10 | dsp:55 | dev-standards adopts log and freeze | plan row | dogfood |
| §3 (no ID) | dsp:57 | Each delivery-script change gets scenarios and mutants; versions from change notes | imperative | mutation, version |
| R5.1 | dsp:73 | `gate_verify.py` keeps result valid for base moves under `inert_paths` (default `docs/**`) | imperative | gate |
| R5.2 | dsp:75 | `join.py` runs install, build, typecheck, affected + dependents tests; skip when tree equals trusted head; per-step times | imperative | join |
| R5.3 | dsp:77 | Lockfile widens only on affected deps; shared-UI runs importing apps' e2e | imperative | gate scope |
| R5.4 | dsp:79 | Build-artifact workflows run only for feeding paths; never docs-only | imperative | CI scope |
| R5.5 | dsp:81 | Pre-push refuses pushes to train branch after ready PR until CI finishes or abandoned; offline allow+warn; override env | imperative | freeze, ready PR |
| R5.6 | dsp:83 | `join.py` checks online runner per label before ready PR; `ci_watch.py` warns queued > 10 min; warn only | imperative (warn) | runners |
| R5.7 | dsp:85 | `cleanup.py` records branch times before delete; appended to release notes; UTC | imperative | delivery log |
| R5.8 | dsp:87 | Packaged program: CI starts packaged form, exercises every child process | imperative | smoke |
| R5.9 | dsp:89 | `ci_watch.py` prints wall time and slowest job; never changes exit code | imperative | CI watch |
| R5.10 | dsp:91 | Templates fail fast, few jobs: secret scan first ... unit/contract last; `fail_fast_order`; one job per suite family; report = last step | imperative | CI templates, secrets |
| R5.11 | dsp:93 | `speed_probe.py` median of 5; scale never below 1; > 3 refuses (exit 2, `error`); budgets in CI only | imperative | budgets, local vs CI |
| R5.12 | dsp:95 | `ci.limits` defaults: 2 browser workers, 8.5 GiB | imperative | limits |
| R5.13 | dsp:97 | `db_per_worker.py` one Postgres DB per worker | imperative | tests |
| R5.14 | dsp:99 | `ci_tool.py tool` kinds file/archive/crate; exit 0/1/2 (DS199) | imperative | CI tools |
| R5.15 | dsp:101 | `tools_pin.py`; pins rustup-init 1.29.3, llvm 20.1.8, cargo-deny 0.20.2, cargo-xwin 0.23.1, Zig 0.17.1 (DS199, DS205) | imperative | CI tools, rust |
| R5.16 | dsp:103 | Gate step `paths: KEY` with `scope_map` skip (DS201) | imperative | gate scope |
| R5.17 | dsp:105 | Release asset names `<Product>-<version>-<os>-<arch>.<ext>`; opt-out; build artifacts stable (DL-96, DL-22) | imperative | release assets |
| R5.18 | dsp:107 | Red release CI run finishes: hook refuses `gh run cancel`; `# D105: blocks-all`; gh fail allows; `cancel_joined_runs.py` skips (DL-97, D105) | imperative | cancel, release |
| R5.19 | dsp:109 | No fail-fast on release PR CI; `fail_fast` `never-on-release` (default), `never`, `on`; doctor warns (DL-98, D104) | imperative | CI, release |
| R5.20 | dsp:111 | After red run: failed tests + changed code tests (`rerun_tests.py`); `rerun` default `failed+changed`; narrowed green not merge gate (DL375) | imperative | rerun, test cost, merge |
| R5.21 | dsp:113 | `test_guardrails.py` G1..G7 (10/60/120 s; 30 min; no retries; no sleeps; 20 cases; no mutation on PRs; times uploaded); mode `warn` default (DL-99) | imperative | test cost, mutation |
| R5.22 | dsp:115 | `ci_watch.py` never cancels red run by default; waits all jobs; `cancel_on_red` only for `blocking_job_re`; replaces DL306 default (D105, DL-97) | imperative | cancel, CI watch |
| R5.23 | dsp:117 | `timeout-minutes` <= 30; `artifact-prune.yml` daily/manual only; mutation passes never on PR, only nightly; PRs `--no-mutants` (G6, DL379) | imperative | mutation, CI templates |
| R5.24 | dsp:119 | `delivery_watch.py` cancels older run only when newer run exists, not bot, no failed job; `ci.cancel_skipped` events (D105, DL381) | imperative | cancel, watcher |
| R5.25 | dsp:121 | Stale trains closed (`merged-elsewhere`, `branch-gone`); no train without head; one DL-03 line; at most 5 trains, cache 6 h; `close`, `close-stale`; one line per rule (DL382) | imperative | ledger, stop |
| R5.26 | dsp:123 | Updater test interface contract, language-free (DL-LC1) | imperative | lifecycle |
| R5.27 | dsp:125 | `lifecycle_conformance.py` checks LC-3..7, 25, 26, 28 (DL-LC2, DL-LC3) | imperative | lifecycle |
| R5.28 | dsp:127 | Lifecycle OS step scripts check install..pairing; lanes template names no runner (DL-109, DL-110) | imperative | lifecycle |
| R5.29 | dsp:129 | `lifecycle_release_check.py` affected target lane + default-branch pass record for others; artifact names; separate stores (DL-125, DL-112) | imperative | lifecycle, release |
| R5.30 | dsp:131 | `lifecycle_optout.py` fails opt-out with no decision ID, reason, or past review (DL-113) | imperative | lifecycle |
| R6.1 | dsp:135 | Scripts stdlib; exit 0/1/2/3/4 | imperative | scripts |
| R6.2 | dsp:137 | Freeze and log never block on GitHub outage | imperative | failure modes |
| D1-D20 | dsp:177-196 | Owner decisions (D2 packaged smoke MUST; D12 merge on green; D13 hooks; D15 stop release per merge; D20 agent rows close from branch signals) | decision | various |

#### A.3 tc (test cost)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| S1-S8 | tc:122-129 | Ranked solutions: area jobs; mutation only when files change + nightly; stop at first fail; no agent full branch runs; skip main run; retire fake group; cancel older run; push once per turn | proposal | test cost, mutation, full run |
| R5.1 | tc:149 | `tools/ci_areas.py` maps change to areas; shared or unnamed path runs every area | imperative | area |
| R5.2 | tc:151 | Ready PR runs only touched areas' jobs | imperative | area, ready PR |
| R5.3 | tc:153 | Mutation pass runs only when its scripts, hooks or suite change; `nightly.yml` and `mutants` input force all | imperative | mutation |
| R5.4 | tc:155 | Mutant mode stops scenario at first failed check; crash = caught; uncaught fails loudly | imperative | mutation |
| R5.5 | tc:157 | Push to main differing only under ignored paths skips run | imperative | full run, main |
| R5.6 | tc:159 | Newer commit cancels older ready-PR run | imperative | cancel |
| R5.7 | tc:161 | Delivery suites parallel jobs; gate mutation 4 shards; final job keeps required-check name | imperative | mutation, required check |
| R5.8 | tc:163 | Artifacts record commits every change, pushes once per turn, before any PR, merge or publish | imperative | commit/push, publish |
| R5.9 | tc:165 | `ci_areas.py --branch-advice` prints `light` or `heavy` | imperative | test cost |
| R6.1 | tc:169 | One-area ready PR ~ slowest job (3.0 min delivery after sharding) | target | test cost |
| R6.2 | tc:171 | Cutting a test never removes a check that caught a bug; heavy = over 3 min locally | imperative | test cost |
| §7 (no ID) | tc:175 | Areas list; workflows list | definition | area |
| §8 (no ID) | tc:181-183 | Unknown path runs all; nightly catches drift; record lags | imperative | failure modes |
| D1-D18 | tc:199-216 | Owner decisions (D6 mutation when files change + nightly; D8 push once per turn; D9 03:00 UTC; D17 block; D18 heavy > 3 min) | decision | test cost |

#### A.4 lc (lifecycle)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| D-a..D-j | lc:35-44 | OS package is the update; policies; retry 1 h then 4 h, third failure waits; audited; remove asks with no default; Ed25519; console first; checks on and block; checks only for `targets`; DS234 guards block at once | decision (owner) | lifecycle |
| O-1 | lc:48-56 | Open: where remove result is kept (A/B/C); until decided no history entry required | open | lifecycle, questions |
| §1 (no ID) | lc:23 | Checks LC-1..LC-33 fail build; opt-out only with recorded owner decision | imperative | lifecycle |
| R1.1 | lc:93 | `lifecycle.json` in design system, valid (LC-1) | imperative | lifecycle |
| R1.2 | lc:95 | UI strings from words table; no banned word (LC-2, LC-31) | imperative | lifecycle, UX |
| R1.3 | lc:97 | Updater passes conformance runner (LC-3..7, 25, 26, 28) | imperative | lifecycle |
| R1.4 | lc:99 | Affected targets pass lane (DL-125); others pass record; unmapped path runs all; lane coverage LC-8..21, 29, 32, 33; artifact name | imperative | lifecycle, area |
| R1.5 | lc:101 | UI parts use shared templates/tokens; no overlap/clipping (LC-22..24, LC-30) | imperative | lifecycle, UX |
| R1.6 | lc:103 | Opt-out names owner decision, reason, review date; past date fails (LC-27) | imperative | lifecycle |

#### A.5 tf (transcript folds)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| §3 (no ID) | tf:49-55 | Fold rules: `foldAbove` default 5; errored, small, review never folded; no hook folding; chords; slash commands | imperative | display |
| §4 (no ID) | tf:67 | Both switches start folded every session; toggle lasts session only | imperative | state |
| R5.1 | tf:71 | Change over `foldAbove` folds; at threshold does not; 0 folds every non-empty diff | imperative | fold |
| R5.2 | tf:73 | Line counts from patch: hunks sum, CRLF, new file all lines | imperative | fold |
| R5.3 | tf:75 | Notebook edit counts cells, names cell | imperative | fold |
| R5.4 | tf:77 | Shell outcome: lines, `no output`, first error line | imperative | fold |
| R5.5 | tf:79 | Text cut to width; wide chars 2 cells; ellipsis | imperative | fold |
| R5.6 | tf:81 | Tally adds each file once, lines every time | imperative | fold |
| R5.7 | tf:83 | `/fold-diffs`, `/fold-commands` flip and say state | imperative | fold |
| R5.8-R5.10 | tf:85-89 | Retired (DS281): hook folds; `/fold-hooks` gone | retired | fold |
| R6.1 | tf:93 | Plugin writes no files, runs no commands | imperative | commit/push by plugins |
| R6.2 | tf:95 | `hooks/fold/` imports only sibling `.ts`; no npm package | imperative | purity |
| R6.3 | tf:97 | Chords differ from those other plugins borrow | imperative | keybindings |

---


### A.6 Feature specs: agents, artifacts, audits, docs, models, project-setup, specs

Keys: the feature folder name = its `spec.md`.


#### agents (version 0.1.1)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | agents:53 | Plugin ships exactly one agent, `architect.md` | imperative; test: none (§11) | models |
| R5.2 | agents:55 | Agent runs on `opus` at `medium` effort | imperative; test: test_model_profiles.py D1 | models |
| R5.3 | agents:57 | Agent cannot write: disallowedTools Edit, Write, NotebookEdit, Bash; reads with Read/Grep/Glob | imperative; no test | agents |
| R5.4 | agents:59 | Description names when to use (hard calls, audit review) and when not | imperative; no test | agents |
| R5.5 | agents:61 | Instructions require one direct recommendation, not an options survey | imperative; no test | agents |
| R5.6 | agents:63 | Flags, never decides, scope/irreversible/business tradeoffs (owner's decision) | imperative; no test | owner questions |
| §7 (no ID) | agents:67 | Model and effort follow owner default medium; profile table holds same default | advice/design | models |
| §8 (no ID) | agents:71 | Agent not started fails open; it is advice, "not a gate" | design | gate |

#### audits (version 0.1.1)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | audits:59 | Exactly three skills: security-, performance-, compliance-audit | imperative; no test | |
| R5.2 | audits:61 | Each skill states it reports and does not remediate | imperative; no test | |
| R5.3 | audits:63 | Each skill has Process, severity rubric, checklist, Output Formatting | imperative; no test | |
| R5.4 | audits:65 | Each skill on `opus` at `medium`; matches model-profile table | imperative; test_model_profiles.py P1, P2 | models |
| R5.5 | audits:67 | Performance audit needs measured or calculated impact per finding | imperative; no test | |
| R5.6 | audits:69 | Compliance audit needs proof of server-side enforcement | imperative; no test | |
| §7 (no ID) | audits:73 | model-profiles.json is the single source for model and effort | design | models |
| §8 (no ID) | audits:77 | Audit not run fails open; "It is not a gate" | design | gate |

#### specs (version 0.2.1)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | specs:50 | spec_check reports duplicate/nested/orphan/gapped/out-of-order heading numbers | imperative; test_spec_check.py | |
| R5.2 | specs:52 | Reports duplicate/malformed/gapped/out-of-order req IDs and prefix not matching section | imperative; test_spec_check.py | |
| R5.3 | specs:54 | Reports `§n.n` with no heading, `Rn.n` with no definition | imperative; test_spec_check.py | |
| R5.4 | specs:56 | `--external NAME=PATH` citations resolve there; unregistered falls through with hint | imperative; test_spec_check.py | |
| R5.5 | specs:58 | Statutory numbers >=100 and lettered insertions (R4.9a) not reported | imperative; test_spec_check.py | |
| R5.6 | specs:60 | Exit 0 clean, 1 findings, 2 unparsable; flags --only --strict --json; STACKSPEC/AUTHSPEC registered by default | imperative; no test (§11) | |
| R5.7 | specs:62 | spec-new writes IDed testable reqs passing spec-check, then stops | imperative; no test | |
| R6.1 | specs:66 | spec_check.py uses only Python stdlib | imperative; no test | |
| §3 step 2 (no ID) | specs:43 | spec-new writes to `docs/` in a DOCSPEC repo, else `specs/` | imperative | docs |
| §7 (no ID) | specs:70 | Skills pin `opus` (spec-new) and `sonnet` (spec-check), both medium | design | models |
| §8 (no ID) | specs:74-76 | Unparsable exits 2 never 0; fails closed in CI (findings exit 1) | design | |

#### models (version 0.5.1)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | models:100 | Every plugin SKILL.md is in model-profiles.json; model/effort frontmatter match | imperative; test_model_profiles.py P1, P2 | models |
| R5.2 | models:102 | Every profile medium for Opus and Sonnet; architect medium; top-level effortLevel medium | imperative; test D1 | models |
| R5.3 | models:104 | Agent rules file: one line per role, `{{SUBAGENT_EFFORT}}` placeholder | imperative; test R1 | models |
| R5.4 | models:106 | Settings template registers SessionStart `effort_drift.py`; hook ships beside it | imperative; test S1 | hooks |
| R5.5 | models:108 | Drift hook warns when active Opus/Sonnet ID has no saved effort; silent otherwise | imperative; no test (manual) | hooks |
| R5.6 | models:110 | claude-setup ships Explore agent: haiku, medium, no edit tools; no plugin ships Explore or Plan | imperative; test X1, X2 | models |
| R5.7 | models:112 | No `model-delegation.md` in claude-setup assets | imperative; test M1 | |
| R5.8 | models:114 | Agent rules: code/bugs/migrations/tests to Sonnet; one failed try to Opus (medium, then high); never Sonnet xhigh; lookups to Explore | imperative; test R1 | models |
| R5.9 | models:116 | Report names `opusplan` as option, never sets it | imperative; test O1 | models |
| R6.1 | models:120 | Drift hook always exits 0; warning as `systemMessage`, never to context | imperative; no test | hooks |
| R6.2 | models:122 | Drift hook off with `CLAUDE_SETUP_EFFORT_DRIFT=off` | imperative; no test | hooks |
| R6.3 | models:124 | claude-setup writes nothing outside repo without owner confirmation in change plan | imperative; no test | owner questions |
| §1 (no ID) | models:25 | Main session Sonnet (Opus via /model); code agents Sonnet; medium; Explore Haiku; auto-compact 350000 tokens | design | models |
| §3 (no ID) | models:57 | claude-setup writes model, modelSettings, effortLevel, `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`; preselects medium; asks every run | design | models, questions |
| §3 (no ID) | models:58 | Agent rules tell main session to pass `effort` on every implementation Agent call | imperative | models |
| §3 table | models:65-69 | Precedence order for subagent model, subagent effort, main effort | reference | models |
| §3 table | models:75-85 | Profiles: main Sonnet medium; code agents Sonnet medium; merges/checks scripts; triage Haiku; architect Opus medium; Explore Haiku medium; failed Sonnet -> Opus medium then high | reference | models, merge |
| §3 table | models:87-92 | Skill kinds: judgment Opus; mechanical Sonnet; haiku Haiku (spec-check, project-artifact-check, task-add, task-status-update, docs-index, docs-note, docs-check); setup Sonnet; all medium | reference | models |
| §7 (no ID) | models:128 | model-profiles.json maps four kinds; "It is the single table" | design | models |
| §2 evidence | models:34 | 18 parallel cloud agents used 5-hour limit in ~20 min; five at a time finished | advice | agents |

#### project-setup (version 0.19.0)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | project-setup:66 | tech-stack-setup offers only compatible tech; `check_stack.py --selection` verifies | imperative; no test | stack |
| R5.2 | project-setup:68 | Four tracks TS/Go/Rust/.NET; gate.json, smoke.json, CI in luismc-delivery; installer writes `.gitleaks.toml` (DL186) | imperative; no test | secrets, CI |
| R5.3 | project-setup:70 | Stack Profile records STACKSPEC version claimed and vendors; no spec copy | imperative; no test | version |
| R5.4 | project-setup:72 | Audit mode reports per section, diff before repair | imperative; no test | |
| R5.5 | project-setup:74 | tech-stack-setup builds no auth; asks to run auth-setup at end | imperative; no test | questions |
| R5.6 | project-setup:76 | auth-setup runs `preflight.py --require stack` first; stops naming skill to run | imperative; test_preflight.py | |
| R5.7 | project-setup:78 | preflight exits 0 ok, 1 unmet, 2 bad args | imperative; test_preflight.py | |
| R5.8 | project-setup:80 | auth-setup reports claimed AUTHSPEC version older than bundled | imperative; no test | version |
| R5.9 | project-setup:82 | claude-setup never overwrites CLAUDE.md or settings key; model-split conflict shown | imperative; no test | |
| R5.10 | project-setup:84 | Every skill's model/effort matches model-profiles.json | imperative; test_model_profiles.py | models |
| R5.11 | project-setup:86 | Every shipped rule line ends with a check tag or `advice` | imperative; test_rule_tags.py | enforcement |
| R5.12 | project-setup:88 | Shipped STACKSPEC/AUTHSPEC pass heading/ID/reference checks; AUTHSPEC content checks | imperative; test_spec_check.py, test_authspec_check.py | |
| R5.13 | project-setup:90 | User-level `questions_stop.py` Stop hook blocks plain-text questions, option lists, "parked" without AskUserQuestion; enforces Q-1, Q-2 | imperative; test_questions_stop.py | questions |
| R5.14 | project-setup:92-94 | Agent running = queued/running or eta+no done_at; park allowed when agent due within 60 min; reads turn in 1 MiB blocks, >32 MiB allowed (DL124, DL208) | imperative; no own test row | questions, ETA |
| R5.15 | project-setup:96 | Both `clarifying-questions.md` copies: open question + RemoteTrigger due <2 hours = warning, never block (DL136) | imperative | questions |
| R5.16 | project-setup:98 | pre-push exits 1 when node_modules missing and gate uses pnpm (DL130) | imperative | test cost |
| R5.17 | project-setup:100 | pre-push re-execs worktree's own hook; `PRE_PUSH_REEXEC` stops loop (DL137) | imperative | |
| R5.18 | project-setup:102 | check_stack accepts `{api, components:[rust]}`; unknown component is error (DS196, D138) | imperative | stack |
| R5.19 | project-setup:104 | check_stack warnings: Rust reason, napi matrix, licence note, Windows option, napi on Vercel | imperative (warn) | stack |
| R5.20 | project-setup:106 | Catalog: rust roles api/component; parts; pairings; Rust out of defaults/bundles (DS196) | imperative | stack |
| R5.21 | project-setup:108 | Wizard Phase 1/3/7 and Mode 2 for native components; no section renumbered (DS197) | imperative | stack |
| R5.22 | project-setup:110 | Rust tooling: toolchain exact 1.91.0; `--locked`; CI installs exact version (DS198) | imperative | stack, CI |
| R5.23 | project-setup:112 | Shipped CI takes Node version from project; fallback Node 24; never pins 22 (DL332) | imperative; test_dl332 | CI |
| R5.24 | project-setup:114 | Writes allow rules gh pr create/ready/edit; never `gh pr merge`; DL-73 exception: agents may open PRs, mark ready; merging stays owner's | imperative; test_dl334, test_delivery_hooks | merge, ready PR |
| R5.25 | project-setup:116 | Pre-commit secret-name pattern case rules, gitleaks-like (DL358) | imperative; f31 test | secrets |
| R5.26 | project-setup:118 | SessionStart update offer; asks owner once with AskUserQuestion; hook only prints, never commits, fails open (SO9) | imperative | questions, commit, version |
| R6.1 | project-setup:122 | claude-setup asks target first; one batch after one confirmation | imperative; no test | questions |
| R6.2 | project-setup:124 | Model-profile default medium for every model; table is the one place | imperative; test_model_profiles.py | models |
| §3 (no ID) | project-setup:60 | claude-setup: project default; six plugins; one batch plan; one grouped question round; heavy step held at memory >85% or CPU >60%; never commits or pushes; ci_pin `--check` exits 1 (DL263) | design | questions, commit, test cost |
| §7 (no ID) | project-setup:145 | STACKSPEC `CHOICE` level: choice recorded/unrecorded, never violating | design | |
| §7 (no ID) | project-setup:146 | Delivery installer writes pre-push, commit-msg, config.json, session_guard (DL172) | design | hooks |
| §7 (no ID) | project-setup:147 | Questions hook never loops, park allowed while wave agents run (Q-5), fails open; off via `CLAUDE_QUESTIONS_STOP=off` | design | questions |
| §8 (no ID) | project-setup:168-171 | auth-setup without stack fails closed; check_stack without PyYAML exits 2 | design | |

#### docs (version 1.18.0)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | docs:60 | migrate dry run unless `--apply`; git mv; rewrites links; never deletes (DOCSPEC R9.1-R9.3) | imperative; test_setup.py | |
| R5.2 | docs:62 | migrate twice changes nothing; existing target skipped (DOCSPEC R9.3) | imperative; test_setup.py | |
| R5.3 | docs:64 | init creates layout; never overwrites (DOCSPEC R9.7) | imperative; test_setup.py | |
| R5.4 | docs:66 | move-record moves record to `record_dir`, points artifacts plugin at it (DOCSPEC R9.6) | imperative; test_setup.py | record |
| R5.5 | docs:68 | index build writes index.html, pages, features/index.md, decisions.md, docs-map.json, llms.txt; deterministic; file:// (DOCSPEC R6.1-R6.3) | imperative; test_index.py | |
| R5.6 | docs:70 | build does not index docs/work, _site, change notes (DOCSPEC R6.7) | imperative; test_index.py | change note |
| R5.7 | docs:72 | index check reports stale generated file (DOCSPEC R6.3) | imperative; test_index.py | |
| R5.8 | docs:74 | note refuses unknown doc, duplicate, multi-line (DOCSPEC R7.1, R7.2) | imperative; test_fold.py | change note |
| R5.9 | docs:76 | fold bumps version once per release, highest change; one row; deletes notes; --dry-run (DOCSPEC R7.3, R7.4) | imperative; test_fold.py | version |
| R5.23 (1st) | docs:78 | After real fold, runs `pending --json`; prints publish steps (settle, refresh, publish, mark-published, commit); never fails fold (DS252) | imperative; test_ds252 | publish, commit |
| R5.9a | docs:80 | `**Version:**` line doc folded in place; both forms refused | imperative; test_dl243 | version |
| R5.10 | docs:82 | docs_check reports layout..docs/work findings; exit 1 on any error (DOCSPEC R8.1) | imperative; test_check.py | |
| R5.11 | docs:84 | Warns stale/missing last_verified, code newer, no diagram; --strict fails (DOCSPEC R8.2) | imperative (warn); test_check.py | |
| R5.11a | docs:86 | T2 uses UTC dates of last non-merge commit; skipped on shallow clone with info line | imperative | merge |
| R5.11b | docs:88 | note sets last_verified to today | imperative; test_dl421_dl422 | change note |
| R5.12 | docs:90 | work guard exits 1 on added docs/work files; strip and summaries serve join (DOCSPEC R10.2, R10.3) | imperative; test_work.py | join |
| R5.13 | docs:92 | Stop hook warns, never blocks; SessionStart adds rule; no-op without docs.json; fail open (DOCSPEC R8.7) | imperative; test_hooks.py | hooks |
| R5.14 | docs:94 | components copies DatePicker/TimePicker/NumberKeypad, no overwrite, adds sections and words (DOCSPEC R15.10) | imperative; test_components.py | |
| R5.15 | docs:96 | Rule UX-56 and raw-inputs guard (DOCSPEC R15.11) | imperative; test_components.py | |
| R5.16 | docs:98 | Generator badge `luismc-docs X.Y.Z` with latest/update/unknown flag; offline; freshness checks ignore it | imperative; test_dl239 | version |
| R5.17 | docs:100 | Default page/surface/ink/line colours; project design.css accents only | imperative; test_dl239 | |
| R5.18 | docs:102 | Font sizes 0.81x original; body 12.96px; root 90% | imperative; test_dl239 | |
| R5.19 | docs:104 | Picker templates compile under strict TS flags and lint (DL331) | imperative; test_dl331 | |
| R5.20 | docs:106 | Install/update window default: UX-62..UX-65, components 35, 36; LayoutCheck at 100/150/200% (DU13) | imperative; test_du13 | |
| R5.23 (2nd) | docs:108 | Lifecycle parts and DS234 guards A-E, LC-22/23/24/30/34 (DOCSPEC R15.22-R15.24) | imperative; test_ds235b | |
| R5.21 (in §6) | docs:112 | Lifecycle schema and starter; LC-1; setup --local-app yes/no (DOCSPEC R15.13, R15.14) | imperative; test_ds235a | |
| R5.22 (in §6) | docs:114 | Words-lint guards LC-2, LC-31 (DOCSPEC R15.15) | imperative; test_ds235a | |
| R5.24 (in §6) | docs:116 | verify blocks DS7, DS8, DS9 (error on release branch, warning on task branch) (DOCSPEC R15.25) | imperative; test_design_system.py | |
| R5.25 (in §6) | docs:118 | Wizard guard `step-bar-more-for-one` (DS244) | imperative; no row in §9 | |
| R5.26 (in §6) | docs:120 | `visuals` prints missing `Proof: UX-n` lines | imperative; test_dl421_dl422 | |
| R5.27 (in §6) | docs:122 | `fold --release RELEASE-n` folds only that release's notes; `--all` folds all (DS274, DL-128) | imperative; test_ds274 | version, change note |
| R6.1 | docs:124 | Stdlib only, Python 3.9+ (DOCSPEC R12.4) | imperative; test_lib.py (partial) | |
| R6.2 | docs:126 | Checks read Markdown/JSON/git/paths; run project command only for generated_reference (DOCSPEC R8.4) | imperative; test_lib.py | |
| §3 (no ID) | docs:52 | `docs-check` runs on every branch gate; hooks only remind | design | gate |
| §8 (no ID) | docs:150-153 | Hooks fail open; gate blocks; docs_check fails closed exit 1; move collision exits 2 | design | |

#### artifacts (version 0.26.0)

| ID | file:line | gist | level | tags |
|---|---|---|---|---|
| R5.1 | artifacts:129 | Feature artifacts plus exactly one Full Progress; first feature creates FP | imperative; test_project_artifacts.py | |
| R5.2 | artifacts:131 | Status stored once in `docs/artifacts/registry.json` | imperative; tests | record |
| R5.3 | artifacts:133 | set-task-status updates registry, renders, writes files in one run | imperative; tests | |
| R5.4 | artifacts:135 | Rejects a status outside "the eight"; names nearest | imperative; test_status_nearest | status names |
| R5.5 | artifacts:137 | Deterministic render | imperative; test_determinism | |
| R5.6 | artifacts:139 | Writing command refuses change that adds finding, not earlier findings | imperative; tests | |
| R5.7 | artifacts:141 | Feature artifact never published; only Full Progress | imperative; tests | publish |
| R5.8 | artifacts:143 | Publish only when owner-visible content changes | imperative; tests | publish |
| R5.9 | artifacts:145 | Daily-limit refusal defers publish until reset; hook does not block | imperative; tests | publish |
| R5.9a | artifacts:147 | mark-deferred local copy; work root order; 60-second auto-refresh; opens once; not with CI or CLAUDE_ARTIFACTS_NO_OPEN | imperative; test_dl246, dl264 | publish |
| R5.10 | artifacts:149 | FP published at least every 60 minutes while work open (Running, Waiting, Needs you) | imperative; tests | publish |
| R5.11 | artifacts:151 | Release Expected = end of last phase; differing `--expected` refused | imperative; tests | Expected |
| R5.11b | artifacts:153 | `--expected` takes DD Mon HH:MM; To do/On hold optional `Not scheduled`; Running/Waiting need one | imperative | Expected |
| R5.11c | artifacts:155 | mark-published stale-copy refusal names steps in order | imperative | publish |
| R5.11a | artifacts:157 | Release number RELEASE-n past ledger and record; phase crosses midnight (DL359) | imperative; test_dl359 | release |
| R5.11d | artifacts:159 | design.css checked against accents contract (minus page/surface/ink/size tokens) (DL259) | imperative | |
| R5.12 | artifacts:161 | Finished feature can be retired; tasks/decisions kept, file/content deleted | imperative; tests | |
| R5.13 | artifacts:163 | promote-to-spec writes feature spec | imperative; tests | |
| R5.14 | artifacts:165 | CI runs section when `.delivery/ci-runs.json` exists (D48) | imperative | CI |
| R5.15 | artifacts:167 | `pending --refresh` renders first (AR67) | imperative | publish |
| R5.16 | artifacts:169 | Phase names agents, join, ci, fix, merge; ci/fix repeat (AR68, DL305) | imperative | phase, join, merge |
| R5.17 | artifacts:171 | Generator badge; default page colours; 0.9x fonts; latest flag not stale (INV-3) (DL239) | imperative; test_dl239 | version |
| R5.17a | artifacts:173 | Every page declares UTF-8 in first 1024 bytes; FP fragment begins with meta charset then title (DL260) | imperative | |
| R5.37a | artifacts:175 | check warns when FP lede names RELEASE-n and a higher one is Live (DL251) | imperative (warn) | release |
| R5.18 | artifacts:177 | Every record write refreshes publish copy; order: refresh, publish, mark-published (AR70) | imperative; test_ar70 | publish |
| R5.19 | artifacts:179 | task-add To do/Running/Built with no rides/release/open release warns, exit 0 (AR70) | imperative (warn); test_ar70 | release |
| R5.20 | artifacts:181 | Settle window `full_progress.settle_sec` default 60; hook says "settling" not block (AR72) | imperative; test_ar72 | publish |
| R5.21 | artifacts:183 | Copy identical to last published not asked for unless hourly or release change | imperative; test_ar72 | publish |
| R5.22 | artifacts:185 | Undated phases anchor to nearest occurrence; >12 h ahead warns (AR74) | imperative; test_ar74 | phase |
| R5.23 | artifacts:187 | `Where it stands` built from record, ~220 chars; in fingerprint (AR77) | imperative; test_ar77 | Expected |
| R5.24 | artifacts:189 | Default Expected by `--type`: agent 15, ci 5, join 10, test 10, docs 15, study 20, release 30, other 30 min; rounded to 5 min (DP7, D2) | imperative; test_artifacts_dp7 | ETA |
| R5.25 | artifacts:191 | Past-Expected open row: hook tells once, non-blocking; Running/Waiting >60 min past due blocks once naming overdue-sweep -> Needs you (DP7, D2) | imperative; tests | ETA, hooks |
| R5.26 | artifacts:193 | Release main unit, PR its carrier; --pr, --release-start, --release-waits-on (DS256) | imperative; test_ds256 | release, carry |
| R5.27 | artifacts:195 | Waiting release never live before deps; sort by Live ETA (DS256) | imperative; test_ds256 | ETA |
| R5.28 | artifacts:197 | Timeline tree geometry: 4px bar, trunk x=22, 18px elbow, <=880 wide, ~52 per row (DS256) | imperative; test_ds256 | |
| R5.29 | artifacts:199 | PR and waits-on from ledger (`<TASK-ID>-integration`) and git; read-only (DL420) | imperative; test_dl420 | train, integration branch |
| R5.30 | artifacts:201 | Release table shown whenever a release open (DL428) | imperative; test_ds256 | |
| R5.31 | artifacts:203 | FP section 0 badge row replaces count tiles (DL429) | imperative; test_dl429 | status names |
| R5.32 | artifacts:205 | "What is happening" <=8 bullets; each active + last 3 Live releases; replaces lede (DL429) | imperative; test_dl429 | |
| R5.33 | artifacts:207 | Badges/bullets read ci-runs.json and ledger, write nothing (DL429) | imperative; test_dl429 | |
| R5.34 | artifacts:209 | CI waste badge: % green, min per merged PR, cancelled min (7 d) (DS258) | imperative; test_ds258 | CI |
| R5.35 | artifacts:211 | Every PR number is a link; https only; target _blank (DS272) | imperative; test_ds272 | |
| R5.36 | artifacts:213 | Manifest `pr_links`; derived from remote.origin.url; render never runs git (DS272) | imperative; test_ds272 | |
| R5.37 | artifacts:215 | Running/Waiting release needs phases or `--no-phases REASON` (>=2 words); warning before 26 Nov 2026 (DS278) | imperative; test_ds278 | phase |
| R5.38 | artifacts:217 | No-phases release = outline diamond; `<time> · no phases` (DS278) | imperative; test_ds278 | |
| R5.39 | artifacts:219 | pending --refresh/render fetch runs via read-only `gh`; stored as `ci_runs`; `CLAUDE_ARTIFACTS_NO_GH=1` skips (DS295) | imperative; test_ds295 | CI, branch name |
| R5.40 | artifacts:221 | Release row shows PR link and runs (name, state, link, UTC start, duration) (DS295) | imperative; test_ds295 | CI |
| R5.41 | artifacts:223 | Task row with PR or pushed `<task-id>-*` branch shows compact runs (DS295) | imperative; test_ds295 | CI, branch name |
| R6.1 | artifacts:227 | Never a git write or writing `gh`; read-only git, `gh pr view`, `gh run list` | imperative; tests | commit/push |
| R6.2 | artifacts:229 | Stdlib only | imperative; no test | |
| R6.3 | artifacts:231 | After-command hook takes task from watched head; <2 s; no-op without manifest | imperative; tests | hooks |
| R6.4 | artifacts:233 | Hooks fail open, exit 0, one stderr line; turn released after three unchanged blocks | imperative; tests | hooks |
| R6.5 | artifacts:235 | No sideways scroll at 360 px | imperative; manual | |
| R6.6 | artifacts:237 | Times in project zone, named | imperative; tests | |
| §6 note | artifacts:239 | "Limit: 200 publishes a day per account... spends at most one per turn" | advice/fact | publish |
| §7 (no ID) | artifacts:253-257 | One script; four hooks incl. before-command (silent); rule delivered at session start, no copy | design | hooks |
| §8 table | artifacts:263-272 | Failure modes: gh skip, fail open, defer on limit, tz fallback, fail closed on finding, U+FFFD refused, atomic edit-content, decisions-migrate warn, ci2/fix2 | design | |
| §10 (no ID) | artifacts:334 | Record default `docs/project`; `.claude/artifacts.json` record_dir wins; else docs/docs.json; old `docs/artifacts` still found (D182, DS219) | design | record |

---

