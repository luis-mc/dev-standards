---
description: Guide a user to a coherent technology stack — language, frameworks, database, host, and providers that work well together — then generate a repository conforming to STACKSPEC, the organization's technology-neutral invariants specification. Also audits an existing repo against those invariants and reports drift by section. Use when the user wants to start a new product, asks "help me pick a stack", "scaffold a conforming repo", "bootstrap a new product", "set up the tech stack", "does this repo conform", "check conformance", or invokes /luismc-project-setup:tech-stack-setup. This skill does NOT build authentication — that is the auth-setup skill, and it only runs if the user asks for it at the end.
---

# Tech stack setup — a guided wizard, then a generator

This skill does two things:

1. **Guides the user to a coherent stack.** Not a menu — a filtered interview
   where every option offered is compatible with everything already chosen, and
   every consequence is stated at the moment of the choice.
2. **Generates a repository** conforming to **`STACKSPEC` 5.1.0**, the binding
   invariants specification at `references/invariants.md`.

## The two halves, and why they are separate

`STACKSPEC` 5.1.0 contains **no technology names**. It specifies properties —
contract-first APIs, atomic enqueue, adapter boundaries, retention and erasure,
consent-gated analytics, three-tier promotion — that hold whether the product is
TypeScript on Vercel or Rust in a container.

The technology knowledge lives in `assets/catalog/`, which is data, not
requirements. Nothing in the catalog is graded. `STACKSPEC §0.2` defines a
fourth requirement level, **`CHOICE`**, precisely for this: a `CHOICE` is
reported as *recorded* or *unrecorded*, never as conforming or violating.

**Read the spec before acting on it.** It is ~1,050 lines. Read the sections a
step actually needs — do not work from this file's summary, and do not generate
against a clause you have not read.

## Scope — what this skill does not do

**It does not build authentication.** `AUTHSPEC` is a separate binding spec owned
by the sibling `auth-setup` skill. Running both in one pass is the behaviour this
split exists to stop: a user asking to "set up the stack" got a full auth stack
they had not asked for and could not review in one sitting.

`AUTHSPEC §2.1` resolves the stack by finding a declared stack document in the
project, and the Stack Profile this skill writes *is* that document. So the
ordering is not a preference — auth-setup has nothing to resolve against until
this skill has finished.

**Phase 9 asks whether to run it. Never start it automatically**, not even if the
user said "set up the whole thing" at the beginning.

## The distribution rule — do not violate it

A product **MUST NOT** contain a copy of the spec (`§2.1`, `§16`). The spec lives
here, versioned with this plugin. A product carries a **Stack Profile** instead:
`assets/stack-profile.md`, deployed to `docs/specs/stack-profile.md`, naming the
spec version it conforms to plus its selections, capability gaps and deviations.

A vendored copy becomes a second, competing authority that no CI check can
compare against the original. The profile's version reference is the only thing
that can go stale detectably.

---

# Mode 1 — The wizard

`STACKSPEC` is prescriptive enough to generate from directly; there is no
template repository.

## Phase 0 — Establish the target, then announce the foundation

Confirm the working directory, that it is a git repo (`git rev-parse
--show-toplevel`; offer `git init` if not), and that it is empty or nearly so.
If it already holds a product, switch to Mode 2 — do not generate over existing
code.

Then **show the fixed foundation and ask nothing about it.** From
`assets/catalog/roles.yaml`, the `fixed:` block:

| Layer | Fixed |
|---|---|
| Repo | Git, monorepo `apps/` + `packages/`, `docs/specs` + `docs/notes` |
| CI | GitHub Actions, path-filtered, twelve required gates (`§13.1`) |
| Promotion | preview per PR, staging on merge, production on release (`§13.2`) |
| Security | gitleaks pre-commit + CI over full history, dependency scanning |
| Contract | One machine-readable contract, authored first, all clients generated from it (`§4.1`) — the *format* is chosen in Phase 3 |
| Secrets | three tiers, one validated config schema, value-free example env |

Everything else is chosen. Say that explicitly — it sets the expectation for the
next eight phases.

## Phase 1 — Profile the product

Six questions, none about technology, from `roles.yaml`'s `profile:` block:
team expertise · cost posture · ops appetite · compliance and residency ·
lock-in tolerance · **does mobile ship**.

