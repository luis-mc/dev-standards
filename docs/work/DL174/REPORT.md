# DL174 report: runner-pool spec split

## What changed
- New `docs/features/runner-pool/spec.md` (version 0.1.0). It holds 18 requirements, R5.1 to R5.18, in three groups: machine config, slots and load (5.1); pool image and refresh (5.2); pool doctor checks and setup (5.3). Each names its old ID, for example `**R5.9** (was delivery R13.68)`. Text is unchanged except references inside it.
- Delivery spec: R13.60 to R13.71, R13.79, R13.80, R13.84, R13.86, R13.87, R13.88 are one-line pointers that keep the ID. Version line and change log untouched.
- Stay in delivery (not pool): R13.72 to R13.78, R13.81 to R13.83, R13.85, R13.89.
- The checker reads `R<n>.<m>` as belonging to section n, so the new IDs use section 5, not R1.x as the brief example showed. Pointer links name no new ID in the link text for the same reason (it would count as an undefined citation in delivery).
- `docs/docs.json` has no feature-to-code map (only apps, topics, roots). The mapping lives in the `code:` front matter of the new spec, so docs.json is not changed. The delivery front matter was left as is.
- Change notes: `docs/features/runner-pool/changes/DL174.md` (minor), `docs/features/delivery/changes/DL174.md` (patch).

## Citations of moved IDs (unchanged, they resolve through pointers)
- `claude/plugins/delivery/README.md:44`
- `docs/guides/windows-packaging.md:7`
- delivery spec change log rows (0.18.0 to 0.20.2) and failure-mode table
- project records under `docs/project/` (decisions, registry, progress pages)

## Tests
- `python3 claude/plugins/docs/scripts/docs_check.py`: only 4 G1 (stale generated files); no other finding.
- `spec_check.py docs/features/runner-pool/spec.md`: 0 errors, 1 warning (section numbering gaps).
- `spec_check.py docs/features/delivery/spec.md`: 0 errors, 2 warnings (both existed before).
- `gh workflow run spec-lint.yml --ref DL174-runner-pool-spec -f areas=docs,specs` (run 42824970395): failed only on 4 G1 (generated files, allowed) and 1 W1 (this report, allowed). No other finding.

