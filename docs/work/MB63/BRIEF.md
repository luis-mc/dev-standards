# MB63 brief and progress log

## Brief (copy)

Task MB63, research for the dev-standards delivery plugin. Branch `MB63-shared-runner-research` from `origin/main`.

Owner request (verbatim): "research into how to make it part of the dev-standard delivery plugin, as an option when user selects to use own runners; if a user own runner is already setup (research how you can detect this) ask if user want to use it in a shared capacity, or if wants to create a new runner".

'It' = one Docker container on the owner's PC with one shared CPU/memory cap, running several GitHub Actions runner agents inside it, one registration per repository (personal GitHub accounts cannot register one runner for many repos; only organisations can).

Run rules: no PR ready/merge/close, no PR or issue comments, no push notifications, no runner/variable/secret/setting changes. One draft PR on dev-standards only. No code change: research plus one design doc. One affected gate (the repo's doc checks). No subagents. No .env files. No proxy probing. No edits to .claude/rules/. No AI attribution in commits or PR body. dev-standards is public: copy no private names, ids, host names, paths or verbatim text from the private project.

Research: (1) runner scope on personal accounts vs organisations, runner groups, limits; (2) multi-agent single-container design; (3) detection of existing own runners, remote and local; (4) security; (5) PC-load rules (85% memory, 60% CPU); (6) fallback when the runner is offline.

Design: detect -> ask shared or new -> plan -> verify; owning skill/script per step, AskUserQuestion texts, files/assets, doctor checks, migration path, open questions.

Output: `docs/research/shared-self-hosted-runners.md` (or the repo's research layout), commit "MB63: research shared self-hosted runner option", one draft PR.

## Progress log

- 2026-11-03: branch created from origin/main; read the delivery spec section 13, /delivery-ci-setup, delivery_ci_setup.py by_hand_items, delivery_doctor.py runner checks.
