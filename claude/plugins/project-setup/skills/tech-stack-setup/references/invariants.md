# Product Invariants Specification

**Spec ID:** `STACKSPEC`
**Version:** 5.1.0
**Status:** Binding
**Applies to:** every new product built by this organization

---

## 0. Purpose

This document binds product architecture to **properties**, not to products.

Every requirement here holds whether the product is TypeScript on Vercel with
Postgres, Go on Fly with MySQL, .NET on Azure with SQL Server, or Rust in a
container with anything. If a clause below can only be satisfied by one named
technology, that clause is defective and MUST be raised against this spec.

**Technology selection lives elsewhere.** The concrete stack — language,
frameworks, database engine, host, cache, storage, mail, error tracking — is
chosen per product through the selection catalog that accompanies this spec, and
recorded in the product's Stack Profile (§18). This document does not name
vendors and does not rank them.

### 0.1 What changed in 5.x, and why

**5.1.0 — the last four technology mandates became properties.** 5.0.0 removed
every vendor name but left four clauses that still constrained technology
directly: the contract format had to be OpenAPI, mail had to avoid raw SMTP,
push had to go straight to the platform transports, and no client could carry a
third-party analytics SDK. Each is now stated as the property it was protecting —
generator coverage for every client language, an authenticated bounce-and-
complaint feedback loop, device tokens never held outside the sub-processor
register, and non-essential events gated on server-side consent at an ingestion
point the product controls.

Nothing is weaker. The excluded cases are still excluded, but by consequence
rather than by name, so a technology that satisfies the property qualifies
instead of being ruled out for not being on a list. A product conforming to
5.0.0 conforms to 5.1.0 unchanged, which is why this is a minor version.

Versions 1.x–4.x were an organization-level Stack Profile: they named
PostgreSQL, TypeScript, Next.js, pnpm, Drizzle, Neon, Upstash and Vercel Blob
as requirements. That served a single-stack organization and stopped serving a
multi-stack one.

Three problems forced the split:

1. **Ungraded declaratives.** Clauses like "Drizzle ORM" and "the job queue is a
   table in the product's own database" carried no requirement level at all, so
   a product diverging from them could not be graded as conforming *or*
   violating. §0.2 now closes that hole.
2. **Vendor `SHOULD`s produced meaningless deviation records.** A product on a
   different cloud accumulated deviation entries that recorded a preference, not
   a risk, which devalued the deviation register for the cases that mattered.
3. **The checklist was unusable off the blessed stack.** Most of the 4.x
   conformance checklist tested for Postgres and TypeScript artifacts, so
   auditing a Go product returned noise.

What survives is what was always the point: the properties that make a product
correct, private, operable and changeable. Those are stack-independent, and
this document is now only those.

### 0.2 Requirement levels

| Level | Meaning |
|---|---|
| `MUST` / `MUST NOT` | Absolute. Violation is non-conformant. |
| `SHOULD` / `SHOULD NOT` | Deviation requires a recorded justification and a named approver (§18). |
| `MAY` | Optional. |
| `CHOICE` | Resolved per product by the selection catalog and recorded in the Stack Profile. Never graded, never a deviation. |

`CHOICE` is new in 5.0.0 and exists specifically so that "which database engine"
and "which mail provider" have a defined, checkable status instead of no status.
A conformance check reports a `CHOICE` as **recorded** or **unrecorded** — never
as conforming or violating.

### 0.3 What a product is, structurally

Every product is one system with up to five deployables and up to four client
surfaces:

| Deployable | Role |
|---|---|
| **API** | The only thing that talks to the database. Owns all business logic. |
| **Worker** | Scheduled and queued work. Shares the API's domain code. |
| **Web app** | Customer-facing browser client. |
| **Admin app** | Operator-facing client. |
| **iOS / Android apps** | Native customer-facing clients. |

Mobile MAY be absent. Web MAY be server-rendered from the API deployable rather
than deployed separately. Admin MAY be a route group inside web. The rules here
apply from day one regardless of which surfaces ship, because the expensive
mistakes — untyped API surfaces, business logic in clients, hardcoded strings,
undeclared data collection — cannot be retrofitted cheaply.

### 0.4 Capability requirements, not product requirements

Several clauses below require a *capability* of a chosen technology rather than
a named technology. Where a product's `CHOICE` cannot supply the capability, the
clause states the required compensating control. Two examples of the pattern:

- §7.2 requires enqueue to be atomic with the write that causes it. A datastore
  with multi-statement transactions satisfies this directly; one without MUST
  use an outbox with a relay.
- §5.5 requires point-in-time recovery. A managed engine offering PITR satisfies
  it; one without MUST document an equivalent recovery position and prove it in
  a drill.

The catalog records which technologies supply which capabilities. The wizard
surfaces the compensating control at selection time, so the cost is visible
before the choice is made rather than discovered during an incident.

---

## 1. The governing doctrine: thin clients

**The server owns every business rule.** This is the single most important rule
in this document and everything else is downstream of it.

A product with a browser client, an iOS client and an Android client implements
any client-side rule three times, and those three implementations will diverge.
Divergence in a calculation, an eligibility check, a validation threshold or a
state transition is a correctness bug that appears on one platform only, months
later, and is nearly impossible to reproduce.

Therefore:

- Clients render data, collect input, and call the API. Nothing else.
- Every calculation, eligibility decision, validation rule, state transition,
  authorization check, price, score, threshold and derived value MUST be
  computed server-side and delivered in the response.
- Clients MUST NOT re-derive a value the server already sent. If a screen needs
  a number, the API returns that number.
- Client-side input validation is permitted **only** as a UX affordance and MUST
  be mirrored by authoritative server-side validation. The server MUST NOT trust
  any client-side check.
- Formatting is not business logic. Date, number and currency rendering, string
  interpolation and layout are client concerns.

**Consequence to accept:** more round trips and richer response payloads. Design
endpoints around screens, not around tables — an endpoint SHOULD return
everything one screen needs in one call.

**Escape hatch:** if a genuine requirement cannot be met with a server round trip
(a real-time interaction loop, a hard offline requirement), it MUST be raised as
a deviation (§18) and MUST be accompanied by a shared test-vector fixture set
that every implementation runs against in CI.

**Server-rendered architectures.** A product whose web client is rendered by the
server (server-side templates, hypermedia, or a server-interactive component
model) satisfies this doctrine trivially for web, because there is no second
implementation of anything. The doctrine still binds the moment a second client
surface exists: if mobile ships, the business rules MUST be reachable through
the API contract (§4) and MUST NOT exist only in the rendering path.

---

## 2. Repository

### 2.1 One repository per product

A product is one repository containing every deployable and every shared module.
Splitting a product across repositories before there is a measured reason is a
defect: it converts a compile-time contract into a versioning problem.

The layout below is the canonical shape. Directory names MAY differ where a
track's ecosystem has a strong convention, but the **roles** MUST be present and
separated:

```
<product>/
├── apps/            deployables: api, worker, web, admin, ios, android
├── packages/        shared modules — see §3
├── docs/
│   ├── specs/       binding specifications for this product
│   └── notes/       superseded specs, research, transcripts
├── tools/           codegen, conformance checker, scripts
└── .github/workflows/
```

- Not every product needs every module. A shared module MUST NOT be created
  before it has a second consumer or a clear adapter role (§3.3).
- Internal modules are linked by the ecosystem's workspace mechanism, not by
  published version ranges, and are not published.
- A product MUST NOT contain a copy of this specification. Its Stack Profile
  (§18) names the version it conforms to; a vendored copy silently becomes a
  second, competing authority that no check can compare against the original.

### 2.2 Package management and build orchestration — `CHOICE`

The package manager, workspace mechanism and task runner are resolved by track
and recorded in the Stack Profile. The requirements on whatever is chosen:

- The tool version MUST be pinned in the repository, not inherited from the
  developer's machine.
- The lockfile (or its ecosystem equivalent) MUST be committed, and CI MUST
  install from it in frozen/locked mode. A CI install that can silently resolve a
  different dependency graph than the developer's is not a build.
- A uniform task vocabulary MUST exist across every workspace that can
  meaningfully implement it: `build`, `test`, `lint`, `typecheck`, `codegen`.
  A single root command MUST run each across the whole repository.
- Task dependencies MUST be declared so `codegen` runs before `typecheck` and
  `build`.
- One root command MUST produce every deployable artifact.
- Where the task runner caches, every environment variable a build reads MUST be
  declared in its task configuration, or the cache will serve artifacts built for
  the wrong environment.