Mobile has the largest cascade of the six: it forces generated Swift and Kotlin
clients, push credentials, store declarations, and it makes hypermedia web
approaches cost double. Ask it even when the answer seems obvious.

Two answers are worth reacting to immediately:

- **Compliance is anything but `none`** → the free bundle is eliminated outright.
  Free tiers rarely offer a DPA and often pin no region. Say so now, not later.
- **Lock-in tolerance is "want a clean exit"** → single-vendor bundles are the
  highest-lock-in options in the catalog. Surface the contradiction rather than
  letting both stand.

## Phase 2 — Entry fork

Three ways in, not two:

| Path | What it does |
|---|---|
| **Recommend me a stack** | Derive 2–3 complete candidates from Phase 1 and present them side by side. Most users should take this. |
| **Infrastructure first** | Host constrains language. |
| **Language first** | Language constrains host. |

The two ordered paths are the same solver with a different binding order —
`roles.yaml`'s `entry_paths:` holds both orders.

## Phase 3 — Bind the roles, filtering after every answer

Work the chosen order. For each role:

1. **Filter** candidates against everything already chosen, using the
   `conflicts`, `requires` and `hosting` scores in the catalog files.
2. **Compare** the survivors on the axes that actually decide it — cost band,
   ops burden, lock-in, and fit with what is already chosen. A table, not prose.
3. **Recommend** one, with a reason referencing the Phase 1 profile.
4. **Say why anything was eliminated.** "ElastiCache is VPC-only and you said no
   VPC" is the guidance; silently omitting it is not.

### The cross-constraint that matters most

Server language largely determines viable hosting. From `tech/hosting.yaml`:

- Picking **Vercel or Cloudflare first eliminates Go, Rust and .NET** for the API.
- Picking **Go, Rust or .NET first eliminates them as API hosts** — but **not**
  as web hosts. Offer split hosting (web on an edge platform, API in containers)
  rather than treating "not all one vendor" as a failure. `§4.1`'s generated
  client is the seam and it already has to exist.

### Vendor roles are open, and that is the point

Every provider — database engine and host, cache, storage, mail, error tracking
— is a `CHOICE`. None produces a deviation. Say out loud why this is safe:
**`§3.3` confines each vendor SDK to exactly one adapter module**, which turns
"we picked the wrong provider" into one file. That rule is what earns the
freedom; mention it when the user hesitates over a vendor.

**No role is closed, but four carry a property the candidate must satisfy.** The
spec names no technology anywhere (`§20` makes doing so a defect), so present
these as a bar to clear, not a list to pick from:

| Role | The property (`§`) | What falls out, and why |
|---|---|---|
| Contract format | Maintained generators for every client language (`§4.1`) | Anything without a Swift or Kotlin generator, when mobile ships |
| Mail | Authenticated bounce/complaint feedback into a suppression list (`§8.1`) | Bare SMTP with no event channel — SMTP *plus* a feedback source conforms |
| Push | Device tokens never disclosed outside the `§10.4` register (`§8.3`) | Nothing. A push vendor is priced, not banned — it adds a register entry |
| Analytics | Non-essential events gated on server-side consent at an ingestion point you control (`§10.3`) | Any SDK reporting to a backend you don't control |

The analytics one gets argued with. It is what excludes Vercel Web Analytics,
Cloudflare Web Analytics, CloudWatch RUM, Pinpoint and GA — but on
**architecture, not brand**: an SDK reporting to a vendor backend cannot be
gated on consent state that backend never sees. A vendor offering consent-gated
ingestion under your control passes the clause. Say it that way, because "not
allowed" invites a fight and "here is the bar" does not.

State the consequence too: with first-party collection, `§14`'s field-vitals
budgets need `web-vitals` reporting to your own endpoint, which is real work.

## Phase 4 — Announce the derived decisions

Do not ask these. Compute and state them:

| Derived | From | Source |
|---|---|---|
| Queue substrate | `db_engine` | `tech/data.yaml` → `queue_derivation` |
| Data access + migrations | `language` + `db_engine` | `tech/data.yaml` → engine `data_access` |
| Package manager, task runner, lint, test, boundary check | `language` | `tech/languages.yaml` → `derives` |

**The queue derivation is the one to explain, not just state.** If the engine
supports transactional enqueue, the queue is a table in the product's own
datastore and enqueue happens inside the business transaction. If it does not, an
outbox with a relay is mandatory — and that is a `§18` item 14 capability gap.

