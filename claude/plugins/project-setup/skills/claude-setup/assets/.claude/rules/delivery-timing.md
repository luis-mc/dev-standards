## Delivery timing
- Every ETA is a clock time: the run's real start plus the typical duration, with the dependency named ("CI for RELEASE-29, started 14:05, ~25 min, so 14:30"). Never "tomorrow" or "next round" unless computed past midnight. <!-- check: DL-31 -->
- Size an agent ETA from its parts: setup + work (by files touched) + affected checks; state the breakdown in the launch's `delivery:` block and never pad. <!-- check: DL-30 -->
- Join and check the next train while the previous train's CI runs; push it the moment that CI is green. <!-- check: DL-02 -->
- A wait is a gap on the timeline, never a phase; one train is in CI at a time. <!-- check: DL-17 -->
- A train leaves when it is green, at any hour; merge it at once and never leave a green train unmerged. <!-- check: DL-03 -->
- Show times in the owner's zone (`tz` in `.delivery/config.json`), labelled, stamped from the real clock. <!-- check: DL-66 -->
- Say RELEASE-n to the owner, never train labels or branch names. <!-- check: DL-64 -->
