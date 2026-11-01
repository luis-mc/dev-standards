# dev-standards

A toolkit of Claude Code plugins for building software to one set of standards.

This repo publishes **`dev-standards`**, a private Claude Code plugin
marketplace. Install it once per machine. Then use its plugins from any
project: scaffold a new product, write specs before you build, or audit what
already exists. You no longer start from a blank repo and hope you remembered
everything.

## Install (marketplace once per machine, plugins per project)

```bash
claude plugin marketplace add luis-mc/dev-standards   # once per machine
# then, inside each project:
claude plugin install luismc-audits@dev-standards --scope project
claude plugin install luismc-agents@dev-standards --scope project
claude plugin install luismc-specs@dev-standards --scope project
claude plugin install luismc-project-setup@dev-standards --scope project
claude plugin install luismc-artifacts@dev-standards --scope project
claude plugin install luismc-docs@dev-standards --scope project
claude plugin install luismc-delivery@dev-standards --scope project
claude plugin install luismc-transcript-folds@dev-standards --scope project
```

A machine that registered the marketplace under another name uses that name after the `@`.

Plugins install at project scope. Each project turns on only what it uses.
Run the `claude plugin marketplace add` line once per machine. Run the install lines inside each project.

Already have a plugin installed at user scope? Uninstall it with `claude plugin uninstall <name>@dev-standards --scope user`. Then install it with `--scope project` inside each project.

The repo is private. The install uses your existing git/gh credentials. You
configure nothing extra.

Do you have older versions of these plugins installed? Remove them first
(`claude plugin uninstall <old-name>`), then reinstall from the list above.
Claude Code tracks plugins by name, so renamed plugins need a clean install.

---

## `luismc-docs` — one documentation standard for every project

DOCSPEC (`claude/plugins/docs/references/docspec.md`) says where each document lives and how it is kept true. It sets these rules:

- `docs/` is laid out by reader question (overview, features, design-system, architecture, guides, reference, project).
- Each feature has one folder with a front-matter spec.
- A generated `docs/index.html` opens offline. It has search and a feature index by app and topic.
- Each release gets one version, folded from one-line change notes.
- Agent briefs and reports never reach the default branch.

Skills: `docs-setup` (lay out a repo or move an existing one, dry run first), `feature-spec-new`, `docs-index`, `docs-check`, `docs-note`. Hooks remind the agent at session start and at the end of a turn when mapped code changed without docs; the docs gate blocks. The plugin is generic: nothing in it belongs to one project. See the plugin's `README.md`.

---

## `luismc-project-setup` — take a repo from empty to production-ready

Use this plugin first. It has three skills. Run them in order. Together they
turn a blank folder into a repository with a coherent tech stack, working CI,
authentication, and a configured coding agent.

### `/luismc-project-setup:claude-setup`

Configures Claude Code itself, so every session in this repo (or on this
machine) behaves the same way.

Sets up:
- A `CLAUDE.md` with your working conventions
- `.claude/settings.json` — auto-compact window, output style, model split
  (project level by default; you can pick user level or both)
- A status line showing model, context, and rate-limit info
- The Caveman output style
- `.claude/rules/agents-and-integration.md` — how agents are run and work is
  integrated (replaces `model-delegation.md`)
- `.claude/rules/clarifying-questions.md` — gather every clarifying question
  and ask them all at once; written on every install and re-run
- `.claude/rules/delivery-timing.md` — ETA and train-timing rules; every rule
  line in the three rule files ends with `<!-- check: DL-nn -->` / `Q-n`
  naming the DELIVERYSPEC id that enforces it, or `<!-- advice -->`
- `.delivery/config.json` (from `assets/delivery-config.json`, never
  overwritten) and a `.delivery/` line in `.gitignore`; `luismc-delivery` in the
  project's `enabledPlugins`; a user-level `no-tomorrow.mjs` Stop entry offered
  for removal; and a table mapping your memory notes to the rule ids that now
  enforce them (reported only, nothing deleted)
- `.claude/hooks/effort_drift.py` — a SessionStart alias-drift warning
- `enabledPlugins` — turns on all eight plugins for the project, including
  `luismc-transcript-folds` (project target only; other entries are kept, and an
  entry you set to `false` stays)
- `extraKnownMarketplaces.dev-standards` in the project's `.claude/settings.json`
  when it is missing; an existing entry is never overwritten
- On every run, at user level: the two transcript-folds chords (`ctrl+x d`,
  `ctrl+x f`) merged into `~/.claude/keybindings.json`, because keybindings have
  no project scope; an existing binding is never changed, and a chord bound to
  something else is shown as a conflict for you to decide

