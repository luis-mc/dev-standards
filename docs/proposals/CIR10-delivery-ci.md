# Proposal CIR10: what the delivery plugin takes from the CI speed work

Status: proposal for the owner to decide. Nothing is built. Written 2026-11-03 on branch `claude/CIR10-delivery-ci-proposal`.

"The reference product" below is the TypeScript product whose CI was studied (about 13,800 unit and integration tests in 1,770 files, plus 955 Playwright runs of 132 specs). Its numbers are the evidence. Plugin means `luismc-delivery`.

## Short answer

DL15 built the **choice** (three CI options per OS, one shard table, a watcher that reads both workflow runs and commit statuses). It did not build the **speed**. The speed work found seven rules that held up in real runs. Five of them are generic and should become template defaults. One (the shard table) stays per project but the plugin should check it. One (cloud launcher and watcher) is the largest missing piece for option c.

The plan is 8 steps and about 50 agent hours. Each step is small enough to ship alone and says what it proves. Eight owner decisions are in section 5, each with a recommendation.

Two caveats up front:
- The study predicted a cold run of 27.9 minutes. The first measured cold run took 38.9. The plugin should ship **measured** defaults and say which numbers are predictions.
- I could not read the measured page (`09-measured`) or the decision file with D15 to D19 and D28. They are not on any branch this sandbox can fetch. This proposal uses the numbers and decisions given in the task brief. If a number below differs from page 09, page 09 wins.

## 1. What DL15 built and what is missing

| Part | Built by DL15 | Missing |
|---|---|---|
| Choice | Option a (self-hosted runners), b (GitHub-hosted), c (Claude cloud sessions), per OS, no default. `delivery_ci.py set/show/unset`. Spec section 13, R13.1 to R13.9. | A guided setup that asks, installs, and prints the manual steps in one flow (section 3). |
| Files | CI and delivery templates moved into the plugin. `delivery_ci_install.py install/update`. tech-stack-setup calls it. | Template `ci.yml` has no fail-fast order, no one-job suites, no skipped report jobs (section 2). |
| Shard table | One format for all options (`ci-shards.json`, example file). | No balance check, no "every test is in exactly one shard" guard, no helper to cut the table. |
| Cloud runner | Starter `cloud_shard.py`: runs one shard, writes a result JSON, pushes it as a branch. | Pass records so unchanged shards do not rerun (D28). Default result branch prefix is `ci-result`, which a cloud session cannot push (section 2, item 6). |
| Cloud status | Starter `cloud_status.py`: lists heads that need shards, posts commit statuses. | The launcher and the watcher routine are described in R13.5 but not built. A lost shard is never restarted (`shard_timeout_min` is read, nothing acts on it). No cleanup of old result branches. |
| Watcher | `delivery_watch.py` and `ci_watch.py` read workflow runs (a, b) and statuses (c). | Nothing checks that the branch ruleset requires the same names the shards post. |
| Doctor | `ci` check: option has what it needs. | No check of the required-check names, no token test. |

## 2. Learnings to move into the plugin

Each item: the rule, the measured evidence, where it goes. "Measured" means from CI runs of the reference product. "Estimate" means computed, not run.

### 1. Cheap checks first, stop the big suites at the first red (fail-fast order)
- Evidence: 58% of Linux minutes in 14 days went to runs that did not end green. A failed run used 66 minutes on average, and 51 of 69 failed runs failed in the cheap checks (codegen, lint, guard tests, typecheck, unit). Stopping the big suites at the first red would have saved about 2,100 Linux minutes per 14 days (estimate: half of the failed runs stop at minute 5).
- Plugin: template `ci.yml` and the shard table get an order. Cheap shards run first or beside; big shards start only if no cheap shard is red. Every cheap failure is listed (continue mode), not just the first. The nightly full run is not affected.

### 2. One job per OS with suites as steps (one-job suites)
- Evidence: each job hand-over cost 15 to 25 seconds, nine hand-overs in a run. Run 2015: job time 35.4 minutes, wall time 37.9. On the one Linux runner, separate jobs also queue behind each other. The reference run 41602331288 took 31 minutes: 19 of work and 12 of waiting for the single Linux runner.
- Plugin: the ts template offers a "suites in one job" layout with a log group per suite. The required check names stay (see item 5). Risk: one crash fails all checks, so each suite keeps its own marker and result.

