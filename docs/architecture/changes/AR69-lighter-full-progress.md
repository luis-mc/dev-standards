---
plugin: claude/plugins/docs/.claude-plugin/plugin.json
change: minor
---

# AR69 lighter Full Progress page

The Full Progress page was 1.84 MB on a project with 1,695 tasks. This change makes it lighter.

- The embedded registry holds only open tasks and the Live or Dropped tasks changed in the last 14 days. It is minified and carries `omitted` and `full_registry` (ARTIFACTSPEC R5.9).
- Live rows older than 14 days are not drawn. One line in Live or built says how many, and where the full list is (R6.3). The Earlier fold is gone.
- Checklist and feature-list cells lose `data-label`. The narrow-box CSS labels each column by position.
- The checker compares the embedded registry with the window, and expects the count line instead of the fold.