**Model split:** the main session runs on Opus and does the thinking and
planning. Subagents run on Sonnet and write the code. Every project gets the
split. The skill asks whether to enforce it for all your projects too. Each run
it also asks whether each model should run at medium or high effort. Medium is
preselected for both Opus and the code agents (Sonnet). The skill writes your
answer to the settings and to the rule file. Cloud agents run Opus and have no
per-model entry. They default to medium through a top-level `effortLevel`.

The rule file also carries the integrate-once, deploy-once workflow. It cites
the `scripts/delivery/*` tools that `tech-stack-setup` 12+ generates. At session
start, the alias-drift warning tells you when the model an alias now resolves to
has no saved effort. You can then re-run the skill. Every skill in the
marketplace also pins its own model and effort in its frontmatter, from one
table in `claude-setup/assets/model-profiles.json`.

You choose whether this applies to the current **project**, your **user-level**
`~/.claude/` config, or both. It never overwrites a `CLAUDE.md` you wrote by
hand. It never changes a settings key you already set, so your deliberate
choices stay. The one exception is the two model-split keys. If one holds a
different model, the skill shows it to you as a conflict to resolve. It does not
leave or replace it silently.

### `/luismc-project-setup:tech-stack-setup`

A guided wizard. It helps you choose a technology stack, then generates a
working repository around it: language, framework, database, hosting, and
every third-party provider. It filters the options, so each one it offers is
compatible with what you already picked.

What you get when it finishes generating:

- A monorepo, scaffolded and ready to run
- CI on GitHub Actions — lint, typecheck, tests, and format all gating merges
- Secret scanning, both as a pre-commit hook and in CI
- A dependency-boundary check, so layers can't silently reach past each other
- Contract-first API scaffolding with generated client code
- A job queue with atomic enqueue, so there are no dual-write bugs between your
  database and your queue
- Consent-gated analytics wired to an endpoint you control, not a vendor's
- Three-tier environment promotion (dev → staging → production)

Since `STACKSPEC` 6.0.0 it also generates how work gets delivered. Every branch
runs one gate command. The command writes a result you can verify against the
branch's current head and base. A pre-push hook runs the fast guards. A merge
script joins branches and stops at a conflict it cannot resolve. The ready pull
request runs the only full CI run, end-to-end tests included, and a CI watcher
follows it by commit. The default-branch run that follows skips a tree CI has
already tested.

Since 7.0.0 the gate installs from the lockfile before it checks anything. It
stops at the first failure and gives up after 30 minutes. A merged train's
branches, gate results and worktrees are removed automatically. GitHub keeps only
the newest build artifact of each name (an installer, a bundle, a report).

Since 7.1.0 the gate fetches its base first and runs only the end-to-end specs a
change affects, the pre-push hook compares with the branch a push forks from,
scanner checksums are pinned, runners are a repository setting, and a
default-branch run skips merges that differ only in documentation. Branches add
change notes instead of editing spec versions; the release folds them.

Since 8.0.0 each delivery layer does only its share: a gate result stays valid while the base moves only by docs, lockfile changes widen only when they cannot be tied to a package, the join runs a quick check instead of a second full gate, a train branch is frozen while its ready PR's CI runs, runner problems are warned about, build-artifact workflows run only when their inputs change, each train's release notes carry its delivery log, and a product that ships a packaged program has CI start it and every worker it starts (the one new MUST).

It supports four language tracks: **TypeScript, Go, Rust, and .NET**. Every
vendor choice is yours: Postgres or MySQL, Neon or RDS, Vercel or Fly. The
wizard never tells you which one to pick. It only tells you which ones are
compatible with each other.

It also runs in reverse. Point it at an existing repo and it audits your
current setup section by section. It tells you where the setup conforms and
where it has drifted. It offers to repair what it safely can. It always shows
you the diff first, and it never touches anything that already conforms.

**It does not build authentication.** That is a deliberate, separate step. See
below.

### `/luismc-project-setup:auth-setup`

Builds a complete authentication and authorization stack on top of a repo that
`tech-stack-setup` already generated.

Sets up:
- Sessions, login, and signup flows
- MFA and step-up authentication
- Passkeys and account recovery
- Consent tracking and data-subject rights (access, export, erasure)
- Abuse prevention and rate limiting
- Full audit logging, designed to survive account erasure
- The test suites that prove all of the above holds