### 3. A shard table the project owns, with a guard
- Evidence: the cloud run uses 10 shards (static, two unit, three integration, two e2e, two budget) on 4-CPU, 16 GiB sessions and finishes in about 12 minutes. A guard test fails when a workspace, an integration file or a budget file is in no shard or in two. Without it, a new test silently never runs.
- Plugin: the table format stays (R13.2). New: `shard_check.py` that takes a project-supplied list of "things that must be in a shard" and fails on missing or doubled. `shard_balance.py` already exists in the templates; it should re-cut from the run times and report when a shard drifts more than a set percent.

### 4. Cache by inputs (run what changed, prove the rest)
- Evidence, all measured: unit step 49 seconds instead of 5 to 9 minutes with a warm cache; lint 15 seconds instead of 100; a master push whose tree equals the tested PR head took 2.7 minutes instead of 49; a second run of a release PR that carried earlier results forward took 21 minutes wall instead of about 49.
- Only half was built. Unit, lint and typecheck are cached by inputs. Integration and e2e were not: 13 of the last 14 releases touched one of 15 shared paths, so every group ran 100% (estimate: 6 of 14 would have needed under 20%).
- Plugin: the contract says "full by inputs": every group whose inputs changed runs. `ci_scope.py` and `area_select.py` are already in the templates. New: a guard that fails when a test reads something outside its input list (the reference product already has this for unit tests). The nightly full run stays the safety net.

### 5. Rerun only what failed or changed (D28), and skip report-only jobs (DL16)
- D28 evidence: the cloud shards compute an inputs key (shard id, its steps, git blob ids of its files and what they depend on, the root files every shard reads). A pass recorded with the same key on the same branch means the shard does not run again. Records live on one orphan branch, one file per branch and shard, written with plain git. A rejected push is rebuilt and retried (5 tries, random wait), so parallel shards all land.
- DL16 evidence (estimate, not yet measured): jobs that only report a result another job already produced were skipped, and the secret scan moved to the idle Windows runner so it starts with the run. Expected 23 to 24 minutes for a run that took 31. Not verified: that GitHub counts a job skipped by `if:` as passing for a required check. The fallback is a repository variable that restores the old jobs.
- Plugin: the inputs key and pass records become generic and work for all three options (a local runner can use them too). The report-only skip stays optional, off by default until the one open question above is verified.

### 6. Timing budgets run only in CI, alone
- Evidence: budget tests are timing-sensitive; they must run alone (2.75 minutes) and never beside another suite. A local run records them as skipped, and the gate accepts that record.
- Plugin: the shard table marks a shard `exclusive: true`. The cloud and runner layouts never run another shard on the same box at that time. This already works in the reference product and costs nothing to generalise.
- A related finding for option c: a cloud session's git proxy refuses pushes outside `claude/*`. DL15's default result prefix `ci-result/...` would be refused. The default should be `claude/ci-result` (one branch per result) or one orphan results branch under `claude/`.

### 7. Playwright with 2 workers, an 8.5 GiB container, database and browsers not at once
- Evidence: e2e took 14.3 minutes on 7 workers and 23.7 on 2. The owner chose 2 workers and an 8.5 GiB container for stability. The Postgres suite and the browser suite cannot share the box: 25 minutes beside e2e against 12 alone. Only the cheap suites may run beside a big one.
- Plugin: the template playwright config and the shard table default to 2 workers and say it is a stability choice, not a speed choice. The "big suite alone" rule becomes a shard flag.

### What the measured cold run says
The study predicted 27.9 minutes for a cold run (every input changed). The measured cold run took 38.9. The honest reading is that the plan is right for the usual run (inputs unchanged) and optimistic for the cold run. The plugin should say "cold run about 39 minutes, usual run much less" and keep the prediction out of the defaults until step 7 measures it on a second project.

## 3. Guided setup, per option

