---
description: Turn on the delivery rules in warn mode for a project that has none. Asks the merge mode, then writes .delivery with safe defaults.
---
# /delivery-onboard

Rules for you:

- Ask the merge mode with AskUserQuestion, no default: `auto` (merge on green) or `manual` (the owner merges).
- Run `python scripts/delivery_onboard.py --merge-mode <answer>` from this plugin, with `--root` set to the project root.
- It writes `.delivery/config.json` (warn mode: nothing is blocked) and `.delivery/ledger.json`. It refuses when a config exists.
- Never commit, push or merge. Tell the owner the files are written and that `delivery_report.py` shows what the rules would have blocked.
- For CI setup after that, point to `/delivery-ci-setup`.