### 2.3 Polyglot and native projects

Where a repository contains projects from more than one ecosystem — a native
mobile project, a compiled server alongside a JavaScript web app, or any two
tracks — each project MUST remain natively openable and buildable with its own
toolchain. A developer MUST NOT be required to run another ecosystem's tooling
for day-to-day work in their own project.

To keep one build entry point, each such project MUST expose a thin task shim
that the repository's task runner invokes and that shells out to the native
toolchain. Native dependencies use their own ecosystems.

---

## 3. Layering and adapter boundaries

### 3.1 Declared layers

Dependencies flow in one direction only:

```
   client surfaces (web, admin, ios, android)
                  │  HTTP only, via generated clients
                  ▼
   server deployables (api, worker)
                  │
                  ▼
   service modules (jobs, mail, storage, notify, ...)
                  │
                  ▼
   data module
                  │
                  ▼
   core  ← imports nothing
```

`contract`, `tokens` and `observability` are leaf modules consumable by any
layer. The UI component module depends only on `core`, `contract` and `tokens`.

### 3.2 Hard rules — CI-enforced

- **`core` MUST NOT import** any framework, any I/O, any environment variable,
  any clock, or any module outside `core`. It is pure functions and types. This
  is what makes it testable, reusable by the worker and by seed scripts, and safe
  to reason about.
- The **data module MUST be the only module** that imports the database driver,
  ORM or query builder.
- **No shared module may import a web framework.** A framework request or header
  API reached from inside a shared module is the first step of the erosion this
  rule exists to prevent.
- **Client apps MUST NOT import** the data module, the auth module, `core`, or
  any service module. They reach the system exclusively through the generated
  API client. (`core` is tempting and forbidden — see §1.)
- **Circular module dependencies MUST NOT exist.**

These MUST be enforced by a dependency-graph check that fails the build, not by
review. A documented convention without enforcement decays. The checking tool is
a `CHOICE`; the enforcement is not.

### 3.3 The adapter rule — load-bearing

**Every external service SDK MUST be imported inside exactly one module, and
nowhere else.** Mail, object storage, push transports, the cache client, the
error tracker, and any future vendor each get one adapter module.

This rule carries more weight in 5.0.0 than in any prior version, and the reason
is structural: because every vendor is now a `CHOICE` rather than a `SHOULD`, the
adapter boundary is the *only* thing that keeps a wrong choice cheap. It converts
"we picked the wrong provider" from a refactor into one file.

Consequences that follow, and MUST hold:

- Swapping any vendor in a role MUST be a single adapter implementation plus a
  configuration change. If it is not, the boundary has already leaked.
- No vendor type, error class, or identifier format may appear in a signature
  outside its adapter. The adapter owns the translation to domain types.
- The adapter MUST define the role's degraded behaviour (§8.4), not its callers.

---

## 4. The API contract

### 4.1 Contract-first: one machine-readable contract is the source of truth

The OpenAPI document is **authored and reviewed first**, and everything else
derives from it. A change to the contract is a reviewable diff — that is the
whole point, because every shipped client binary depends on it.

Required pipeline:

1. The contract document is the committed source.
2. **Request and response validation schemas** are generated from the contract
   and used by the API handlers. A handler MUST validate its input against them
   and MUST type its output against them.
3. **A client is generated for every client surface** the product ships, in that
   surface's language, and committed. Generated code MUST be committed so a
   native build never depends on running another ecosystem's codegen.
4. CI MUST regenerate every artifact and fail if the working tree differs.
5. CI MUST run a breaking-change check against the previous released contract.

**Handwritten HTTP calls to product endpoints MUST NOT exist in any client.** If
a client needs an endpoint, the contract gets it first.

The contract format and the generator toolchain are both a `CHOICE`, constrained
by what the pipeline above demands of them:

- The format MUST have a **committed, human-reviewable source document**, and
  MUST have **maintained client generators for every language this product ships
  a client in**. The requirement is not "some schema" but *one schema from which
  clients in unrelated languages are generated* — a format with no generator for
  the product's mobile languages makes step 3 unsatisfiable, and choosing it is
  choosing to hand-write the clients that step 3 forbids.
- Verify generator coverage against the actual client languages **before**
  selecting, not after. This is the check the clause exists for.

OpenAPI is the usual answer because its generator coverage is the broadest; it
is not the required one.

### 4.2 API shape

- The API deployable serves route handlers and its generated reference page. It
  carries no UI.
- Every handler is thin: parse → authorize → call a service → shape response.
  Business logic lives in `core` and the service modules, never in a handler.
- Every response MUST go through one response helper that applies the standard
  error envelope and sets the declared cacheability (§4.5).
- Any route touching the database, cryptography or a platform-restricted API
  MUST run on a runtime that supports it. Constrained edge runtimes MAY be used
  for genuinely stateless routes only.

### 4.3 Versioning

All endpoints live under an explicit version segment: `/v1/…`, `/v2/…`.

- Within a version, changes MUST be backward compatible: fields may be added,
  never removed or retyped; enum values may be added only because clients are
  required to tolerate unknown ones (§9.5); optional stays optional.
- A breaking change means a new version path. Both versions run side by side.
- Every version MUST have a declared **sunset date** at the moment its successor
  ships, published in the contract and returned in `Deprecation` / `Sunset`
  response headers.
- The API MUST record the client version and platform, from a required client
  header, on every request — so retirement is a data-driven decision rather than
  a guess about who is still out there.
- Before a version is retired, remaining traffic MUST be identifiable by client
  version, and those users MUST have been given an upgrade path.
- The server MUST be able to refuse a client below a configured floor with a
  distinct, machine-readable "upgrade required" response that every client
  renders as a blocking screen. This is the emergency lever for a security fix;
  it MUST exist even if never used.

### 4.4 Endpoint conventions

- Resource-oriented paths, plural nouns, no verbs in paths.
- Every list endpoint is paginated — cursor-based where the set can grow
  unboundedly — with a hard maximum page size declared in the contract.
- One error envelope for the whole API, with stable machine-readable codes.
- Every mutating endpoint accepts an idempotency key (§9.4).
- Endpoints are designed per screen, not per table (§1).

### 4.5 Response transport

- **Compression.** Text responses larger than 1 KB MUST be served compressed.
  This MUST be verified, not assumed from platform defaults.
- **Payload budget.** A single response SHOULD stay under 50 KB uncompressed. An
  endpoint that cannot MUST justify it in the contract and MUST be paginated or
  split. Contract examples are the measurement point; CI SHOULD fail when an
  example exceeds the budget.
- **Cacheability is declared per endpoint**, in the contract, as one of:
  - `no-store` — authenticated or principal-specific. **The default.**
  - `private, max-age=N` — per-user but safely reusable by that user's client.
  - `public, s-maxage=N, stale-while-revalidate=M` — shared, non-personal data.
    These MUST be served from a cache or CDN edge on hit, not from a compute
    invocation.

  An endpoint with no declared cacheability defaults to `no-store`.
- **Conditional requests.** Endpoints returning large or slowly-changing
  resources SHOULD support `ETag` + `If-None-Match`. Endpoints where concurrent
  edits are possible MUST support `If-Match` optimistic concurrency and return a
  conflict response rather than silently overwriting.
- Public marketing and informational pages MUST be statically generated, not
  rendered per request.

### 4.6 Rate limiting is universal

Rate limiting is not an authentication concern; it is a property of every
endpoint.

- Every endpoint MUST declare a rate-limit bucket in its contract entry, keyed by
  principal, device, IP or resource as appropriate.
- An endpoint with no declared bucket MUST fail the route-coverage test (§11.1) —
  the same structural gate that enforces authorization declarations.
- Bucket failure mode is declared per bucket: credential and token-issuing
  buckets **fail closed**, everything else **fails open**.
- Limits are configuration, tunable per environment without a code change.
- Responses MUST carry rate-limit headers, and `Retry-After` on rejection.

### 4.7 Error hygiene

- Production responses MUST NOT contain stack traces, driver or ORM error text,
  query fragments, file paths, internal hostnames or dependency version strings.
- Unhandled errors MUST be caught at a single boundary that logs full detail
  server-side with the `correlationId` and returns only a stable error code, a
  safe message, and that correlation id.
- A test MUST assert that a deliberately-triggered internal error returns no
  internal detail. This is verified, not trusted to framework defaults.