This skill refuses to run until you have run `tech-stack-setup`. If you have
not, it tells you what is missing. A project's authentication choices depend
entirely on the stack underneath it, so without that stack there is nothing
reliable to build on.

It can also audit an existing auth implementation against the same standard,
the way `tech-stack-setup` audits the rest of the stack.

---

## `luismc-artifacts` — see what is live, running and waiting without reading code

Keeps a project's status in front of you. It makes one **feature artifact** per
feature and one **full-progress artifact** for the whole project. Each has a
status checklist, written content and a stamp of the last update. A feature
artifact is a standalone HTML file in the repository
(`docs/artifacts/feature-<slug>.html`). It opens by double-click and is never
published. The full-progress artifact is the project's one claude.ai artifact.
It is published once at the end of each turn (claude.ai allows 200 publishes per
account per day), and it links to the feature files as local files.
The plugin generates them from a record in the project's repository
(`docs/artifacts/` in the working tree: a manifest, a task registry, content),
to the binding `ARTIFACTSPEC`. The plugin writes these files and never commits
or pushes them. The project commits when it chooses. Status is typed in one
place, so every view agrees. A deleted full-progress artifact is recreated from
the record without duplicates. The artifacts use the project's own design, found
and confirmed with you, or a default one.

Five skills:

- **`/luismc-artifacts:feature-artifact-new`** — asks the feature, its apps and
  task prefix, finds the project's design, and writes the content and tasks of
  its standalone file.
- **`/luismc-artifacts:full-progress-artifact-new`** — creates the project's one
  full-progress artifact.
- **`/luismc-artifacts:task-add`** — records work as a task before it starts.
- **`/luismc-artifacts:task-status-update`** — changes a status through the
  script; Full Progress is published once, at the end of the turn.
- **`/luismc-artifacts:project-artifact-check`** — checks the artifacts against
  the spec and explains each finding with its requirement ID.

Hooks queue status changes when a pull request is opened, readied or merged,
when CI finishes, and on a production deploy. The end of a turn waits until the
plugin applies those changes and publishes Full Progress. The end of a turn also
asks for a Running task when work started in the background without one. Every
activity is a task, the session's own included. Built means finished but not yet
released. Live means released. The plugin delivers that rule itself at every
session start in any project with a record, so the rule is always current.
Installing creates nothing in a project.
`luismc-project-setup`'s `claude-setup` enables the plugin in every project it
sets up.

---

## `luismc-audits` — a rigorous second opinion on what you've already built

Three focused review skills. Each one reads your code, finds and verifies real
issues, and hands you a severity-ranked report. It never changes code for you.
That is intentional: a human triages and prioritizes the findings before
anything is touched.

- **`/luismc-audits:security-audit`** — reviews authentication, authorization,
  cryptography, and data handling against major security frameworks (NIST,
  FedRAMP, SOC 2, ISO 27001, NIS2). It traces real exploit paths and does not
  flag theoretical ones.
- **`/luismc-audits:performance-audit`** — hunts down slow database queries,
  N+1 patterns, memory leaks, and anything hurting Core Web Vitals. Measured
  or calculated impact backs every finding. None is a guess.
- **`/luismc-audits:compliance-audit`** — maps how personal, health, and
  financial data moves through your app against GDPR, CCPA/CPRA, HIPAA, and
  SOC 2. It verifies that enforcement happens server-side, not just in the
  UI.

Run any of these at any time: on a brand-new project, an inherited codebase, or
right before a release.

---

## `luismc-agents` — a second opinion when a call is genuinely hard

Installs the **`architect`** subagent. It is available in any project once you
install the plugin. Use it for decisions that have no obviously right answer:

- Weighing a real architectural or technology tradeoff
- A second opinion before committing to a risky approach
- Triaging and prioritizing findings from a security, performance, or
  compliance audit — real severity and exploitability, not a tool's default
  rating

It gives you a direct recommendation with its reasoning, not an exhaustive list
of options. It flags decisions that are yours to make (anything that changes
scope, is hard to reverse, or is a business tradeoff) and does not decide them
for you.

---

## `luismc-specs` — think it through before you build it

Two skills that make "write the spec first" practical for anything that touches
more than one file.

### `/luismc-specs:spec-new`

Interviews you about a feature, component, or migration. It asks about scope
boundaries, what data must never be lost, how the feature should fail when a
dependency goes down, and what happens on retries and duplicate requests. Then
it writes a precise, numbered specification to `specs/<feature-name>.md`.

