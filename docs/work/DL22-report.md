# DL22: CIR10 step S6 (guided /delivery-ci-setup for Options 1 to 3)

Status: built, tests pass, draft PR open.

Base: `origin/main`. `origin/DL17-ci-option-names` held only a start report when I began (no rename), so I used the Option 1 to 3 names from CIR10 section 3 and did not base on it. Rebase on it when it lands; the only overlap is wording.

## What was built
- `claude/plugins/delivery/commands/delivery-ci-setup.md`: the command. It reads the project, shows the option table, asks per OS, asks each option's own questions, never picks an answer. Caps are offered and may be skipped.
- `scripts/delivery_ci_setup.py`: the engine. `facts`, `apply --answers`, `checklist`, `confirm`. `apply` refuses and lists every missing answer (no default; a cap needs an explicit `null`; X has no default, 10 is only an example in the command text). It writes `.delivery/config.json`, runs `delivery_ci_install.py install`, runs the doctor checks, prints the numbered by-hand list and how to change later.
- `by_hand_items(cfg)`: the one list. The printer and the doctor read it.
  - Option 1: runner per machine (commands per OS), load gate per machine, `CI_RUNS_ON`, `CI_SERIAL`, add-a-runner advice for X minutes.
  - Option 2: larger runner per OS, `CI_RUNS_ON`, GitHub spending limit.
  - Option 3: statuses-only token variable, ruleset "Any source", session access.
- Doctor `ci` check: for a config with `ci.guided`, checks each item through `gh` (runners, variables, hosted runners, rulesets) or the environment. Item states: ok, confirmed, open, cannot check. An open or unreadable item fails the check; an unreadable one is closed with `delivery_ci_setup.py confirm ITEM`. A project without `ci.guided` behaves as before.
- Schema: new `ci` keys (`guided`, `confirmed`, `serial`, `wait_min`, `limits`, `hosted`, `cloud.max_sessions_per_day`).
- Spec: R13.10 and R13.11 added after R13.9 (no IDs moved); `commands/*.md` added to the spec's `code:`. Change notes: `docs/features/delivery/changes/DL22.md`, `docs/architecture/changes/DL22-ci-setup-command.md` (names the plugin's `plugin.json`, minor).

## Proof
- `claude/plugins/delivery/tests/test_ci_setup.py` (27 tests, fake `gh` through `DELIVERY_GH`): no default for each option, caps, per option doctor tests (runner missing / offline / missing label, wrong variable, larger runner, spending limit, pinned vs "Any source" ruleset, token variable), and `ListMatchesDoctorTests`: every printed item is named by the doctor when open.
- Whole delivery plugin suite: 387 tests OK. `docs_check`: only W1 (this report under `docs/work/`, expected on a branch). The generated `docs/docs-map.json` goes stale (G1) until the release regenerates it; I did not commit it. With it rebuilt locally the M1 warning for `commands/` is gone.
- `ci_areas.py --branch-advice` says heavy (delivery): `gh workflow run spec-lint.yml --ref DL22-ci-setup-command -f areas=delivery`. See the PR for whether I could start it. I did not run `tools/test_delivery_ci.py` in full (the session guard refuses it locally).

## Limits and notes
- Not measured on a real repository: the `gh api` shapes (runners, hosted-runners, rulesets) follow GitHub's REST docs and the fake; the first real run may need a fix.
- The doctor cannot read billing, a remote machine's load gate, or the cloud environment. Those items need `confirm`.
- `CI_RUNS_ON` is one variable. With several OSes the setup uses the labels of the first self-hosted machine (else the first hosted label). Other OSes' jobs name their own runner in the workflow.
- `delivery_ci.py` is unchanged and still takes `a|b|c` (S1 owns it). The engine accepts 1/2/3, a/b/c and the names.
- Option 4 is not in this command.

## Shared files (likely to conflict with other steps)
- `docs/features/delivery/spec.md` (section 13 and the `code:` list: S1, S11).
- `claude/plugins/delivery/scripts/delivery_doctor.py` (docstring and `check_ci`: S1, S7).
- `claude/plugins/delivery/references/config-schema.json` (`ci` block: S7).
