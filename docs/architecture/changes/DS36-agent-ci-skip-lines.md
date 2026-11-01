---
spec: docs/features/delivery-speed/spec.md
change: patch
---
agent_ci.py prints one line per skipped branch with its reason, reports a push the pre-push guards refuse as a failing branch with the guard's own lines (and goes on with the next branch), and reads `agent_ci` from `.delivery/config.json` over `ci-scope.json`.
