---
spec: claude/plugins/artifacts/references/artifactspec.md
plugin: claude/plugins/artifacts/.claude-plugin/plugin.json
change: minor
---

Full Progress section 1 becomes a table `Feature artifact | Last updated | Tasks | Where it stands` (R5.6): the new column shows the time each feature page last changed (its stamp, kept in the manifest entry as `updated`, R4.30), and the rows start newest first. The two headers `Feature artifact` and `Last updated` are buttons that sort the rows on the page and reverse on a second click, with an arrow and `aria-sort` (R5.39); the template's script does it and stores nothing. Each feature page shows `Full Progress published: DD Mon HH:MM (<label>)` right under its stamp, linking to Full Progress's URL (R5.38), from the new manifest field `published_at` that `mark-published` sets; recording a publish redraws the feature pages keeping their stamp, so Full Progress does not change and `pending` has nothing to list again. A command that renders features and Full Progress draws the features first (R7.5).
