---
spec: docs/features/delivery/spec.md
change: patch
---
The merge check (DL-06) reads only the newest run of each workflow on a pull request's head and counts a skipped run as passing; a failed, cancelled or timed-out newest run still blocks the merge.