---

## 5. Data

The engine, its host and the data-access library are a `CHOICE` (§0.2). Every
rule below binds whatever is chosen. Where a rule requires an engine capability,
the compensating control for engines lacking it is stated.

### 5.1 Access and connections

- The data module is the only module that touches the datastore (§3.2).
- The driver MUST support **real multi-statement transactions** where §5.3
  requires them. A driver that cannot — some HTTP-only and edge-constrained
  drivers — MUST NOT be used for write paths, because the resulting
  read-then-write races are a known source of correctness bugs in credential and
  one-time-token handling.
- **Connection management MUST match the execution model.** Serverless and
  per-request execution models MUST use a pooler or a connection-reuse mechanism
  appropriate to the engine; per-request connection establishment is a defect.
  Long-lived processes MUST declare pool sizing.
- Connection acquisition MUST have a timeout. A request MUST fail fast rather
  than queue indefinitely for a connection.

### 5.2 Schema

- The schema definition MUST be the single source of truth for structure, and
  migrations MUST be derived from or checked against it.
- Every constraint that expresses a domain invariant — referential integrity,
  uniqueness, permitted values — MUST be enforced by the datastore where the
  engine supports it, not only in application code. Where the engine does not
  support a constraint class, the invariant MUST be enforced at a single
  application chokepoint and that gap MUST be recorded in the Stack Profile.
- Every field used as a query predicate, sort key or join key MUST be indexed.
  Partial or filtered indexes for soft-state predicates are required, not
  optional, where the engine supports them.
- Money MUST NOT be stored as floating point. Timestamps MUST be timezone-aware
  or stored as unambiguous instants.

### 5.3 Transactions and consistency

- Any operation writing more than one record across more than one collection or
  table MUST be atomic.
- Read-modify-write sequences MUST use a transaction with appropriate locking, or
  a single conditional statement. "Read, decide in application code, write"
  without either is a race and MUST NOT ship.
- Job enqueue MUST be atomic with the business write it accompanies (§7.2).
- **No external I/O inside an open transaction.** A transaction MUST NOT remain
  open across an HTTP call, a mail or push send, an object-storage operation or
  any other non-datastore await. This rule is load-bearing precisely because
  atomic enqueue is mandatory: enqueue inside the transaction and perform the I/O
  in the handler, never inline.
- Transactions MUST be short. A transaction spanning a long computation holds
  locks that manifest as unexplained latency elsewhere while datastore CPU looks
  healthy.
- Where the engine offers no multi-record atomicity, every operation that would
  require it MUST be restructured so that a single-record write is the commit
  point, with an outbox (§7.2) carrying the rest. This restructuring MUST be
  recorded in the Stack Profile, because it changes how every write path is
  reviewed.

### 5.4 Migrations

- Migrations MUST be generated or authored, committed, reviewed and applied in
  order.
- Every migration MUST be reversible, or explicitly marked irreversible with a
  recorded justification.
- Migrations MUST be applied by a **dedicated, reliable runner** invoked in the
  deploy pipeline, with locking so concurrent deploys cannot race, and clear
  logging of what ran. Ad-hoc migration scripts MUST NOT be used.
- **Destructive changes MUST be split across sequenced deploys**: stop writing →
  deploy → stop reading → deploy → drop. Shipped mobile binaries make this
  mandatory: a binary may still be reading a field weeks after the web app
  stopped.
- Every migration MUST be tested against a non-empty dataset in CI.
- Seed data MUST be idempotent and re-runnable.
- Schema migrations MUST run under a role more privileged than the application's
  own, used by nothing else.

### 5.5 Environments, backups and recovery

- Three persistent tiers — **preview/dev**, **staging**, **production** — with
  separate datastores and separate credentials. Production data MUST NOT be
  copied into lower tiers without irreversible anonymization.
- CI integration tests MUST run against an **ephemeral real instance** of the
  chosen engine, seeded through the migration chain. Not mocks, not an in-memory
  substitute for a different engine, and not a shared long-lived test database.
- **Point-in-time recovery MUST be enabled** with a declared retention window.
  Where the engine or host offers no PITR, the product MUST document its actual
  recovery position and prove it in the drill below.
- Backups MUST be encrypted at rest and access-controlled separately from the
  application's own credentials.
- A **restore drill MUST be performed and recorded at least quarterly**, into an
  isolated environment. An untested backup is not a backup.
- **RPO** and **RTO** MUST be declared in the Stack Profile.
- The restore runbook MUST enforce the erasure **suppression list** — accounts
  erased since the backup was taken MUST NOT return to life on restore.
- Backup retention MUST be bounded and stated, because it is the outer bound on
  the erasure guarantee given to data subjects.

### 5.6 Query discipline

- **Statement timeouts are mandatory** where the engine supports them, set at the
  role or connection level, with documented per-query overrides for the few
  operations that legitimately need longer. Without one, a single slow query pins
  a pooled connection and stalls every unrelated request behind it. Where the
  engine has no equivalent, the data module MUST impose a client-side deadline.
- **Round-trip budget.** A hot-path request handler MUST NOT exceed three
  datastore round trips. Exceeding it requires a recorded justification; each
  extra trip multiplies under concurrency into connection, network and datastore
  CPU pressure.
- **No sequential waterfalls.** Independent queries in one handler MUST execute
  concurrently or be consolidated.
- **No N+1.** One query per item of a collection is a defect; use a batch, a
  join, or a single multi-key query.
- **Push computation down.** Counting, summing, filtering, sorting, grouping and
  deduplication MUST happen in the datastore, not by fetching records into
  application memory to reduce them.
- **Select named fields.** Wildcard selects and full-object-graph fetches MUST
  NOT be used where a subset is consumed downstream.
- Query performance MUST be verified against realistic record counts, not against
  a development dataset with a hundred rows.

### 5.7 Classification, retention and minimization

Every field in the schema MUST carry a classification, declared alongside the
schema and machine-readable:

| Class | Meaning | Consequences |
|---|---|---|
| `public` | Safe to expose to anyone | None |
| `internal` | Non-personal operational data | Not exported, not logged verbatim |
| `pii` | Identifies or relates to a person | Export, erasure, retention, redaction all apply |
| `phi` | Health data | As `pii`, plus access logging |
| `secret` | Credential or key material | Never exported, never logged, encrypted at rest, never returned by any endpoint |

Derived requirements:

- **Encryption at rest** MUST be enabled for the datastore, object storage and
  backups. Fields classified `secret` MUST *additionally* be encrypted at the
  application layer, so a datastore dump alone is not enough.
- **Minimization.** Every field MUST map to a stated purpose in the
  data-collection inventory (§9.7). A field with no purpose MUST NOT be added,
  and an existing one whose purpose has lapsed MUST be dropped. CI MUST
  cross-check the schema against the inventory and fail on an unmapped field.
- **Retention.** Every table or collection MUST declare a retention period. CI
  MUST fail when one has no declaration. An automated job (§7.4) MUST enforce
  each declaration by deleting or irreversibly anonymizing expired records, and
  MUST log what it removed.
- **Export.** Every table containing `pii` or `phi` owned by a principal MUST be
  included in the data export, or explicitly excluded with a recorded reason. A
  test MUST fail when a new table matching that description is neither.
- **Erasure.** The same set defines the erasure inventory. Classification is what
  keeps export, erasure, retention and redaction from drifting apart as the
  schema grows.
- The application MUST connect with a role that has **no update or delete
  privilege on audit records**. Append-only enforced by convention alone is not
  append-only.
- Production datastore credentials MUST NOT be usable from a developer machine
  without an explicit, logged access path.

---

## 6. Caching and ephemeral state

The cache technology is a `CHOICE`. The rules bind whatever is chosen, including
"no cache at all" where a product has none.

- The cache MUST be treated as **ephemeral and untrusted**: anything read back
  MUST be schema-validated before use, and **no data may exist only in the
  cache**.
- Failure policy per use is explicit and declared: rate limiting on credential
  endpoints fails closed; caches fail open.
- Cache keys MUST be namespaced by product and environment.
- Any cache holding user-derived data MUST be enumerable for erasure.
- **Invalidation is explicit.** A write that changes cached data MUST invalidate
  the affected keys directly. TTL expiry is a backstop against missed
  invalidation, never the primary mechanism, and flushing an entire namespace on
  write is not an invalidation strategy.
- Every cache entry MUST have a TTL. An entry with no expiry is a leak.
- Multiple cache operations in one request path MUST be pipelined or issued
  concurrently, not awaited one at a time.
