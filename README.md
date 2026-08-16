# dev-standards

Your personal toolkit for building software the right way, every time.

This repo publishes **`luismc-dev-tools`** — a private Claude Code plugin
marketplace. Install it once per machine, then reach for its plugins from
any project: to scaffold a new product on solid foundations, to write specs
before you build, or to run a rigorous audit against what already exists.
No more starting from a blank repo and hoping you remembered everything.

## Install (once per machine)

```bash
claude plugin marketplace add luis-mc/dev-standards
claude plugin install luismc-audits@luismc-dev-tools
claude plugin install luismc-agents@luismc-dev-tools
claude plugin install luismc-specs@luismc-dev-tools
claude plugin install luismc-project-setup@luismc-dev-tools
```

Private repo — this uses your existing git/gh credentials, nothing extra to
configure.

Already have older versions of these plugins installed? Remove them first
(`claude plugin uninstall <old-name>`), then reinstall from the list above —
Claude Code tracks plugins by name, so renamed ones need a clean install.

---

## `luismc-project-setup` — take a repo from empty to production-ready

The plugin you reach for first. Three skills, meant to be run in order, that
turn a blank folder into a repository with a coherent tech stack, working CI,
authentication, and a properly configured coding agent.

### `/luismc-project-setup:claude-setup`

Configures Claude Code itself so every session in this repo (or on this
machine) behaves consistently.

Sets up:
- A `CLAUDE.md` with your working conventions
- `.claude/settings.json` — auto-compact window, output style
- A status line showing model, context, and rate-limit info
- The Caveman output style

You choose whether this applies to the current **project**, your **user-level**
`~/.claude/` config, or both. It never overwrites a `CLAUDE.md` you've already
written by hand, and never changes a settings key you've already set — your
deliberate choices are always left alone.

### `/luismc-project-setup:tech-stack-setup`

A guided wizard that helps you choose a technology stack, then generates a
working repository around it — language, framework, database, hosting, and
every third-party provider, all filtered so every option offered is
compatible with what you've already picked.

What you get, once it's done generating:

- A monorepo, scaffolded and ready to run
- CI on GitHub Actions — lint, typecheck, tests, and format all gating merges
- Secret scanning, both as a pre-commit hook and in CI
- A dependency-boundary check, so layers can't silently reach past each other
- Contract-first API scaffolding with generated client code
- A job queue with atomic enqueue — no dual-write bugs between your database
  and your queue
- Consent-gated analytics wired to an endpoint you control, not a vendor's
- Three-tier environment promotion (dev → staging → production)

Supports four language tracks: **TypeScript, Go, Rust, and .NET**. Every
vendor choice — Postgres or MySQL, Neon or RDS, Vercel or Fly — is yours;
the wizard never tells you which one to pick, only which ones are compatible
with each other.

It also runs in reverse: point it at an existing repo and it audits your
current setup section by section, telling you exactly where it conforms,
where it's drifted, and offers to repair what it safely can — always showing
you the diff first, and never touching anything that already conforms.

**It does not build authentication.** That's a deliberate, separate step —
see below.

### `/luismc-project-setup:auth-setup`

Builds a complete authentication and authorization stack on top of a repo
`tech-stack-setup` already generated.

Sets up:
- Sessions, login, and signup flows
- MFA and step-up authentication
- Passkeys and account recovery
- Consent tracking and data-subject rights (access, export, erasure)
- Abuse prevention and rate limiting
- Full audit logging — designed to survive account erasure
- The test suites that prove all of the above actually holds

This skill refuses to run until `tech-stack-setup` has been run first, and
tells you exactly what's missing if it hasn't — a project's authentication
choices depend entirely on the stack underneath it, so there's nothing
reliable to build on otherwise.

It can also audit an existing auth implementation against the same standard,
the same way `tech-stack-setup` audits the rest of the stack.

---

## `luismc-audits` — a rigorous second opinion on what you've already built

Three focused review skills. Each one reads your code, finds and verifies
real issues, and hands you a severity-ranked report — it never changes code
for you. That's intentional: findings get triaged and prioritized by a human
before anything is touched.

- **`/luismc-audits:security-audit`** — reviews authentication, authorization,
  cryptography, and data handling against major security frameworks (NIST,
  FedRAMP, SOC 2, ISO 27001, NIS2). Traces real exploit paths rather than
  flagging theoretical ones.
- **`/luismc-audits:performance-audit`** — hunts down slow database queries,
  N+1 patterns, memory leaks, and anything hurting Core Web Vitals. Every
  finding is backed by measured or calculated impact, not a guess.
- **`/luismc-audits:compliance-audit`** — maps how personal, health, and
  financial data moves through your app against GDPR, CCPA/CPRA, HIPAA, and
  SOC 2. Verifies enforcement actually happens server-side, not just in the
  UI.

Run any of these any time — on a brand-new project, an inherited codebase, or
right before a release.

---

## `luismc-agents` — a second opinion when a call is genuinely hard

Installs the **`architect`** subagent, available in any project once the
plugin is installed. Bring it in for the decisions that don't have an
obviously right answer:

- Weighing a real architectural or technology tradeoff
- A second opinion before committing to a risky approach
- Triaging and prioritizing findings from a security, performance, or
  compliance audit — real severity and exploitability, not a tool's default
  rating

It gives you a direct recommendation with its reasoning, not an exhaustive
list of options — and it flags decisions that are really yours to make
(anything that changes scope, is hard to reverse, or is a business tradeoff)
rather than deciding them for you.

---

## `luismc-specs` — think it through before you build it

Two skills that make "write the spec first" actually practical, for anything
that touches more than one file.

### `/luismc-specs:spec-new`

Interviews you about a feature, component, or migration — scope boundaries,
what data must never be lost, how it should fail when a dependency goes down,
what happens on retries and duplicate requests — then writes a precise,
numbered specification to `specs/<feature-name>.md`.

Every requirement in the spec gets a citable ID and a named test that proves
it. Nothing goes in that can't be verified. The skill deliberately stops once
the spec is written — implementation happens in a fresh session, so the spec
gets built against, not the discarded options from the interview.

### `/luismc-specs:spec-check`

Validates the numbering and cross-references in any spec — this repo's own
binding specs included. Catches duplicate or out-of-order section numbers,
orphaned subsections, and references that point nowhere. Run it right after
writing a spec, and again after every revision.

---

## The two standards behind `project-setup`

`tech-stack-setup` and `auth-setup` aren't improvising — they build against
two binding, versioned specifications:

- **`STACKSPEC`** — the technology-neutral shape every generated repo must
  have: contract-first APIs, safe queueing, proper retention and erasure,
  consent-gated analytics, and more. It names no vendor and no framework, only
  properties, so it applies equally whether you're on TypeScript or Rust.
- **`AUTHSPEC`** — the same idea, applied to authentication and authorization.

Because they specify properties instead of products, your project doesn't
vendor a copy of either spec. Instead, `tech-stack-setup` writes a **Stack
Profile** (`docs/specs/stack-profile.md`) recording which spec versions your
project conforms to, plus the vendors and settings you chose. That file is
what later runs — including `auth-setup` — read to understand your project,
and what makes "has this drifted from the standard?" an answerable question
instead of a guess.

---

## One-time setup for this repo itself

This repository carries its own secret scanning, separate from anything it
generates for other projects. After cloning, activate the pre-commit hook
once:

```bash
git config core.hooksPath .githooks
```

Without this step, secrets are still caught in CI — just after they've
already been pushed, rather than before they're committed.
