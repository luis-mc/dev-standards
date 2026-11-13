---
description: Guided CI setup for Options 1 to 4. Asks every question (no defaults), writes .delivery/config.json, installs the CI files, runs the doctor and prints the by-hand list.
---
# /delivery-ci-setup

Set up where CI runs, one OS at a time. You are the guide; the engine is `scripts/delivery_ci_setup.py` in this plugin. Rules for you:

- **No default at any question.** Never pick an answer, never say "the usual is". If the owner has not answered, ask again. An example value is shown only as an example, and it is never taken when the owner is silent.
- Ask one idea per question. Plain, short English.
- Change nothing but the config and the missing templates. Never commit, push or merge.

## 1. Read the project

Run `python3 <plugin>/scripts/delivery_ci_setup.py facts` (the plugin folder is next to this file). It lists the track, whether a shard table and an installer workflow exist, which OS the shards use, and the options already chosen. Say what you found in two lines. Ask for the track if it is null. It is a multi-select: one or more of `ts`, `go`, `rust`, `dotnet`. A project with a Rust workspace and a pnpm workspace picks `rust` and `ts`. With several tracks the installer takes them comma-separated (`--track rust,ts`) and writes one `ci.yml`, one `gate.json` and one `ci-scope.json` that cover all of them. `facts` lists every track it finds in `tracks`. Put the answer in the answers file as `"track": ["rust", "ts"]` (a plain string still works for one track). `delivery_ci_setup.py apply` passes every track to the installer and prints them, so there is no need to run the installer yourself.

## 2. Show the table, then ask per OS

Show this table once:

| Option | Where CI runs | Cost | Needs by hand |
|---|---|---|---|
| 1 | Your own runners, on any machines you have | No per-minute bill; your machines and power | Install a runner on each machine |
| 2 | GitHub-hosted runners | Per minute; the GitHub spending limit is the hard stop | A spending limit, larger runners if used |
| 3 | Claude cloud sessions, Linux only, no Actions, no webhooks | Counts against the Claude plan | A statuses-only token and the ruleset change |

Option 4 is Option 1 plus a fallback after a wait (section 3, "Option 4"). It is not a fourth answer: the OS is answered Option 1, and the fallback questions follow.

For each OS the product tests on (linux, windows, macos), ask: "Which option for <OS>: 1, 2 or 3?" Option 3 is for Linux only.

## 3. Ask each chosen option's own questions

**Option 1.** For each machine that will run a runner: its name and OS. The runner labels. Does a ready PR run queue one at a time (`serial`)? The memory ceiling and the CPU ceiling of each machine, in percent. `wait_min`: how many minutes a job may wait before the owner adds a runner on another machine (10 is only an example). Tell the owner that one runner of a label is the first bottleneck, so a second machine is the first fix.

**Option 2.** The runner label or size per OS (a 2-core hosted runner is too small for a large suite). Whether larger runners are used (they need a paid plan). A monthly minutes cap: offer it, say that without it only GitHub's spending limit stops the bill, and accept "none" as an answer (store `null`). If Windows is hosted: does it run only the small Windows set?

**Option 3.** The repository (OWNER/NAME). The branches to watch. The shard timeout in minutes. The NAME of the environment variable that holds the statuses-only token (never ask for the token). A cap on sessions per day: offer it, accept "none" (store `null`).

**Option 4 (only for an OS answered Option 1; ask whether the owner wants it).** Per such OS, which fallback: `cloud` (Linux only) or `github-hosted`. X: after how many minutes of waiting for a runner the fallback may start (10 is only an example; only runner waits count). Optional caps, each answered by a number or "none" (`null`): `max_shards_per_day` and `max_minutes_per_month` (hosted minutes). Say plainly: without caps nothing but GitHub's spending limit stops the cost, and that limit is a by-hand step. Say that unattended, a fallback may start up to an hour late (the hourly routine is the only watcher when no session is open). For `cloud`: the URL of the routine's API trigger and the NAME of the variable that holds its token. The answers go in the `fallback` section; the engine writes `ci.fallback`. Optional `limits` (`browser_workers`, `integration_workers`, `memory_gib` per option) go to `ci.limits`.

## 3a. Option 1: offer the guided path (D26, D44)

When an OS is answered Option 1 (and the repositories are private), offer: "I can set up shared CI on this machine for you: one pool for Linux jobs, one service per repository for Windows jobs, and one common limit of CI slots. Do you want that, or the by-hand list?" This follows contract section 13: plan first, do every install and configuration you can, one line per step, finish with Done / Left for you / What you can do now.

