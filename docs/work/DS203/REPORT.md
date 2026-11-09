# DS203 report: release docs

## New requirement IDs
- delivery spec, section 5:
  - R5.33 prune workflow list and `--sync-workflow` flags (DL122)
  - R5.34 DL-53 accepts Git Bash and WSL worktree paths (DL133)
  - R5.35 postpone warning with an open question (DL136)
  - R5.36 `agent-check`, `agents_done`, stale agents in `show` (DL127)
  - R5.37 `ci_watch.py` ledger root from a worktree (DL132)
  - R5.38 CI result matched by train, PR, branch, sha; train creation (DL138)
  - R5.39 unfiltered run list for other workflows (DL139)
  - R5.40 `join.py` skips a stacked older branch (DL128)
  - R5.41 `join.py --create` (DL129)
  - R5.42 join-interaction note (DL135)
  - R5.43 `pre_pr_docs` step (DL140)
  - R5.44 local integration ahead; `docs/work` conflicts (DL145)
  - R5.45 gate restores `docs/work`; UTF-8 logs and env (DL131, DL134)
  - R5.46 C# build or warning (DL141)
  - R5.47 workflow `needs` guard test (DL147)
  - R5.48 `rust_ci.py` subcommands (DS200)
  - R5.49 rust `smoke.json` and `gate.json` fields (DS200)
  - R5.50 rust workflows (DS201)
  - R5.51 rust doctor check (DS202)
- delivery-speed spec: R5.14 `ci_tool.py tool`; R5.15 `tools_pin.py` and shipped pins, Zig not pinned; R5.16 `scope_map` and step `paths` (DS201). Code list gains the rust scripts.
- project-setup spec: R5.14 stop hook ETA parking (DL124); R5.15 postpone rule line (DL136); R5.16 pre-push node_modules (DL130); R5.17 pre-push hand-over (DL137); R5.18 to R5.20 `check_stack.py` components, warnings, catalog (DS196); R5.21 wizard text (DS197); R5.22 tooling assets (DS198). Code list gains `tools/test_check_stack_rust.py`.
- artifacts spec: R5.15 `pending --refresh` renders first (AR67); R5.16 `--phase` in the status skill (AR68). Code list gains `tools/test_artifacts_ar*.py`.
- New guide `docs/guides/rust-beside-js.md`.
- Change notes: `docs/architecture/changes/DS203-release-docs.md` and `docs/features/{delivery,delivery-speed,project-setup,artifacts}/changes/DS203.md`.

## Not covered (outside my owned files)
- DS193 (`docs_work.py strip --apply` commits `docs/work/` only; exit 1 with the finish command when git refuses). It belongs in `docs/features/docs/spec.md`, which I do not own.
- Branch reports that say NOT READY or left open items: AR67 (spec-lint not finished), DL147 (rust `ci.yml` jobs `verify`/`integration` lack the `needs.decide.result` guard; `tools/test_delivery_ci.py` `IF_COND` needs updating), DS199 (CI cancelled; Zig not pinned), DS200 (needs a delivery-speed note, now present), DS202 (doctor fix strings still name `ci_tool.py ensure zig` / `ensure llvm`; the real commands are `tools_pin.py entry zig ...` and `ci_tool.py tool llvm --exe lld-link`). R5.51 states the behaviour, not those strings.
- DL127: SessionStart check-in could name stale agents (not done).
- DL122 follow-up: the installer could run `--sync-workflow` itself.

## Tests
- `python3 tools/ci_areas.py --branch-advice`: `light: test locally only`.
- `python3 claude/plugins/docs/scripts/docs_check.py`: 3 errors, 2 warnings.
  - G1 (docs-map.json, llms.txt stale): the new guide; generated files are not committed here, the join rebuilds them.
  - W1: this report, expected on a branch.
  - M1 passes.
  - T2 for artifacts and delivery-speed: spec older than code; the release fold handles it.

Branch head SHA: see `git rev-parse origin/DS203-release-docs`.

READY
