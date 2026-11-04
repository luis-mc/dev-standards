---
title: Run work in cloud routines
type: how-to
---
# Run work in cloud routines

Use this guide when you create a cloud routine (a `RemoteTrigger` routine) that starts an agent session, for example to deliver a task branch. The CI fallback routines in [the fallback guide](ci-fallback-test-run.md) follow the same rules.

## Create it so it cannot miss

A routine with `run_once_at` fires once, at that time. If the time passes while an update call is still in flight, the routine never fires and leaves no run session. Use this order:

1. Create the routine **disabled**, with a `run_once_at` far in the future.
2. Finish every update: sources, `clear_mcp_connections`, and the rest. Do the updates one at a time.
3. Start it with the `run` action.

If you rely on `run_once_at` instead, set it at least **3 minutes** after the last update call returns.

## Check that it started

About **5 minutes** after any launch:

1. Call `list_runs` and look for a run session.
2. Check that the task branch exists on the remote.

If there is no run session, the launch was lost. Start the routine again with the `run` action.

## The create body needs the repository

- A create body needs `job_config.ccr.session_context.sources` with the repository. Without it the session has no push access, and its pushes fail with 403.
- An update **replaces the whole `ccr` object**. Send the full `ccr` (including `session_context.sources`) with every update. A partial `ccr` drops what you left out.

## Node version in the sandbox

The sandbox may ship an older Node than the project asks for. `scripts/delivery/agent_setup.sh` reads `engines.node` from `package.json`. When the active Node major does not satisfy it, the script activates the lowest major that does and prints one line saying so. It prefers volta, fnm or nvm when present. Otherwise it downloads the official tarball and checks its SHA-256 against the official `SHASUMS256.txt`. With no `package.json` or no `engines.node`, it does nothing.
