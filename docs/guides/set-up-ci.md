---
title: Set up CI for a project
type: how-to
---
# Set up CI for a project

Use this guide to choose where a project's CI runs and to finish the steps only a person can do. The rules are in [delivery spec section 13](../features/delivery/spec.md#13-ci-options).

You need Claude Code open in the project, the `luismc-delivery` plugin installed, and admin rights on the GitHub repository.

## The four options

| Option | Runs on | Costs | Good when |
|---|---|---|---|
| 1. Own runners | Runners you install on any of your machines | No per-minute bill. Your machines and power. | You have a machine that can stay on. |
| 2. GitHub-hosted | GitHub's runners | Per minute, on your GitHub plan | You want no machines to look after. |
| 3. Claude cloud sessions | One cloud session per shard, no Actions | Claude plan usage. No GitHub bill. | Linux only tests, no Windows. |
| 4. Own runners first, fallback after X minutes | Option 1; Option 2 or 3 when a shard waits more than X minutes | Free unless the fallback starts | Your runners are sometimes busy or off. |

Option 3 runs Linux only. If the project tests on Windows, pick another option for Windows. The choice is per OS.

## Steps

### Guided: `/delivery-ci-setup`

1. Run `/delivery-ci-setup`. It has no default at any question.
2. It reads the project: tracks, whether an installer is built, whether a shard table exists.
3. For each OS the product tests on, choose Option 1 to 4.
4. Answer the questions of that option:
   - Option 1: the machines (a name and an OS each), the runner labels, whether ready-PR runs queue one at a time, the memory and CPU ceiling of each machine.
   - Option 2: the runner size per OS, whether to use larger runners, an optional monthly minutes cap.
   - Option 3: the repository, the branches to watch, the shard timeout, the name of the variable that holds the token, an optional cap on sessions per day.
   - Option 4: the main (Option 1), the fallback (Option 3, or Option 2 for Windows), X (the setup shows 10 as an example), which runs may use the fallback, and optional caps.
5. It writes `.delivery/config.json`, runs `delivery_ci_install.py install` and `delivery_doctor.py`.
6. It prints the by-hand list for your choice. Do those steps next.
7. To change the choice later, run the command again. It changes the config only and says what the new choice still needs.

### By hand

Do the steps that match your option. The doctor re-checks them.

1. **Runners (Options 1 and 4).** Install the GitHub runner on each machine and register it with the labels the setup printed. The setup prints the commands for each OS. Add a runner on a second machine when a job waits longer than X minutes: one runner per label is the first bottleneck.
2. **Repository variables.** Set the variables the setup prints (for example `CI_RUNS_ON`).
3. **Larger runners (Option 2).** Create them in the organisation settings, if you use them.
4. **Spending limit (Options 2 and 4 with a hosted fallback).** Set a spending limit in GitHub billing. This is the hard stop on money. The plugin caps are a second brake.
5. **Token (Option 3 and a cloud fallback).** Create a fine-grained token with only `commit statuses: write`. Put it in the cloud environment under the variable name you gave. Do not put it in a file.
6. **Ruleset: "Any source".** Required checks are commit statuses. In the repository ruleset, set each required check to accept **Any source**. The doctor cannot see or change this. If you skip it, the checks stay missing.
7. **Cloud access (Option 3 and a cloud fallback).** Give the cloud sessions access to the repository.
8. Run `python3 claude/plugins/delivery/scripts/delivery_doctor.py` and fix what it names.

## Good to know

- **A fallback can start late when nobody is watching.** The fallback is started by the CI watch of the session that opened the pull request. If no session is open, an hourly routine starts it, so it can start up to an hour after X.
- **Caps are optional.** The setup offers them and explains the risk. It does not refuse a fallback without caps.
- **The first claim wins.** If the main runner frees up while the fallback runs, the fallback finishes. Nothing is pre-empted, and only one status is posted.
- **Windows.** Cloud sessions cannot run Windows tests. Use Option 1, or Option 2 for the small Windows-only set.
- **A Linux-built installer** is a CI check only. The shipped installer is built on Windows.

## Check it worked

1. The doctor's `ci` check passes.
2. Open a pull request. Each required context shows a status.
3. Stop the main runner, wait X minutes (Option 4). The fallback posts the status.
