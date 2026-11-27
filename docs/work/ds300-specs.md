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
| D5 | Watch CI by the head commit's runs | DL-07 (ds:66) | r/ai:21, inv:1600 | Keep DL-07. |
| D6 | Train freeze while the ready PR's CI runs | DL-01 (ds:60) | f/dsp DL6 (:52), inv:1590 | Keep DL-01. |
| D7 | Shared contracts committed before agents start | DL-45 (ds:110) | r/ai:13, inv:1571 | Keep DL-45. |
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