- **In-process caches** — module-level maps, memoization tables, any long-lived
  collection in application memory — MUST declare a maximum size and an eviction
  policy. An unbounded in-memory collection in a long-lived process is a memory
  leak with a delayed fuse.
- Identical queries or lookups repeated within a single request lifecycle MUST be
  de-duplicated by request-scoped memoization.

---

## 7. Jobs and scheduling

### 7.1 The job contract is independent of its substrate

- The **enqueue API, handler registry and payload schemas** MUST be independent
  of both what stores the queue and what triggers the drain. Swapping either MUST
  be a configuration change, never a rewrite of handlers.
- Handlers MUST be registered with a typed payload schema validated on dequeue.
- **At-least-once delivery MUST be assumed. Every handler MUST be idempotent.**
  This is not advisory — every queue substrate double-delivers eventually.
- Claim MUST be a single atomic operation. Claim-then-update in two steps is a
  race.
- Exponential backoff with jitter, a per-job attempt cap, then a dead-letter
  state that alerts.
- Stuck-job recovery: a job claimed beyond a timeout MUST return to pending.
- Every job MUST be individually invocable and observable — start, end, counts,
  duration, failures — and MUST alert on failure.

### 7.2 Enqueue MUST be atomic with the write that causes it

This is the invariant, and it is the one that decides the substrate:

- Where the datastore supports multi-statement transactions, **the queue SHOULD
  live in the product's own datastore** and enqueue happens inside the same
  transaction as the business write. This introduces no additional sub-processor,
  keeps the queue inspectable with ordinary queries, and eliminates the
  dual-write problem outright.
- Where the datastore does not, or where an external queue is chosen for another
  reason, an **outbox MUST be used**: the business write and an outbox record
  commit together, and a relay publishes to the queue afterwards with
  at-least-once semantics. Publishing directly to an external queue from inside
  application code, alongside an uncommitted or separately-committed business
  write, is the dual-write bug and MUST NOT ship.

The substrate is a `CHOICE`; atomicity is not.

### 7.3 Polling cost — where the queue is a polled table

A datastore-backed queue drained on a schedule generates constant baseline query
load and lock churn. That cost is accepted deliberately, and MUST be bounded:

- A **partial or filtered index on the claim predicate is required**. Without it,
  every drain is a full scan over a table that only grows.
- Each drain MUST process a bounded batch sized to complete within its execution
  limit, and MUST return rather than loop until empty.
- A drain that finds nothing MUST back off, so an idle system does not pay full
  polling cost around the clock.
- Completed and dead jobs MUST be pruned on a schedule. The queue MUST NOT
  accumulate terminal records indefinitely.
- Drain frequency, batch size and the resulting steady-state load MUST be
  recorded in the Stack Profile, and queue depth and age MUST be alerted on.

### 7.4 Required jobs

Every product MUST implement at minimum: mail dispatch, push dispatch (where
mobile ships), session and token purge, deletion execution, export expiry, audit
verification, retention pruning, orphan sweep, access review, and any
product-specific scheduled work.

### 7.5 Trigger security

Trigger and drain endpoints MUST be authenticated with a dedicated secret
compared in constant time, and MUST NOT be reachable with a user or operator
session.

### 7.6 Bounded concurrency

- Any fan-out over a collection of unknown or unbounded size MUST be throttled to
  a declared concurrency limit.
- Unbounded parallel dispatch MUST NOT be used. It exhausts connection pools,
  breaches downstream provider rate limits, and converts a routine batch into an
  outage for everything sharing the runtime.
- Long-lived listeners, timers and subscriptions MUST have explicit cleanup. Any
  process registering one MUST unregister it on shutdown or completion.

### 7.7 Live updates

Server-pushed live data updates are outside the default architecture. Clients
poll on foreground and at a declared interval; anything urgent is delivered as a
push notification. Introducing a bidirectional realtime data channel is a
deviation requiring its own design.

Bounded, short-lived streams (a progress indicator, a streamed generation) MAY be
used where the stream lifetime fits inside the execution limit. A persistent
connection used as a **rendering transport** by a server-interactive UI model is
not a realtime data channel for the purposes of this clause and does not require
a deviation — but it does make the web client stateful, which §13.2 constrains.

---

## 8. Outbound integrations

### 8.1 Transactional mail

The provider and the transport are a `CHOICE`. What binds is the feedback loop:

- **Bounce and complaint feedback MUST reach the product**, be
  signature-verified or otherwise authenticated, and MUST update a suppression
  list the adapter consults before every send. A transport that cannot deliver
  that feedback cannot satisfy this clause — which in practice rules out bare
  SMTP with no event channel, not by naming it but by consequence.
- The provider MUST sit behind the mail adapter module (§3.3).
- All sends MUST be **enqueued as jobs**, never awaited inline in a request.
- Webhooks MUST be signature-verified and MUST update a **suppression list** that
  the adapter consults before every send.
- Delivery state — queued, sent, delivered, bounced, complained — MUST be
  persisted and exposed through the API, so any interface can show honest status
  and offer a rate-limited resend.
- Templates MUST live with the adapter, be plain-text-plus-HTML, and **MUST
  escape every interpolated value**. Display names are attacker-controlled.

### 8.2 Object storage

The provider is a `CHOICE`. The rules:

- Storage MUST be accessed exclusively through the storage adapter module.
- Uploads from any client MUST go through **short-lived signed URLs issued by the
  API** after authorization. Clients MUST NOT hold storage credentials.
- Uploaded media MUST be validated server-side by **content sniffing**, not by
  filename or client-declared MIME type, with a size cap and an allow-list.
- Every stored object MUST be attributable to an owning record, so the erasure
  inventory can find it.
- Public and private objects MUST be separated by path convention, and privacy
  MUST be enforced by the adapter, not by obscurity of the URL.
- **Streaming is mandatory for large payloads.** Uploads, downloads, media
  processing and generated artifacts — notably data-subject exports, which grow
  with account age — MUST be processed in chunks. Buffering a whole file or
  export into memory is a defect that fails under exactly the conditions that
  matter: the largest account, at the busiest moment.
- **Deleting an object MUST also invalidate any CDN cache entry for it**, or the
  erasure is cosmetic. Where the chosen storage and CDN do not do this
  automatically, the adapter MUST issue the invalidation and the erasure path
  MUST wait on it.

### 8.3 Push notifications

The transport is a `CHOICE`. What binds is who holds the tokens:

- **Device tokens and the principal they belong to MUST NOT be disclosed to any
  party that is not in the sub-processor register (§10.4)** with a signed
  agreement, a declared processing region, and coverage by erasure and export.
  Delivering server-owned, directly to the platform transports, satisfies this
  with no additional processor and is the path of least resistance. A push
  vendor is not forbidden — it is priced, exactly as the error tracker is.
- Push MUST be implemented in the notify adapter module and dispatched through
  the job queue with per-platform payload shaping.
- Device tokens are stored against the authenticated principal and device record,
  and MUST be deleted on logout, on invalidation feedback from the transport, and
  on account erasure.
- Rejection feedback MUST prune dead tokens automatically.
- **Push payloads MUST NOT contain personal data, credentials or anything
  sensitive.** A notification says *that* something happened and carries an
  identifier the app uses to fetch details over the authenticated API.
- Permission state MUST be tracked server-side — granted, denied, never asked —
  so campaigns do not target devices that cannot receive them.
- Transport credentials are secrets under §15 and MUST be rotatable.

### 8.4 Outbound call resilience

Applies to every call leaving the process — providers, third parties and internal
services alike:

- An explicit timeout is **mandatory**. A call with no timeout is a defect.
- Retries MUST use exponential backoff with jitter and a hard attempt cap.
  Uncapped retries against a degraded dependency multiply load precisely when the
  system can least absorb it.
- A **circuit breaker** MUST short-circuit a repeatedly-failing dependency, so one
  slow provider cannot queue inbound requests until the runtime exhausts memory
  or sockets.
- HTTP clients MUST reuse connections rather than performing a fresh handshake
  per call.
- Every dependency MUST have a **declared, tested degraded behaviour** — fail
  open, fail closed, or queue for later — chosen deliberately and recorded.

### 8.5 Outbound requests and SSRF

Any request the server makes to a URL that is user-supplied, user-influenced or
derived from user content is an SSRF vector. Common sources: embedded media URLs,
link previews, webhooks, avatar imports.

