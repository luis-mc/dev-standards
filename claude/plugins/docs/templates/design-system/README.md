# The design system: how it is kept

This folder is the **only home of the project's UX rules, tokens, components and words** (DOCSPEC R11.2, R11.3). This page holds only the rules for keeping it. It holds nothing of any version's content. A feature spec shows its screens and cites rules by ID; it never copies them.

## The folders

- **Numbered version folders `v1`, `v2` ...**: `v` and a whole number from 1, raised by one only when the **owner** approves a new version. No gaps.
- **One draft folder, `next-version`**: the version being written.
- **The highest numbered folder is the version every app follows** and the guard tests enforce. Until `v1` exists, the guards read `next-version`.
- `approvals.json`: the recorded owner approvals (who, when, where) and a digest of each approved version. Written only by `design_system.py`.
- Nothing else lives here.

## What every version folder holds

- `README.md`: the status (draft, or approved with the approval line) and what the version is.
- `CHANGES.md`: the change list from the version before, one entry per change (`- C1: what changed (file; source)`).
- `ux-rules.md`: numbered rules with IDs (`UX-1` ...); each rule names the guard that proves it.
- `components.md`: numbered sections, one per shared component (export path, what it is for, guard).
- `tokens.md`: colour, type and spacing tokens, the only place a value is given.
- `content.md`: the words users see (labels, messages) and the retired words (DOCSPEC R11.3).
- `review-visuals/index.html`: an offline gallery of the version that the owner reviews, built by `design_system.py visuals`; it loads nothing from the network.
- **Each folder is self-contained.** No file is shared between versions; a version links only inside its folder.

## Who approves, and how

- **Only the owner approves a version**, and its implementation. Nobody else, and no script, does.
- The approval is recorded by `design_system.py promote --approved-by ... --approved-on ... --evidence ...`: it needs all three.
- A numbered folder is **read-only once approved**; the digest in `approvals.json` and the guard tests flag any edit. Two one-time additions are allowed afterwards: `audit/` (what each app must change) and `visual/` (real screenshots once the implementation is live).
- **Every change, even a typo, goes into `next-version`.**

## Order of work

1. Apps follow the **current** (highest numbered) version.
2. UI work for a new version starts only after the owner approves the version and an audit has shown what changes in each app, and the owner approves that implementation (`design_system.py approve-implementation`).
3. UI bug fixes that restore what the current version already promises are allowed at any time.
4. A UI PR body states which version and which sections it follows.
5. Code and comments cite rules by ID without a version or a path (`design system UX-4`), so a new version touches no code.

## Promotion steps

1. Write the change into `next-version`, with a `CHANGES.md` entry; rebuild the gallery (`design_system.py visuals`).
2. Show the gallery to the owner. Wait for the approval.
3. `design_system.py promote --approved-by owner --approved-on YYYY-MM-DD --evidence "where it was given"` (dry run), then `--apply`: `next-version` becomes the next `vN`, its approval is recorded, older versions are made read-only, and `next-version` is recreated as a full copy of `vN`.
4. Write the audit for the apps; the owner approves the implementation; then `approve-implementation vN`.

## Tooling

`design_system.py` (the `luismc-docs` plugin) does `init`, `check`, `status`, `visuals`, `promote`, `approve-implementation` and `guards`. The guard tests for the stack sit in the project (`scripts/design/`) and read the enforced version through one helper.