1. **Detect** (read only): `python3 <plugin>/scripts/delivery_ci_setup.py pool-detect --root <project>`. It lists every repository the owner administers, runner services, runner folders, containers and `.wslconfig`.
2. **Show the plan**: `pool-plan [--repos OWNER/A,OWNER/B] [--windows-repos OWNER/C]`. With no `--repos` it takes the repositories detect found and names them in the plan. The pool cap is measured on this machine; `--total-gib`, `--used-gib`, `--cpus` only override it. It lists every old runner that will be removed (start clean), the machine config, the pool cap (`sizing`, contract 6.4), the repository variables, and what needs the owner. Public repositories are refused. Show it as printed and ask: "Run it for you, or print the steps for you to run?"
3. **Run** only after a yes: `pool-run ... --yes`. Each step prints one line. A deletion (a runner folder, a container, a volume) needs its own yes that names what goes: ask, then pass the exact names in `--yes-delete`. Steps that need an administrator shell are printed for the owner; the engine checks them afterwards.
4. **Windows on the shared machine runner (D269 to D272).** Ask: "Does this project's Windows CI run on the shared machine runner of this PC?" It uses the same CI slots and the same 85% memory / 60% CPU limits as the Linux pool, so there are no separate Windows slots. If yes, add the repository to `--windows-repos` and offer: "I can set up everything for you: a dedicated non-admin account `ci-<name>` for the service, a group `luismc-ci-runners`, the folder rights, the runner download (SHA-256 checked), the registration, the `.env` and the service start. Do you want that?" Then:
   - In an administrator shell, `pool-run --windows-repos OWNER/NAME --yes` does every step. The password is made while it runs and goes only to the runner setup; it is never written down or shown. The registration token is fetched at run time and never stored.
   - Not in an administrator shell, the engine writes one PowerShell script under the machine folder (`setup/windows-runner-<name>.ps1`, no secret in it) and prints one line. Tell the owner to run that line in an administrator PowerShell, then run the setup again to check it.
   - If the repository already has a Windows runner with another name or account (for example a hand-made one as NETWORK SERVICE), the plan replaces it after the new runner is online. That step is a deletion: ask a second yes that names the old runner and pass it in `--yes-delete`. A runner with a running job is never touched.
   - If the plan says the runner pin has no real SHA-256, say so plainly: the download is refused until the pin in `tools.json` holds the published hash.
5. **Windows installers and extra packages.** Ask: "Does this project build Windows installers on Linux?" (WiX under Wine). Suggest yes when the repo has `*.wxs` files. Yes: set `"pool": {"layers": ["windows-packaging"]}` in `.delivery/config.json` (about 1 GB more in the pool image; never in the default image). Say that the pool image comes from the plugin, so a Dockerfile in the repo (for example under `infra/runners/`) never reaches the pool. Extra apt packages go in `.delivery/pool.apt`: one name per line, `#` starts a comment, only letters, digits, `+ - .`. Then run `pool-refresh --yes` (it refuses while a pool runner is busy; `--force` overrides).
6. **Hand over** the engine's three parts as printed: Done, Left for you, What you can do now. If a step failed, say what is done and what is left. Running again is safe: set steps say "already set".

The owner can say no to the guided path. Then print the by-hand list as in section 5.

## 4. Write the answers and run the engine

Write the answers as JSON in the shape documented in the engine's header, to a scratch file, then run:

`python3 <plugin>/scripts/delivery_ci_setup.py apply --answers <file> --root <project>`

Add `--set-variables` only if the owner says yes to running `gh variable set` for them. If the engine refuses, it lists the missing answers: ask them, do not fill them in. The engine writes `.delivery/config.json`, runs `delivery_ci_install.py install`, runs the doctor and prints the numbered by-hand list.

Run the installer (install and update) on the owner's PC, from the installed plugin, not inside a cloud agent: a cloud sandbox refuses to run it from a cloned checkout. A cloud agent can then merge any `.new` files and commit.

## 5. Hand over

Show the numbered by-hand list as printed. Say that some doctor lines fail until the list is done, and that `delivery_doctor.py` re-checks every item. For an item the doctor cannot read (billing, a remote machine, the cloud environment), tell the owner to run `delivery_ci_setup.py confirm <item>` after doing it. Say how to change the choice later: run `/delivery-ci-setup` again; it asks everything again and prints what the new choice still needs. Nothing is removed from machines or GitHub.