- The URL MUST be validated against an **allow-list** of schemes and hosts. A
  deny-list MUST NOT be used.
- Resolved addresses MUST be checked against private, loopback, link-local and
  cloud-metadata ranges — **after DNS resolution and again after any redirect**.
  The rebinding attack is exactly the gap between those two checks.
- Redirects MUST NOT be followed automatically for user-supplied URLs.
- Every such request MUST enforce a connect and read timeout, a response size cap
  and a content-type check.
- Responses MUST NOT be echoed back to the caller verbatim.

---

## 9. Clients

### 9.1 Design tokens

- One language-neutral token source holds color, spacing, typography scale, radii,
  elevation, motion and breakpoints.
- A build step MUST emit the per-platform form each client surface consumes.
- Generated outputs MUST be committed, and CI MUST fail if regeneration changes
  them.
- Components remain native per platform. Only the token *values* are shared.
- **Hardcoded colors, spacing values, font names and durations MUST NOT appear in
  any app on any platform.** A lint rule SHOULD enforce this where the toolchain
  allows.
- Products with runtime theming MUST express the runtime theme in the same token
  vocabulary, so generated tokens are the baseline and the runtime payload is an
  override — not a parallel system.

### 9.2 Web clients

- **Authorization MUST be enforced by the API.** Web route guards are UX, never
  security. The API assumes every request is hostile.
- **No secret may ever reach a client bundle.** A build-time check MUST fail on
  any non-public configuration value referenced from client code.
- Each app MUST declare a bundle-size budget; CI MUST fail on regression beyond a
  documented threshold.
- Fonts, icons and images live in **one shared source** consumed by all surfaces.
  Duplicating a font set across web and admin is a defect.
- Web fonts MUST be self-hosted, subset to the characters used, preloaded only for
  above-the-fold usage, and served with `font-display: swap`.
- Images MUST be served in modern formats at appropriate sizes, with explicit
  dimensions to prevent layout shift.
- **Non-critical components MUST be code-split** and loaded lazily — modals,
  charts, editors, pickers, anything below the fold or behind an interaction.
- The build MUST target modern browsers. Legacy transpilation output and
  polyfills MUST NOT be shipped to browsers that do not need them.
- Styling MUST be delivered as pre-compiled CSS. Runtime style computation that
  blocks rendering MUST NOT be introduced.
- Data-heavy routes SHOULD stream or defer non-critical sections rather than
  blocking first paint on the slowest query.

### 9.3 Server state vs client state

This separation exists because thin clients poll. It binds any client that holds
state locally — which is every rich client, and no purely server-rendered one.

- **Server state** — anything that came from the API — MUST go through one
  server-state layer. Caching, staleness, refetch-on-focus, retry with backoff,
  request de-duplication and loading/error states are configured **once**, not
  reinvented per component.
- **Client state** — open dialogs, form drafts, view preferences — belongs in
  local UI state.
- Server-derived values MUST NOT be copied into a client store, where they
  silently go stale.
- Ad-hoc HTTP calls in components are forbidden; all access is through the
  generated client wrapped by the server-state layer.
- Polling intervals MUST be declared per query, pause when the view is hidden, and
  back off on repeated failure.

A server-rendered or hypermedia client satisfies this section by construction:
there is no client-side copy of server state to go stale. It MUST still declare
its polling or refresh intervals and honour the backoff rule.

### 9.4 Idempotency contract

- Every mutating endpoint accepts a client-supplied idempotency key.
- The server stores the key with its response for a documented window and returns
  the original response on replay, rather than performing the action twice.
- The key is generated **when the user takes the action**, not when the request is
  sent — a retry after a timeout MUST carry the same key.

### 9.5 Forward compatibility

Shipped binaries live for years. Every client MUST:

- Tolerate unknown fields in a response without failing to parse.
- Tolerate unknown enum values by mapping them to a defined fallback, never by
  crashing or discarding the record.
- Send its platform and version on every request.
- Render the "upgrade required" response (§4.3) as a blocking screen with a store
  link.
- Degrade gracefully when an optional field is absent.

### 9.6 Localization — mandatory from day one

- No user-facing string may be hardcoded in any client on any platform.
- All copy lives in resource files with a **shared key namespace** across every
  client surface, so one translation set serves all of them.
- Server-supplied user-facing text MUST be either already localized — the client
  sends its locale — or accompanied by a key the client resolves.
- Plurals, dates, numbers and currency use platform locale APIs, never string
  concatenation.
- Layouts MUST tolerate string-length variation; RTL support MUST NOT be
  structurally precluded even if no RTL language ships initially.

Mandatory now because retrofitting it means touching every screen on every
platform.

### 9.7 Data-collection inventory as a build gate

A single **declared data-collection inventory** lives in the repository: for
every category of data the product collects — its purpose, whether it is linked
to identity, whether it is used for tracking, and its retention.

From that one source, the product generates its store privacy declarations (where
mobile ships) and its regulatory processing record.

CI MUST fail when code or a dependency collects a category absent from the
inventory, or when generated artifacts differ from the committed ones.

Third-party SDKs carrying their own privacy declarations MUST be reviewed against
the inventory before adoption. This gate exists because a mismatch between
declared and actual collection is simultaneously a store rejection and a
regulatory exposure.

### 9.8 Mobile behaviour

Applies to every native client surface.

**Offline.** The last successful response for a screen MAY be cached locally and
displayed when offline, and MUST be **visibly marked as stale** with its age.
Cached data is for display only; clients MUST NOT compute over it (§1). Actions
taken offline are **queued locally** with a client-generated idempotency key and
replayed on reconnect, in order, with backoff. The queue MUST be persistent
across restarts, MUST be bounded, and MUST surface its state to the user.
Conflicts are resolved **server-side** and the client adopts the server's
response; a client MUST NOT merge state itself. Sensitive data MUST NOT be cached
offline unless the product explicitly requires it, and then only in encrypted
platform storage. Actions with real-world consequence — payment, deletion,
irreversible submission — MUST NOT be queued offline.

**Credential storage** MUST use the platform's hardware-backed secure store,
never general-purpose preference storage or a plain file, and MUST be excluded
from unencrypted backups.

**Deep links** MUST be cryptographically verified via association files served by
the web app. Every link target MUST exact-match an allow-list — no wildcard, no
open redirect. Every deep link MUST have a working web fallback. Auth-bearing
links are single-use, short-TTL, and consumed by an immediate server-side
redirect that strips the token.

**Sensitive screens** MUST be masked in the app switcher and excluded from
screenshots and recents previews.

**Lifecycle.** Navigation state MUST be restorable and process death MUST be
handled without data loss, since the OS will terminate the app.

**Transport hardening.** Cleartext HTTP MUST be disabled at the platform level,
with no debug exception in a release build. **Certificate pinning is a declared
decision, not a default**: each product MUST record whether it pins and, if not,
why; if it does, it MUST document the backup-pin and rotation procedure —
unrotatable pins have bricked more apps than they have saved. The API base URL
MUST come from build configuration (§15), never from a value the app can be
persuaded to change at runtime.

### 9.9 Accessibility

WCAG 2.2 AA is the standard for web, with platform parity for native. This is a
`SHOULD` at release-gate strength rather than a hard CI gate, but semantic
markup, keyboard and screen-reader operability, visible focus, labelled controls,
font scaling, minimum touch targets, honoured reduce-motion settings and
token-guaranteed contrast are expected as ordinary craft rather than as a later
remediation project.

Accessibility findings that block a user from completing an account, consent,
payment or deletion flow are treated as defects, not as enhancements.

---

## 10. Observability

### 10.1 Required capabilities

The tools are a `CHOICE`. The capabilities are not:

| Capability | Requirement |
|---|---|
| Error tracking | An error and crash reporter on every deployable and every client surface. Unhandled errors MUST reach a human. |
| Structured logs | Machine-parseable, one event per line, with a fixed field set |
| Distributed tracing | A `correlationId` generated at the client, carried on every request, propagated into jobs, and present in every log line and error report |
| Metrics | Request rate, latency and error rate per endpoint; job throughput, failure rate, queue depth and age |
| Alerting | Defined thresholds with named owners for: error-rate spikes, dead-letter jobs, queue-age growth, failed migrations, rate-limiter unavailability, security events |
| Uptime checks | External checks on API health and critical flows |

**Uptime checks MUST NOT run only inside the infrastructure they watch.** A check
that dies with the provider it monitors is not an external check.

