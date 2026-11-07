---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: patch
---
The pool setup now sets POOL_BROWSERS to chromium when a repository it serves uses Playwright: a playwright.config file at the root or in a workspace package, or @playwright/test or playwright in a package.json. An explicit browsers choice still wins, and the setup prints one line saying why chromium was picked. The doctor fails, naming the repository and the fix, when a served repository uses Playwright and the pool .env has POOL_BROWSERS=none, or when the live image lacks the browser libraries. It warns when Docker cannot be read.
