# DS67 join report

## Step 1: merges (order DS68, DS69, DS70, DS71)
- DS68 ledger: clean.
- DS69 hooks: one conflict, `claude/plugins/delivery/.claude-plugin/plugin.json` (both branches created it). Kept one manifest with a combined description (ledger + recorder + hooks + watcher), version 0.1.0 (the plugin's first release).
- DS70 runner plan and hourly publish: clean.
- DS71 setup wiring: clean (`marketplace.json` already lists `luismc-delivery`; README section present once).

## Step 2: D6a (runner offline)
- `runner_plan.py runners [--once]`: `RunnerGuard` reads `gh api repos/<owner>/<repo>/actions/runners` for the runners listed in `.delivery/config.json` `runners[]`. Offline: ledger event `runner.offline` and the report channel (`runner_plan.report_command`, text in `$DELIVERY_REPORT`) at once; then every `retry_seconds` (300) it runs the `repair` commands, re-reads the status, and only when online re-runs the train CI the outage cancelled or failed (`runner.repair`, `runner.retry`, `runner.online`, `runner.rerun`, `runner.giveup`).
- Integration bug fixed on the way: `runner_plan.py` called the ledger as `record(kind, data, root=)` but `delivery_ledger.record` is `record(root, op, **kw)`; every job/runner write was a silent no-op. `delivery_ledger.record` gained `job` and `runner` upsert ops, the adapter and the test spy use the real signature, and a test now runs against the real ledger file.
- Config schema: `runners[]` (`name`, `repair`) and `runner_plan.retry_seconds|runner_max_retries|report_command` in `delivery-config.json`; docs in tooling README, CONTRACT.md, README, DELIVERYSPEC.

## Step 3: checks and CI wiring
- The `claude/plugins/delivery` unit tests and `tools/test_delivery_hooks.py` were not run by any workflow: added job `delivery-plugin` to spec-lint (in the `delivery` aggregate), the path filter, and a ci_areas rule + test.

## Step 4: versions (folded with change_notes.py)
- luismc-delivery 0.1.0 (new), luismc-project-setup 14.3.0 -> 14.4.0, luismc-artifacts 1.10.0 -> 1.11.0 (plugin and ARTIFACTSPEC).