**Why an external error tracker clears a bar that most analytics vendors do
not.** §10.3 requires every non-essential event to be gated on server-side
consent, yet §10.4 assumes the error tracker is an external processor. That is
not an inconsistency; the two are on different lawful bases:

- Product analytics is **non-essential** processing. Non-essential events MUST
  NOT be emitted or buffered before consent is recorded server-side, and that
  MUST be enforced at the ingestion endpoint. A vendor SDK reporting directly to
  a backend the product does not control cannot be gated on consent state that
  backend never sees — so it is the *architecture* that fails §10.3, and any
  vendor whose ingestion the product does control passes it.
- Error and crash reporting is **strictly necessary** for service delivery and
  security, so it does not depend on consent to be lawful.

The remaining costs of an external error tracker — an extra sub-processor, an SDK
in the mobile binaries, retention outside your control — are not avoided. §10.4
prices them instead, which is why it imposes a register entry, a signed
agreement, explicit retention, and erasure and export coverage. The practical
reason is buildability: a first-party event pipeline is an endpoint and a table,
while a first-party crash reporter means symbolication, deminification, native
crash capture on two mobile platforms, grouping and alerting.

### 10.2 Redaction

A **never-log list** MUST be declared and MUST apply to every surface, including
mobile crash reports and breadcrumbs. A central redaction utility MUST be applied
at the logging boundary on each platform, and a test MUST assert it works.

Crash reporters MUST be configured to strip user content from breadcrumbs and to
obey the same list.

### 10.3 First-party product analytics

The analytics technology is a `CHOICE`, constrained by one property that most
vendor SDKs cannot satisfy:

- **Non-essential events MUST NOT leave the device before affirmative consent
  has been recorded server-side, and the classification MUST be enforced at the
  ingestion endpoint** — not merely in the client. Any pipeline able to honour
  that qualifies.
- In practice this means first-party collection to the product's own API, and it
  excludes an SDK reporting directly to a vendor backend, because such an SDK
  cannot be gated on consent state the vendor does not hold. That is a
  consequence of the property, not a ban on a named product: a vendor offering a
  consent-gated ingestion proxy under your control satisfies the clause.
- Where first-party collection is chosen, the accepted costs are no additional
  sub-processor, no SDK in the mobile binaries, full control over retention —
  and dashboards you build yourself.
- Events follow a **declared schema** in the contract; ad-hoc event names MUST NOT
  be emitted, and unknown events MUST be rejected.
- Events MUST carry a pseudonymous principal reference, never an email.
- Analytics data is personal data: it appears in the erasure inventory, the
  export and the collection inventory, and has a declared retention period.
- Cost accepted: dashboards are yours to build.

**Consent applies even though the analytics are first-party.** Being your own
processor removes the sub-processor problem; it does not remove the lawful-basis
problem. Therefore:

- Every event type MUST be classified in the contract as **strictly necessary**
  (security, fraud, abuse prevention, service delivery — permitted without
  consent) or **non-essential** (product analytics, engagement measurement,
  experimentation).
- Non-essential events MUST NOT be emitted, buffered or queued by any client
  before affirmative consent has been recorded server-side.
- Consent MUST be withdrawable, and withdrawal MUST stop collection immediately
  and be reflected in the client without requiring a restart.
- The classification MUST be **enforced at the ingestion endpoint**, not merely in
  the client: an event arriving without a valid consent state for its class MUST
  be rejected, not silently stored.
- Consent state is recorded through the same mechanism as every other consent,
  with history retained.

This is the clause that rules out platform-bundled analytics products regardless
of how convenient their integration is. It is a consent-lawfulness rule, not a
vendor preference, and it MUST NOT be recorded as a deviation.

### 10.4 Vendor and sub-processor register

Every external service that receives, stores or processes product data MUST
appear in a maintained register committed to the repository:

| Field | Content |
|---|---|
| Vendor | Name and service |
| Purpose | Why it exists |
| Data categories | What it receives, by classification (§5.7) |
| Processing region | Where the data physically lives and is processed |
| Agreement | DPA / BAA status and date |
| Owner | Who is accountable for the relationship |

- At minimum this covers: datastore host, hosting platform, cache, object
  storage, mail provider, error tracker, push transports, and any CI service that
  touches production data.
- **The error tracker is a data processor.** It will receive request context, user
  identifiers and — despite redaction — occasional payload fragments. It MUST be
  in the register with a signed agreement, retention configured explicitly, and
  its data covered by erasure and export.
- Adding any new SDK, integration or outbound data flow REQUIRES a register entry
  in the same change. A pull request introducing an outbound flow without one
  MUST be rejected.
- Consolidating on a single cloud reduces the number of entries; it does not
  remove the obligation for the ones that remain.
- Where a product's scope includes health data, no vendor may receive it without
  an executed BAA recorded here.

---

## 11. Testing

### 11.1 Mandatory

**Contract tests.** Every client and the server verify against the same fixtures
derived from the contract document. CI fails when any client drifts. With
generated clients in unrelated languages and no shared runtime, this is the
highest-value control in the entire repository.

Required coverage: every endpoint's success shape, every documented error code,
pagination envelopes, unknown-field tolerance, unknown-enum tolerance, and the
"upgrade required" response.

**Unit tests.** All of `core`, plus service-module logic. Pure, fast, no I/O.

**Integration tests.** API routes exercised end to end against an ephemeral real
instance of the chosen datastore, seeded through the migration chain. Not mocks.
These catch the migration, index, transaction and constraint bugs that mocks
hide.

**Route-coverage tests.** A structural test MUST fail the build when any route
ships without an explicit authorization declaration, and when any route ships
without a declared rate-limit bucket (§4.6).

### 11.2 Recommended, not gated

End-to-end tests on critical web journeys and mobile smoke journeys are `SHOULD`.
Where they are not automated, the release checklist MUST name the manual journeys
verified before each release — an untested release path is a decision, and it
should be a visible one.

### 11.3 Discipline

- Tests run on every pull request; the default branch is always releasable.
- A test suite that finds no tests MUST fail, not pass. A mis-globbed suite
  reporting green over zero tests is the failure mode this rule exists to catch.
- Flaky tests are quarantined and fixed, never re-run until green.
- Every bug fixed gets a regression test.
- No coverage-percentage target. Coverage of the security suite, the contract and
  the domain rules is what matters.

---

## 12. Security and compliance

- **Secret scanning** as a pre-commit hook *and* a CI gate. The CI scan MUST
  examine full history, not only the tip commit.
- **Dependency scanning** in CI on every PR, failing on known-exploitable
  advisories in production dependencies.
- **Security headers** on all browser-facing responses: HSTS with preload, a
  restrictive CSP without inline script execution, content-type options,
  referrer policy and a permissions policy.
- **CORS** with an explicit origin allow-list per environment. Reflecting an
  arbitrary origin MUST NOT be the default, even when credentials are excluded.
- **TLS 1.2 minimum, 1.3 preferred**, enforced everywhere.
- **Input validation** at every boundary against a generated schema (§4.1).
- **All queries parameterized.** String-concatenated query construction is a hard
  failure.
- **Startup validation**: every service declares its required configuration and
  refuses to boot when a security-relevant value is missing or is a known
  placeholder.

### 12.1 Data subject rights as product features

These MUST be implemented as features, not as manual operations:

- **Rectification.** Every field of personal data a user supplied MUST be
  correctable by that user through an authenticated, server-validated endpoint.
  Where a field cannot be self-corrected, there MUST be a documented request path
  with a defined response window, and every operator-side correction MUST write an
  audit record with a reason.
- **Export completeness** is enforced structurally by §5.7: a table holding
  principal-owned personal data is either in the export or explicitly excluded
  with a reason, and CI fails on a table that is neither.
- **Erasure** MUST propagate to every store that holds the data — datastore,
  object storage, cache, analytics and any registered sub-processor.

### 12.2 Assurance cadence

- A vulnerability disclosure policy MUST be published, with a monitored contact
  and a stated response window.
- Dependency advisories MUST be triaged within the window declared in the Stack
  Profile.
- An independent security review or penetration test SHOULD be performed before
  first public release and at a declared cadence thereafter. Findings and their
  disposition are recorded.

---

## 13. Build, CI and release

### 13.1 Required gates

The CI platform and the tools are a `CHOICE`. Every pull request MUST run, and
MUST fail the build on:

1. Install from the committed lockfile in frozen mode
2. Codegen drift — regenerate every generated artifact and fail if the tree differs
3. Lint
4. Format check
5. Type check, where the track is statically typed
6. Unit tests
7. Integration tests against an ephemeral real datastore
8. Contract tests
9. Route-coverage tests — authorization and rate-limit declarations
10. Dependency scan
11. Secret scan, over full history
12. Layer-boundary check (§3.2)

Workflows MUST be path-filtered so a change to one surface does not rebuild
unrelated ones. Where a track's runners are materially more expensive — macOS
runners for iOS builds — path filtering is mandatory rather than an optimization.

### 13.2 Promotion

**The three-tier promotion flow is not optional**, whichever host is chosen:
preview per pull request, staging on merge to the default branch, production on
an explicit release action.

- Migrations run in the deploy pipeline **before** the new code is serving.
- Every deploy is traceable to a commit, and rollback is a documented, rehearsed
  procedure — not an improvisation.
- A deployment target that cannot provide an isolated per-PR preview MUST provide
  an equivalent pre-merge verification environment, and the substitution MUST be
  recorded in the Stack Profile.

**Stateful web clients constrain the deployment target.** A web client holding a
persistent server-side session per connection requires sticky routing and
graceful connection draining on deploy. Where a product chooses that model, its
host MUST support both, and the release runbook MUST state what happens to
in-flight sessions during a deploy.

### 13.3 Mobile release

- Signing material MUST be stored reproducibly with a documented, **tested**
  recovery path. Losing an Android upload key is unrecoverable.
- PR builds compile and run tests; they do not sign or distribute.
- Merges to the default branch produce an internal-track build automatically.
- Store submission is an explicit, triggered action, never automatic.
- Build numbers derive from CI run identifiers; marketing versions are set
  deliberately. Both MUST be traceable to a commit.

### 13.4 Release coordination

The API MUST be deployed before clients that depend on new endpoints. Because
mobile release timing is controlled by store review, the sequence is always
**additive API → web/admin → mobile submission**. A mobile binary MUST NOT depend
on an unreleased endpoint.

---

## 14. Performance budgets

| Surface | Budget |
|---|---|
| API p95, typical read endpoint | ≤ 200 ms server time |
| API p95, session validation | ≤ 10 ms |
| Web LCP (p75, mobile field data) | ≤ 2.5 s |
| Web INP (p75) | ≤ 200 ms |
| Web CLS (p75) | ≤ 0.1 |
| Mobile cold start to first meaningful content | ≤ 2 s on a mid-range device |
| Job queue age (p95) | ≤ 60 s for interactive-adjacent jobs |
| API response payload | ≤ 50 KB uncompressed, per response |
| Datastore round trips | ≤ 3 per hot-path request handler |
| Cold start (p95), where the runtime has one | ≤ 1 s to first byte |
| Web initial bundle | Declared per app, enforced in CI |

Budgets are **measured, not assumed**. Regressions fail the build where a gate
exists and are triaged where they do not.

The web field-data budgets require **first-party collection**, because §10.3
rules out any analytics pipeline that cannot be consent-gated. Reporting field vitals to the product's
own ingestion endpoint is required work, not an optional extra.

---

## 15. Configuration and secrets

- Every service declares its required configuration in **one schema** and
  validates it at startup, failing loudly and immediately on anything missing,
  malformed or left at a placeholder value.
- **Three tiers** — preview/dev, staging, production — with separate credentials
  for every external service. A single credential shared across tiers is a defect.
- Secrets live in the platform's secret storage and are never committed. An
  example environment file documents every variable with a description and
  whether it is required; it **MUST contain no real values**.
- Local development values MAY live in a git-ignored environment file. They MUST
  NOT be production credentials.
- Mobile builds get a generated configuration file per scheme or flavour — API
  base URL, environment name, feature toggles. **Mobile binaries MUST NOT contain
  server secrets**; anything in an app bundle is public.
- Every key is versioned, and rotation is zero-downtime with a documented
  runbook.
- A dedicated secret manager MAY be adopted; it is not required.

---

## 16. Documentation

- `docs/specs/` holds binding specifications for this product. Anything there is
  authoritative for behaviour.
- `docs/notes/` holds superseded specs, research and transcripts. Never
  authoritative.
- A superseded spec **moves** to `docs/notes/`; it is not deleted and not left in
  `docs/specs/`.
- Every product MUST carry: its Stack Profile (§18), an architecture overview, a
  local-setup guide that works from a clean machine, and operational runbooks.
- A product MUST NOT carry a copy of this specification (§2.1).
- Every non-obvious decision MUST be recorded with its rationale and the
  alternatives rejected. Comments MUST explain *why*, including known residual
  limitations.
- Agent-facing instructions live in `CLAUDE.md` / `AGENTS.md` at the root.

---

## 17. Non-goals

Explicitly outside the default architecture, so a product does not drift into one
without a decision. Each is a **deviation requiring its own design**, not a
prohibition:

- **Microservices.** One API, one worker, one datastore per product until there is
  a measured reason otherwise.
- **Bidirectional realtime data channels** (§7.7).
- **Full offline-first local databases with bidirectional sync** (§9.8).
- **Sharing UI component code across web and native.**
- **More than one API contract format in a product** (§4.1).

Two items that were non-goals in 4.x are **no longer** non-goals, because 5.0.0
stopped grading technology:

- **Self-hosted infrastructure** is now a `CHOICE`. The obligations that made it
  costly — backups, PITR, restore drills, uptime checks that survive the host's
  own outage — are stated as requirements in §5.5 and §10.1 and apply to managed
  and self-hosted alike.
- **Cross-platform UI frameworks** are now a `CHOICE`. A product adopting one
  still owes §1's thin-client doctrine, §4.1's generated client, §9.6's
  localization and §9.8's mobile behaviour rules in full.

---

## 18. The product Stack Profile

Every product MUST carry a Stack Profile at `docs/specs/stack-profile.md`
recording:

1. **`STACKSPEC` version** implemented.
2. **Track and selections** — every `CHOICE` this spec defers: language and
   runtime, web framework, API framework, datastore engine and host, data-access
   library and migration tool, cache, queue substrate, object storage, mail
   provider, error tracker, hosting platform, CI platform, package manager and
   task runner, lint/format/test tooling.
3. **Exact pinned versions** of every framework, runtime and toolchain named
   above.
4. **Minimum supported OS versions** for each client surface, with a review date.
5. **Environment inventory** — every tier, its URLs, its datastore, its secrets
   scope.
6. **Provisioning ledger** — for each external service, whether dev and
   production credentials exist, where they are stored, and who owns them. Values
   are never recorded here.
7. **Data-collection inventory** (§9.7), or a pointer to it.
8. **Data residency** — the processing region of every vendor in the register
   (§10.4), the jurisdictional boundary the product commits to, and the legal
   basis for any cross-border transfer.
9. **Resilience** — RPO, RTO, PITR retention, backup retention, and the date of
   the last successful restore drill (§5.5).
10. **Classification and retention** — a pointer to the machine-readable field
    classification and the per-table retention declarations (§5.7).
11. **Queue economics** — substrate, drain schedule, batch size, and the
    resulting steady-state load (§7.3).
12. **Certificate-pinning decision** per mobile platform, with rationale and, if
    pinning, the rotation procedure (§9.8).
13. **Assurance cadence** — dependency-advisory triage window and security review
    schedule (§12.2).
14. **Capability gaps** — every place a `CHOICE` could not supply a capability
    this spec requires, and the compensating control adopted (§0.4). Specifically:
    non-transactional enqueue (§7.2), absent datastore constraints (§5.2), absent
    PITR (§5.5), absent statement timeouts (§5.6), absent per-PR previews (§13.2).
15. **Deviations** — every `SHOULD` not followed and every `MUST` waived, each
    with a reason and a named approver.

A `CHOICE` recorded in item 2 is **never** a deviation. Item 15 is reserved for
graded clauses, which keeps the deviation register meaningful.

---

## 19. Conformance checklist

Every item is checkable regardless of stack.

**Repository and layering**
- [ ] Package manager and task runner versions pinned; CI installs frozen
- [ ] Uniform task vocabulary across workspaces; one root command builds everything
- [ ] Layer boundaries declared and enforced by a failing CI check
- [ ] `core` imports no framework, no I/O, no environment, no clock
- [ ] No web framework imported inside any shared module
- [ ] Client apps import no server module
- [ ] Every external SDK confined to exactly one adapter module
- [ ] No circular module dependencies
- [ ] No copy of this spec in the repository

