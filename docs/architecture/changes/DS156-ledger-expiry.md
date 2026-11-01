---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
The delivery ledger writer drops finished rows older than a retention window (default 14 days) on every write: closed trains (cleaned, abandoned; not while a hold is active), finished agents (done, empty, failed, stopped, disabled), finished installs (done, failed) and events with an old timestamp. Open rows and rows with no readable timestamp are kept. New optional config key `ledger_retention_days` (whole days, 0 keeps all). Audit F2.

Needed spec sentence (DELIVERYSPEC, not edited here): in the ledger section, "Finished rows (closed trains, finished or disabled agents, finished installs, events) older than `ledger_retention_days` (default 14; 0 keeps all) are dropped when the ledger is written; open rows are never dropped." Optional follow-up: a `ledger_retention_days` accessor in `delivery_config.py` (the ledger reads the key itself).