Every requirement in the spec gets a citable ID and a named test that proves it.
Nothing goes in that cannot be verified. The skill stops once it has written the
spec. Implementation happens in a fresh session, so you build against the spec
and not against the options discarded in the interview.

### `/luismc-specs:spec-check`

Validates the numbering and cross-references in any spec, this repo's own
binding specs included. It catches duplicate or out-of-order section numbers,
orphaned subsections, and references that point nowhere. Run it right after you
write a spec, and again after every revision.

---

## `luismc-delivery` — make the delivery rules mechanical

Rules written in a memory note get forgotten. This plugin turns them into
checks. Hooks (Stop, PreToolUse, PostToolUse, SessionStart) and a watcher read
a per-repository ledger, `.delivery/ledger.json`, and enforce trains and CI
(merge on green, never `--auto`, one train in CI at a time), agent launches
(ETA breakdown, concurrency caps, cloud first), owner questions (the
questions wizard, context inside each question), and attribution. The
rules are numbered in
[`docs/architecture/DELIVERYSPEC.md`](docs/architecture/DELIVERYSPEC.md)
(DL-nn, Q-n); the rule files `claude-setup` installs tag each line with the id
that enforces it.

`/luismc-project-setup:claude-setup` enables it for a project, writes
`.delivery/config.json` (caps, work root, time zone, label patterns, ETA
table, outbound deny list, `no_attribution`, `runners[]` with their repair
commands) and git-ignores `.delivery/`. When a CI runner the project uses goes
offline, `runner_plan.py runners` reports it at once, then every 5 minutes
repairs the runner (restart its service or container), re-checks it and only
then re-runs the CI that needed it; every step is in the ledger (D6a). The
plugin is built in `claude/plugins/delivery`.

The config is checked by `delivery_config.py validate` (a JSON Schema in the
plugin; unknown keys warn) and `delivery_doctor.py` self-checks the setup (config,
gh sign-in, time zone, hooks, ledger). From 0.2.0 the watcher obeys the config
(`watcher.push_trains|open_prs|merge_on_green`, `runner_plan.cancel_replaced_runs|
hold_dependabot_during_train|heavy_jobs_yield`) and starts the runner guard
itself, and `enforcement` sets the mode (`block`/`warn`), the block ceiling and an
optional `.delivery/blocks.log`. From 0.3.0 a train is green only when every
`watcher.ci_workflows` run succeeded on the PR head, DL-31 skips measured
durations, and DL-76 (`pr_proven_jobs`) enforces one CI per release. See `claude/plugins/delivery/README.md` and
DELIVERYSPEC section 6.

## `luismc-transcript-folds` — keep long diffs and commands from flooding the transcript

Folds the transcript to one line per change. It draws a diff of more than a few
lines as `» path:line (+added −removed)`. It draws a finished shell command as a
single row with its outcome. A band above the prompt shows the two switches and a
tally of files and lines changed this session. `claude-setup` enables the plugin
in the project and binds its chords for you.

- **Chords:** `ctrl+x d` toggles folded diffs, `ctrl+x f` toggles folded commands.
- **Slash commands:** `/fold-diffs` and `/fold-commands` flip the same two switches.
- **Settings** (under `/config`): `foldAbove` (default 5; diffs with this many
  changed lines or fewer are drawn in full), `marker` (starts each folded line;
  default `»`), `compactCounts` (put the counts on the tool call's own row).

## The two standards behind `project-setup`

`tech-stack-setup` and `auth-setup` do not improvise. They build against two
binding, versioned specifications:

- **`STACKSPEC`** — the technology-neutral shape every generated repo must
  have: contract-first APIs, safe queueing, proper retention and erasure,
  consent-gated analytics, and more. It names no vendor and no framework. It
  names only properties, so it applies equally to TypeScript and Rust.
- **`AUTHSPEC`** — the same idea, applied to authentication and authorization.

Because they specify properties instead of products, your project does not
vendor a copy of either spec. Instead, `tech-stack-setup` writes a **Stack
Profile** (`docs/architecture/stack-profile.md`). It records which spec versions
your project conforms to, plus the vendors and settings you chose. Later runs,
`auth-setup` included, read that file to understand your project. It also makes
"has this drifted from the standard?" a question with an answer, not a guess.

---

## One-time setup for this repo itself

This repository has its own secret scanning, separate from anything it
generates for other projects. After you clone it, activate the pre-commit hook
once:

```bash
git config core.hooksPath .githooks
```

Without this step, CI still catches secrets. It catches them after they are
pushed, not before they are committed.