Say the thing that is counter-intuitive: **an external queue is not an upgrade.**
Where the engine supports transactional enqueue, moving the queue out *adds* a
sub-processor and reintroduces the dual-write problem that the outbox then has to
solve.

## Phase 5 — Consequence review

Show the complete stack on one screen. Then run the validator:

```
python3 assets/check_stack.py --selection <selections.yaml>
```

It reports **errors** (combinations that cannot be built) and **warnings**
(capability gaps that `STACKSPEC` requires to be recorded). Do not skip it
because the reasoning "already checked" — a wizard that reasons its way to "Go on
Vercel" in a long session is exactly the failure the script exists to make
impossible.

For each warning, capture a one-line reason and the compensating control. These
become `§18` item 14. Pushback rules, from `roles.yaml`:

| Situation | Action |
|---|---|
| Hard conflict | Block. Offer the nearest working alternative. |
| Weakens an invariant | Explain, capture a reason, record it |
| Ordinary tradeoff | State it once, proceed. No ceremony. |

## Phase 6 — Provisioning ledger

For every external service in the stack, ask three things: *do you have an
account?* → *do you have the dev credential?* → *should I provision it now?*

Three outcomes per row: **have it**, **provision now**, **defer with a
placeholder and a TODO**.

**Dev is automatic, production is manual.** This split is deliberate:

- **Dev / preview** — provision freely where a CLI exists (`neonctl projects
  create`, `wrangler r2 bucket create`, `supabase projects create`, `fly secrets
  set`, …). Write values to a git-ignored `.env.local`.
- **Production** — generate the exact commands and have the **user** run them via
  the `!` prefix, so production secrets never enter the transcript. If a value is
  read into a tool call it lands in conversation history and possibly in logs.

Four rules for this phase:

1. **Never write a production secret to the repo, and never echo one into the
   transcript.** `.env.example` gets key names and descriptions only (`§15`).
2. **Verify, don't assume.** After each credential, smoke-test it — a trivial
   query, a cache ping, an upload-then-delete, a send to a sink. A wrong-but-
   present credential fails at 2am instead of now.
3. **Three tiers, so it is a matrix** (`§15`). Dev, staging, production, with
   separate credentials. A single list quietly encourages sharing one.
4. **Resumable.** Write the ledger to `docs/specs/stack-profile.md` item 6 with
   statuses only, never values, so a later run picks up the deferred rows.

