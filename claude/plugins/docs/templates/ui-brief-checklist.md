<!-- Paste into the UI task brief template and the pull request template. Keep or delete each line to fit the project. -->
## Design system checklist (UI briefs and pull request bodies)

- [ ] Design-system version followed: `v<N>` (the highest numbered folder), and the sections used: `ux-rules`, `components`, `tokens`, `content` (name the rule IDs).
- [ ] For a wizard: I rendered it in first run, running, paused, stopped, failed, done and done after reload. Later steps could not be pressed. Stop was there when the job can stop. Done showed the result. Each button that starts work was disabled and said so while it ran.
- [ ] The step, lock, Stop and busy state come from the shared wizard part. The page passes data only.
- [ ] Shared parts used, by name: `<part>`, `<part>`.
- [ ] No hand-made button, bar, table, tab row, empty box or scroll box. No stylesheet, no `style=` with layout or colour, no class the shared UI package does not define.
- [ ] The enforcement kit is green for what I touched: no-app-CSS scan, DOM layout at 360, 393 and 1300 px, wizard behaviour. No entry was added to a known list; the entries I fixed are removed.
- [ ] Any new word the user sees is in `content`.
- [ ] A change to a rule, token or component went into `next-version` first, with a `CHANGES` entry.

What stays a human check (no test can say it): the page looks like one frame with its siblings; the words read as a person would say them; the next action is the obvious one.
