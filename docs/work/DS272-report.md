# DS272 report: pull request links in Full Progress

Branch: `DS272-pr-links`.

Built:
- `claude/plugins/docs/scripts/pr_links.py`: provider table (`github`, `gitlab`, `custom`), setting check, URL builder, anchor helper, remote parser.
- `render_artifacts.py`: the release table, the tree label, the bullet heads and the Carrier PR badge link to the PR. The setting is read from the manifest and passed in; git is never run in the render.
- `project_artifacts.py`: `pr-links` command, `render` derives the setting from `git remote get-url origin` when absent, `check` validates it.
- Spec: ARTIFACTSPEC R5.65, R5.66, D25; feature spec R5.35, R5.36; change notes.
- Tests: `tools/test_artifacts_ds272.py` (14 cases).

Unverified:
- Whether `target="_blank"` opens a new window on a published claude.ai page (sandboxed). The link works as a normal link if not.
- The links were not looked at in a browser.