**Contract**
- [ ] OpenAPI document is the committed source of truth
- [ ] A client generated and committed for every client surface; CI fails on drift
- [ ] Request validation and response types generated from the contract
- [ ] Breaking-change check against the previous released contract
- [ ] Explicit `/vN` path versioning with declared sunset dates
- [ ] Client platform and version header recorded on every request
- [ ] Minimum-client-version refusal implemented and rendered by every client
- [ ] Single error envelope with stable codes; all lists paginated with a hard cap
- [ ] Idempotency keys accepted on every mutating endpoint
- [ ] Every endpoint declares a rate-limit bucket; undeclared endpoints fail the coverage test
- [ ] Cacheability declared per endpoint; default `no-store`; public data served from the edge
- [ ] Text responses over 1 KB compressed; payload budget enforced
- [ ] Conditional requests on large or concurrently-edited resources
- [ ] No internal detail in production errors, asserted by a test
- [ ] No handwritten HTTP calls to product endpoints in any client

**Data**
- [ ] Driver supports the transaction semantics §5.3 requires on write paths
- [ ] Connection strategy matches the execution model; acquisition timeout set
- [ ] Multi-record writes atomic; no read-modify-write without transaction or conditional
- [ ] No external I/O inside an open transaction
- [ ] All query predicates indexed; domain invariants enforced by the engine or a recorded chokepoint
- [ ] Migrations ordered, reversible-or-justified, lock-protected, applied by a runner, tested on non-empty data
- [ ] Destructive changes sequenced across deploys
- [ ] Migrations run under a separate, more privileged role
- [ ] Three tiers with separate datastores and credentials
- [ ] Integration tests run against an ephemeral real instance of the chosen engine
- [ ] Statement timeout or client-side deadline enforced
- [ ] ≤3 round trips per hot-path handler; no waterfalls; no N+1
- [ ] Aggregation and filtering pushed down; named fields selected
- [ ] PITR or a documented equivalent; backups encrypted; restore drill performed and dated
- [ ] RPO and RTO declared; restore runbook replays the erasure suppression list
- [ ] Every field classified; every table has declared retention, enforced by a job
- [ ] Encryption at rest on datastore, object storage and backups; `secret` fields encrypted at the application layer
- [ ] CI fails on an unmapped field or a table missing retention
- [ ] Every table with principal-owned PII is in the export or explicitly excluded
- [ ] Application role holds no update/delete on audit records

**Jobs and integrations**
- [ ] Enqueue atomic with the originating write, or an outbox with a relay
- [ ] Job contract independent of substrate and trigger
- [ ] Atomic claim; backoff with jitter; attempt cap; dead-letter that alerts; stuck-job recovery
- [ ] Every handler idempotent, typed, individually invocable, observable, alerting
- [ ] Where the queue is polled: claim-predicate index, bounded batches, empty-drain backoff, terminal rows pruned
- [ ] All §7.4 required jobs implemented
- [ ] Trigger endpoints authenticated with a constant-time secret comparison
- [ ] Fan-out concurrency bounded; listeners and timers cleaned up
- [ ] Mail via provider API with signature-verified webhooks and a suppression list
- [ ] All mail enqueued, never inline; templates escape interpolated values
- [ ] Storage behind an adapter; signed-URL uploads; server-side content sniffing
- [ ] Large uploads, downloads and exports streamed, never buffered whole
- [ ] Object deletion invalidates CDN cache
- [ ] No party outside the sub-processor register holds device tokens; tokens pruned on rejection; no PII in payloads
- [ ] Every outbound call has a timeout, capped jittered backoff, circuit breaker and connection reuse
- [ ] Each dependency has a declared, tested degraded behaviour
- [ ] User-supplied URLs: allow-list, private-range checks after DNS and after redirect, no auto-redirect, size and time caps

**Caching**
- [ ] Nothing exists only in the cache; everything read back is schema-validated
- [ ] Failure policy declared per use; credential rate limits fail closed
- [ ] Keys namespaced by product and environment; user-derived entries enumerable for erasure
- [ ] Invalidation explicit on write; every entry has a TTL
- [ ] In-process caches bounded with an eviction policy
- [ ] Per-request memoization prevents duplicate queries within one request

**Clients**
- [ ] Design tokens generated per platform from one source; CI fails if stale
- [ ] No hardcoded colors, spacing, fonts or durations on any platform
- [ ] Authorization enforced by the API, not by client route guards
- [ ] No secret reachable from client code, enforced by a build-time check
- [ ] Server state through a dedicated layer where the client holds state
- [ ] Polling intervals declared, paused when hidden, backed off on failure
- [ ] Assets shared, subset, budgeted; no duplicated font sets
- [ ] Non-critical components code-split; modern build target; no legacy polyfills
- [ ] Unknown fields and unknown enum values tolerated by every client
- [ ] No hardcoded user-facing strings; shared localization key namespace
- [ ] Offline: marked-stale read cache, persistent bounded write queue, idempotency keys, server-resolved conflicts
- [ ] Credentials in hardware-backed platform storage, excluded from backups
- [ ] Deep links verified, allow-listed, single-use, with web fallback
- [ ] Sensitive screens masked in app switcher and excluded from screenshots
- [ ] Cleartext HTTP disabled on mobile; pinning decision recorded
- [ ] Accessibility baseline met across surfaces

**Observability**
- [ ] Error and crash reporting on every deployable and client surface
- [ ] `correlationId` generated client-side, propagated through API and jobs into every log and error
- [ ] Structured logs with a fixed field set
- [ ] Metrics and alerts with named owners for the required thresholds
- [ ] Uptime checks survive an outage of the infrastructure they watch
- [ ] Redaction utility applied at every logging boundary, including mobile breadcrumbs, with a test
- [ ] Declared event schema; no analytics pipeline that cannot be gated on server-side consent
- [ ] Every event classified strictly-necessary vs non-essential
- [ ] Non-essential events blocked before consent, enforced at ingestion; withdrawal immediate
- [ ] Analytics data covered by erasure, export and the collection inventory
- [ ] Sub-processor register complete, with region and DPA/BAA status per vendor
- [ ] Error tracker in the register, retention configured, covered by erasure and export
- [ ] New outbound data flows require a register entry in the same change

**Testing and CI**
- [ ] Contract tests across server and every client, failing on drift
- [ ] Unit tests for `core` and service logic
- [ ] Integration tests on an ephemeral real datastore
- [ ] Route-coverage tests for authorization and rate-limit declarations
- [ ] A suite finding zero tests fails rather than passes
- [ ] All twelve §13.1 gates present and failing the build
- [ ] Secret scan covers full history
- [ ] Workflows path-filtered; expensive runners not used on unrelated changes
- [ ] Three-tier promotion; migrations before serving; rollback documented and rehearsed
- [ ] Release order enforced: additive API → web/admin → mobile submission
- [ ] Mobile signing material stored reproducibly with a tested recovery procedure

**Configuration and compliance**
- [ ] One config schema per service, validated at startup, refusing placeholder secrets
- [ ] Separate credentials per tier; example env file complete and value-free
- [ ] Mobile config generated per scheme; no server secrets in any binary
- [ ] Security headers, explicit CORS allow-list, TLS enforcement
- [ ] All queries parameterized
- [ ] Data-collection inventory is the single source for privacy artifacts
- [ ] CI fails on undeclared collection or stale generated artifacts
- [ ] Performance budgets declared and measured; web field vitals collected first-party
- [ ] Self-service rectification of user-supplied PII; operator corrections audited
- [ ] Erasure propagates to every store and sub-processor
- [ ] Vulnerability disclosure policy published; triage window and review cadence declared
- [ ] Stack Profile complete: all `CHOICE`s recorded, all capability gaps recorded, all deviations approved

---

## 20. Governance

- Semantic versioning. **A new `MUST` is a major version.**
- Promoting a `CHOICE` to a `SHOULD` or `MUST` is a major version. Naming a
  vendor anywhere in this document is a defect, not an edit.
- Products record the `STACKSPEC` version they satisfy in their Stack Profile.
- A conflict between a product's needs and this spec is resolved by a recorded
  deviation with a named approver — not by silent divergence.
- Superseded versions move to `docs/notes/`.
- This spec is the answer to "what makes a product of ours correct." When reality
  outgrows it, the spec changes; the codebase does not quietly drift ahead of it.