The setup asks one question per OS: where should CI run? There is no default. The same command changes the answer later. Setup then writes the files and prints exactly what the user must do by hand.

| | a: self-hosted runners | b: GitHub-hosted runners | c: Claude cloud sessions |
|---|---|---|---|
| What the setup asks | Which machines, which OS, how many runners | Which runner size (default or larger) | Repo, branches to watch, which shards, token variable name |
| Automated | Writes `ci.yml`, `runners` list, runner load gate (DL-79), repair loop | Writes `ci.yml` with `ubuntu-latest` (or a larger label) | Writes shard table, `ci.cloud.*` config, launcher and watcher routine definitions |
| By hand | Install each runner, set labels, add the load-gate hook to the runner's `.env`, restart the service. Windows: execution policy for the service account | Enable Actions, check the plan's included minutes. Larger runners need an org setting | Create a fine-grained token with only "Commit statuses: write" on this repo; put it in the cloud environment under the chosen name; create the routines; switch the ruleset's required checks to "Any source" |
| Speed for a product like the reference | One runner means jobs queue: the measured 31-minute run was 12 minutes of waiting. Two runners per OS remove most of it. Median full release run 49 minutes before the speed work | Jobs run in parallel with no queue. A hosted standard runner is smaller than the 8.5 GiB / 2 worker setup, so e2e needs a larger runner or more shards. Not measured | About 12 minutes with 10 shards (measured). Linux only |
| Cost | No cash cost. Uses the owner's machine and power. The reference project's rule of 85% memory and 60% CPU applies | Billed per minute. The reference product used 11,668 Linux minutes in 14 days before the speed work, 150 minutes per release. Multiply by the current price; I did not look it up | No Actions minutes. Uses cloud session time on the owner's Claude plan. I have no figure for it. Rule: no spend without the owner's approval (see question 6) |
| Weak points | The PC must be on. Cores and memory are shared with the owner's own work | Cost grows with every extra run. Cancelled and failed runs cost the same as green | A lost shard needs a restart rule (not built). Windows cannot run here. Branch protection must accept statuses from a non-Actions source |
| Switch later | `delivery_ci.py set --os linux --option b` then `delivery_ci_install.py update`. Remove the runners by hand. **Do not remove the runners before the ruleset is switched when going to c: every merge blocks** | Same command. Delete the `runs-on` override | Same command. Keep the old checks until the new ones have posted once, then switch the ruleset |

Mixed choices are allowed per OS. A normal result is Linux on cloud sessions and Windows on a self-hosted runner. The watcher already reads both.

### The guided flow, in order
1. Ask per OS (the Questions wizard, all at once, per the rules).
2. Install the files (`install`), never commit.
3. Show the shard table and run the shard check.
4. Print the by-hand list for the chosen options as a checklist.
5. Run the doctor. It reports each by-hand item as done or open. For c it posts one test status to a throwaway sha and reads it back.
6. After the first green head, print the ruleset step.

## 4. What stays per project and what is generic

| Per project (the product writes it) | Generic (the plugin owns it) |
|---|---|
| The shard table: which commands, how many shards, which are exclusive | The table format, the runner, the status poster, the result JSON |
| The test commands (`tests` map) | The order rules (cheap first, big alone) and the fail-fast logic |
| The list of "things that must be in a shard" | The coverage and balance checks |
| The input lists per test group | The inputs key, pass records, carry-forward contract |
| The scope rules (what is a full-run path) | `ci_scope.py` and `area_select.py` |
| The plan step if it needs the project's dependency graph | The plan contract (inputs and outputs) |
| Timing budgets and their values | Running budgets alone, in CI only |
| Worker counts and memory, with the owner's reason | A safe default (2 workers, 8.5 GiB) and the flag names |
| `quarantine.json` (read by the playwright config) | Where it is looked for (open question 8) |

Rule of thumb: if two products would write the same thing, the plugin ships it. If the thing names a workspace, a file or a command of one product, the product keeps it.

## 5. Open questions for the owner

Each has options and a recommendation. Per the rules, these are listed together so you can answer them at once.

