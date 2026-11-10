---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
DL168: the delivery ledger now records when an agent finished and how long each CI run took. A new script, `delivery_eta.py`, gives the median and p75 from that history. The launch check (DL-30) refuses an agent ETA more than 50 % above the measured p75 when there are at least 5 samples, unless the brief carries an `eta-reason:` line. `delivery_ledger.py show` prints the ETA against the time taken.
