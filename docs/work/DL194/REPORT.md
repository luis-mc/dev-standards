DL194 report (in progress)

Base: origin/DS228-integration; test_dl189_ci_tool_file_name.py exists. OK.
User model found: each pool agent is its own Unix user (useradd --system, own group, in pool_agents.py). No shared group. /ci-tools was 1777.
Changed: ci_tool.py makes folders 0777 in a world-writable cache root, mkdtemp folders get 0777/0755, version folder not writable falls back to ~/.cache/ci-tools with a stderr line (fetch, kind file/archive/crate, gitleaks). Dockerfile comment only. compose.yaml and pool-add-agent need no change.
Tests: see below.
