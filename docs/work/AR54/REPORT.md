# AR54 report (in progress)

Branch: AR54-full-progress-display

## Findings so far
- Bug 1: labels and group headers already use the stored `release` number on main. The drift shows when
  the Item still starts with an older `RELEASE-<n>` lead: the row shows the stored name, then the old lead.
  Fix: a numbered release drops any `RELEASE-<n>` lead from its Item; `check` reports a lead that disagrees.
- Bug 2: not reproduced; the timeline reads each release's own fields. A regression test pins this.
- Bug 3: axis labels are placed every 30 or 60 minutes with no gap test. Fix: thin labels by minimum gap.

Status: NOT READY (work started)
