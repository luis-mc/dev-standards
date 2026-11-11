DL194 report

Base check: origin/DS228-integration; claude/plugins/delivery/tests/test_dl189_ci_tool_file_name.py exists. OK.

User model found: each pool agent is its own Unix user (useradd --system, own group; pool_agents.py). No shared group. /ci-tools was 1777, so a folder made by one user (0755) was closed to the others.

What changed:
- ci_tool.py: in a world-writable cache root (the pool's /ci-tools), each folder it makes is set to 0777; temp folders get 0777 (mkdtemp makes 0700). Downloads keep a per-process .partial renamed with os.replace; a valid final file is used as is. If a version folder is not writable (made earlier, 0755), one stderr line and the cache moves to ~/.cache/ci-tools (fetch, file/archive/wheel/crate kinds, gitleaks). Outside the pool nothing changes (root not world-writable, or Windows).
- Dockerfile: comment only, names DL194. compose.yaml and pool-add-agent: no change needed.
- Docs: runner-pool spec R5.25, feature note, architecture change note.

Tests:
- python3 -m unittest tests.test_dl194_pool_tool_cache tests.test_dl115_ci_tool tests.test_dl189_ci_tool_file_name tests.test_ds199_tool_fetch (from claude/plugins/delivery): OK
- cd tests; python3 -m unittest test_dl188_doctor_tools: 13 OK
- python3 tools/test_delivery_ci.py --no-mutants: 78 passed, 0 failed
- python3 claude/plugins/docs/scripts/docs_check.py: 0 errors before adding this report (warnings T2 only, not mine); CI shows W1 for this report only.
- spec-lint run 42937801504 (areas=delivery,docs): every job ended. success: areas, change notes enforced and folded, area mapping, CI scripts and templates, artifact pruning, runner plan, setup preflight, packaged-program smoke, branch gate, train cleanup, ledger/recorder/watcher/hooks, docs plugin, delivery scripts umbrella. skipped: change notes, change notes folded, model profiles, shard job, specs/templates/AUTHSPEC, transcript folds, artifact renderer. failed: docs check, only W1 (this docs/work report, expected; stripped before the join).
- Tests simulate the unwritable folder by patching os.access, because the sandbox runs as root.

Session must do after release:
1. Rebuild the pool image (Dockerfile comment only; ci_tool.py ships in the project scripts, so the rebuild is not strictly needed for the fix).
2. Fix the existing volume once, as root in the pool container: chmod -R a+rwX /ci-tools (or remove the cargo-xwin folder). Without it the per-user fallback still keeps jobs green.

Follow-ups: the per-user fallback re-downloads and rebuilds a crate per user until the shared volume is fixed. Existing files made by earlier versions keep their owners; a shared group could replace 0777 later.

Branch head SHA: see git log (prior commit 5a8c5c8, report commit follows).
READY
