---
spec: claude/plugins/project-setup/references/stackspec.md
change: minor
task: DS305
---
STACKSPEC moves to `project-setup/references/stackspec.md`. Auth endpoints send only `Retry-After` (AUTHSPEC R17.7); a one-way hash (AUTHSPEC §5.3) meets the `secret` rule; a new MUST is a major version only when it breaks a conforming product (§20); branches MUST NOT edit a spec's version (DOCSPEC R7.1); §12 owns secret scanning; the §2.1 tree points to DOCSPEC §2; §0.1 is "What changed".