Generate `.env.example`, the config-validation schema (`§15`'s "one schema,
validated at startup") and the CI secret list **from the ledger**, so the three
cannot drift.

## Phase 7 — Generate

Build in dependency order. Each step is a precondition of the next:

| Step | Owner |
|---|---|
| 1. Repository skeleton, workspace, CI, hooks, secret scanning — copy `assets/tooling/<track>/` | this skill |
| 2. `core`, then the data module with initial schema and migration runner | this skill |
| 3. `contract` — the OpenAPI document and generators | this skill |
| 4. *(auth)* | **`auth-setup`** — skip entirely |
| 5. `apps/api` — skeleton, health route, error envelope, route-coverage test **harness**, non-auth routes only | split |
| 6. `jobs` + `apps/worker` with `§7.4`'s required job set | this skill |
| 7. Adapters: `mail`, `storage`, `notify`, `observability` | this skill |
| 8. `tokens` and the UI module | this skill |
| 9. `apps/web`, `apps/admin` | this skill |
| 10. `apps/ios`, `apps/android` — whenever wanted | this skill |
| 11. Stack Profile, runbooks, conformance run | this skill |

### The seam is at steps 4 and 5 — do not paper over it

- **Step 4 is entirely `auth-setup`'s.** Do not create the auth module, not even
  an empty one with a README. An empty auth package makes `auth-setup`'s
  preflight see a satisfied requirement that is not.
- **Step 5 splits.** Create the API app, its bootstrap, its health route, its
  error envelope and the `§11.1` route-coverage test **harness**. Leave the auth
  endpoints out. The coverage test over zero auth routes is correct here and
  starts failing usefully the moment `auth-setup` adds routes without
  declarations.
- **Step 7's mail adapter is a dependency of auth**, not of it. Build it here;
  `auth-setup` wires notifications into it.
- **Step 6's job set** is `§7.4`'s. `AUTHSPEC`'s pruners belong to `auth-setup`,
  which adds them to the same jobs module.

**Do not create modules speculatively.** `§2.1`: a shared module MUST NOT exist
before it has a second consumer or a clear adapter role. Generating eleven
packages for a product with one app is a defect.

## Phase 8 — Verify and report

Run Mode 2 against what you generated. A generation that has not been checked is
not finished. Expect and ignore auth-shaped absences — they are the declared gap,
not findings.

Report: what was generated · what was deferred and why · every profile field the
user still has to fill · every open ledger row · the Mode 2 findings.

## Phase 9 — Ask about authentication

Authentication is absent by design. Say so plainly, then **ask**:

> The stack is set up and authentication is not part of it. `auth-setup` builds
> `packages/auth` against `AUTHSPEC`, a separate binding spec. Want to run it
> now, or later?

**Do not start it without an answer**, and do not treat an earlier "set up the
whole thing" as that answer. Two binding specs in one unreviewable pass is the
failure this split exists to prevent. If the user says later, say what to run and
stop.

---

# Mode 2 — Check conformance

`STACKSPEC §19` is the checklist. Until a script implements it, this mode is that
check, performed by reading.

1. **Find the declared standard.** Read `docs/specs/stack-profile.md`. Note the
   `STACKSPEC` version it claims. If it is behind the version in `references/`,
   say so first — every finding is relative to the version the product claims,
   and the delta between versions is itself a finding.

   A profile claiming **4.x or earlier** predates the technology-neutral split.
   Report that its technology clauses no longer exist as requirements, and that
   its recorded vendor deviations are now `CHOICE`s needing recording, not
   approval. That conversion is the main finding for such a product.

   Check the profile's `AUTHSPEC` version too, but do not audit auth here.
   Report only whether the product claims one.

2. **If there is no profile, that is finding number one.** `§16` and `§18` make
   it mandatory. Without it there is no declared engine, no RPO/RTO, no pinning
   decision, no capability-gap record and no deviation record — so most clauses
   cannot even be evaluated. Report it and continue with what is checkable.

3. **Work `§19`'s checklist**, section by section: Repository and layering ·
   Contract · Data · Jobs and integrations · Caching · Clients · Observability ·
   Testing and CI · Configuration and compliance. For each item resolve one of:
   **conforms**, **violates**, **absent**, **not applicable** (with the reason).
   Cite file and line for every violation — a finding without a location is not
   actionable.

4. **Check the structural gates specifically.** These fail silently when absent:
   - layer-boundary check (`§3.2`) and the adapter rule (`§3.3`) — every vendor
     SDK confined to one module
   - route-coverage test exists and runs (`§11.1`) — authorization *and*
     rate-limit declarations. Whether the *auth* routes declare authorization is
     `auth-setup`'s finding, not this skill's
   - contract drift: all generated clients regenerated and committed (`§4.1`)
   - a test suite finding zero tests fails rather than passes (`§11.3`)
   - secret scan covers full history (`§12`)
   - field classification, retention declaration, export inclusion (`§5.7`)
   - data-collection inventory vs. generated artifacts (`§9.7`)

5. **Classify divergence correctly.** This is where Mode 2 most often produces
   false positives, and 5.x changed the rules:

   | Kind | Test | Verdict |
   |---|---|---|
   | `MUST` violated | No waiver in the profile | **violation** |
   | `MUST` waived | Reason + named approver recorded | conforming |
   | `SHOULD` not followed | Reason + named approver recorded | conforming |
   | `SHOULD` not followed | Not recorded | **violation** |
   | `CHOICE` | Recorded in profile item 2 | **conforming — always** |
   | `CHOICE` | Not recorded | **unrecorded**, not a violation |
   | Capability gap | Compensating control in item 14 | conforming |
   | Capability gap | No control recorded | **violation** |

   **A vendor is never a violation.** Postgres vs. MySQL, Sentry vs. Bugsnag,
   Neon vs. RDS, Drizzle vs. Prisma, Vercel vs. Fly — all `CHOICE`s. The only
   question is whether the profile records them. Do not import 4.x's graded
   `SHOULD`s for Neon, Upstash or Vercel Blob; they no longer exist.

   **The tools are also never a violation.** `§13.1` requires twelve gates to run
   and fail the build. It names no tool. A repo on Biome instead of ESLint, or
   `go test` instead of Vitest, conforms perfectly.

6. **Report severity-ranked findings, grouped by section. Edit nothing while
   surveying** — a check that repairs as it goes cannot tell you what the repo
   actually looked like.

7. **Then offer to fix the mechanical findings — opt-in, never automatic.** Some
   violations are decisions (a missing RPO, a layering breach needing code
   moved). Others are absent files this plugin carries. Offer the second kind,
   listed explicitly, as one confirmation:

   - `.gitleaks.toml`, pre-commit hook missing → `§12` secret scanning
   - CI workflow missing or short of `§13.1`'s twelve gates
   - boundary-check config missing → `§3.2` has no enforcement, so the layer
     rules are decaying by default
   - lint, format, test and task-runner configs missing

   Rules for the repair pass:

   - **Diff before replacing.** If the file exists but differs, show the diff and
     ask. An existing CI workflow may carry project-specific jobs a blind
     overwrite destroys; an existing `.gitleaks.toml` may carry allowlist entries
     added for real false positives.
   - **Never touch a conforming file**, even if it differs from the template. The
     template is one way to satisfy a clause, not the only one.
   - **Re-run the check afterwards.** A repair that was not re-verified is a
     claim, not a fix.
   - If the user declines, leave everything untouched and say which findings
     remain open.

---

# The catalog

`assets/catalog/` is the compatibility model. It is data, not requirements —
nothing in it is graded.

| File | Holds |
|---|---|
| `roles.yaml` | The slots, which are asked vs. derived vs. fixed, the Phase 1 profile questions, the two entry orders, the pushback rules |
| `tech/languages.yaml` | The four tracks, their per-track derived foundation, hosting scores |
| `tech/frameworks.yaml` | Web and API frameworks by track; the rich vs. server-rendered distinction |
| `tech/hosting.yaml` | Compute platforms, language scores, VPC and cold-start implications, spec exclusions |
| `tech/data.yaml` | Engines, hosts, the capability matrix, and the queue derivation |
| `tech/services.yaml` | Cache, object storage, mail, error tracking, uptime |
| `bundles.yaml` | Pre-pinned coherent stacks, plus the anti-combinations to block or warn on |

Two habits when using it:

- **`say_out_loud` blocks are not optional.** They exist because the consequence
  is invisible at selection time and expensive later. Read them to the user.
- **Run `check_stack.py --catalog` after editing any of it.** It verifies the
  files agree with each other — that framework tracks name real languages, hosts
  name real engines, every engine answers every declared capability, and bundle
  selections reference technologies that exist.

## Keeping the catalog honest

The catalog carries claims about the world — that Workers have no raw TCP, that
D1 lacks interactive transactions, that PlanetScale discouraged foreign keys.
These go stale. When a claim is load-bearing for a recommendation and you are not
current on it, say so rather than asserting it, and verify before blocking a
user's choice on it.

## The tooling assets

`assets/tooling/<track>/` holds working implementations of `§13.1`'s twelve
gates, one set per track. Copy in Phase 7 step 1 — before any module exists, so
the first commit is already gated.

Three properties every track's templates must preserve, because they exist so an
absent check cannot masquerade as a passing one:

- **A suite that finds no tests fails** (`§11.3`). A mis-globbed suite must not
  report green over zero tests.
- **The codegen drift check regenerates then diffs**, so a stale committed
  artifact cannot satisfy it.
- **The secret scan checks out full history.** At the default clone depth
  gitleaks silently examines one commit and reports clean.

### The tool names are this generator's choice, not the spec's

`STACKSPEC §13.1` requires the twelve gates to run and fail the build. It names
no tool, and it must not start to — `§20` makes a new `MUST` a major version, and
naming a vendor anywhere in the spec is defined there as a defect.

So record the tools in `docs/specs/stack-profile.md`, not here. In Mode 2 that
distinction is the difference between a finding and a false positive.

---

# Editing `STACKSPEC` itself

Not part of using this skill. The spec is maintained in the `dev-standards`
repository, which gates every edit with `tools/spec_check.py` and documents the
process in its README. A product never edits its copy, because it never has one.

Two governance rules worth knowing before proposing a change (`§20`):

- **A new `MUST` is a major version.**
- **Promoting a `CHOICE` to a `SHOULD` or `MUST` is a major version, and naming a
  vendor anywhere in the spec is a defect, not an edit.** Technology belongs in
  the catalog.