1. **Result transport for option c.** Options: (a) one branch per result (what DL15 built); (b) one orphan results branch, one file per branch and shard (what the reference product built after finding that cloud sessions can only push `claude/*`); (c) post only the status, keep no result file. Recommendation: (b), with the prefix under `claude/`. It needs no cleanup rule per sha and parallel pushes already work.
2. **Status token.** Options: (a) fine-grained personal token, repo-scoped, "Commit statuses: write" only; (b) a GitHub App token. Recommendation: (a) now, (b) if more than one person uses it. The token lives only in the cloud environment.
3. **Required checks for option c.** Options: (a) switch the ruleset to "Any source"; (b) keep a tiny Actions job that mirrors the status. Recommendation: (a). (b) puts Actions back into option c, against D17.
4. **Default for fail-fast and one-job suites.** Options: (a) on by default; (b) opt-in. Recommendation: (a) for fail-fast (no downside, the nightly run stays complete), (b) for one-job suites (one crash fails all checks).
5. **Pass records (D28) for options a and b.** Options: (a) option c only; (b) all options, opt-in; (c) all options, on. Recommendation: (b). The key logic is the same; the first projects to use it should choose it.
6. **Cost of option c.** I cannot measure it. Options: (a) run a one-week pilot and read the usage; (b) decide without a figure; (c) skip c. Recommendation: (a), and the setup says "cost not yet known" until the figure is in. This follows the rule that no spend is approved without you.
7. **Skipped report jobs.** Not verified that GitHub counts a skipped job as a pass for a required check. Options: (a) ship it off by default; (b) ship it on with the variable fallback; (c) wait for the reference product's PR to prove it. Recommendation: (c) then (a).
8. **`quarantine.json` and DL rule IDs.** Two open items from DL15. Options for the file: stays with tech-stack-setup, or moves to delivery. Options for rules: new `DL-nn` IDs for the seven learnings, or keep `R13.x`. Recommendation: file stays (the playwright config reads it); give the learnings DL IDs so the Stop hook can check them.

Not a question, but a warning: going from a to c before the ruleset is switched blocks every merge.

## 6. Step plan

Sizes are agent hours, setup plus work plus affected checks. Each step is its own branch and ships alone.

| # | Step | Agent hours | What it proves |
|---|---|---|---|
| 1 | Template defaults: fail-fast order, optional one-job layout, `exclusive` flag, 2 workers and 8.5 GiB defaults | 6 | A fresh project gets the fast layout; `test_delivery_ci` and `test_ci_speedups` still pass |
| 2 | `shard_check.py` (coverage, double entry) and the balance report | 6 | A test added without a shard fails the check; a re-cut keeps shards within the set percent |
| 3 | Inputs key and pass records, generic (port of the reference implementation), plus the no-rerun rule | 8 | Same inputs give the same key; a rejected push retries; a changed root file changes every key |
| 4 | Option c launcher and watcher routines, lost-shard restart, results branch under `claude/`, cleanup | 12 | A killed shard session is restarted; two heads do not cross results; old results are removed |
| 5 | Guided setup flow (ask, install, checklist, switch command) | 8 | Setup for each option ends with a correct by-hand list; switching a to c and back changes only the intended files |
| 6 | Doctor additions: required-check names versus contexts, token round-trip, runner label check | 4 | A mismatch between ruleset and shard contexts is reported before the first merge |
| 7 | Measure on a second project: one cold run and one usual run per option, compared to the predictions | 6 | Whether 38.9 cold / 11 usual hold outside the reference product; replaces predictions with numbers |
| 8 | Spec section 13 update, DL rule IDs, README, change notes (written inside each step; this is the final pass) | 4 | `docs_check.py` clean; the spec and the code agree |
| | **Total** | **54** | |

Order: 1, 2 and 3 can run in parallel (different files). 4 needs 3 (pass records) and the answer to question 1. 5 and 6 need 4. 7 needs 1 to 6. Steps 1 to 3 give value to option a and b users at once and need no owner decision beyond questions 4 and 5.

Not in this plan: any change to the reference product, a Windows cloud option, and any cost beyond what the owner approves.
