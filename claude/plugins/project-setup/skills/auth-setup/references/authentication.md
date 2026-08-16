# Authentication & Authorization Framework Specification

**Status:** Normative
**Version:** 3.0.0
**Applies to:** every web and mobile application in this organization
**Audience:** Claude Code (as a generation guide) and human implementers/reviewers

---

## 0. How to use this document

This specification defines a **single, reusable authentication and authorization framework**. It is the source of truth for:

- the Auth API surface (consumed by any number of visual interfaces),
- the persistence schema required to back it,
- the security, privacy, and performance controls the implementation must satisfy,
- the client-side contract every consuming web/mobile app must implement,
- the tests and audits that prove conformance.

**This document is deliberately technology-neutral.** It names no language, framework, runtime, database engine, ORM, cache product, or cloud provider. Every requirement is expressed as behaviour, structure, and constraint. Section 2 defines how an implementer binds these requirements to the concrete stack of the project it is generating into.

### 0.1 Conformance language

- **MUST** / **MUST NOT** — absolute requirement. A violation is a defect.
- **SHOULD** / **SHOULD NOT** — strong recommendation; deviation requires a written, reviewed justification recorded in the project's configuration reference (§24).
- **MAY** — genuinely optional.

### 0.2 Reading order for a generator

1. §2 — resolve the concrete technology stack. **Do not generate any code before this step completes.**
2. §3 — internalize the architecture and the principal model.
3. §4–§6 — generate the persistence schema, crypto/key management, and session layer.
4. §7–§16 — generate flows, authorization, admin plane, privacy machinery, audit trail.
5. §17–§21 — generate abuse controls, notifications, API surface, client SDK contract, UI requirements.
6. §22–§26 — apply performance budgets, retention jobs, configuration, tests, deliverables.
7. §27 — run the conformance gate. Generation is not complete until it passes.

---

## 1. Scope

### 1.1 In scope

| Area | Summary |
|---|---|
| Identity | A single global user space; separate, isolated administrative identity plane; service accounts as first-class non-human principals |
| Authentication | Email + password, passkeys/WebAuthn, magic link / email OTP, social OIDC, enterprise SAML, TOTP second factor |
| Sessions | Authoritative server-side sessions; cookie transport for web, opaque bearer transport for mobile/native; cache-accelerated validation |
| Authorization | Roles that expand to fine-grained named permissions, enforced statelessly at every endpoint |
| Privacy | Versioned consent, self-service data export, rectification, grace-period deletion followed by cryptographic erasure |
| Assurance | Hash-chained append-only audit trail, tiered retention, security notifications, privileged-access alerting |
| Delivery | Server implementation + persistence schema/migrations, client SDK contract, test suite, operational runbooks |

### 1.2 Out of scope (explicit non-goals)

- **User impersonation / "log in as user" support tooling.** Deliberately excluded. Implementations **MUST NOT** provide any mechanism by which an administrative principal acquires a user-plane session. See §12.6.
- Multi-tenant organization membership. The identity model is a single global user space (§3.2). §4.14 documents the forward-compatibility rule that keeps this option open.
- Acting as a general-purpose third-party OAuth authorization server. Only the token *shape* and verification metadata are OIDC-compatible (§6.4).
- Billing, subscription, or entitlement logic. Permissions are the boundary; commercial entitlement mapping belongs to the consuming application.

### 1.3 Deferred extension points

These are intentionally not built now. The implementation **MUST** leave the named seam so they can be added without a schema migration or breaking API change.

| Extension | Required seam |
|---|---|
| Bot/CAPTCHA challenge on high-risk endpoints | A `challenge` verification port in the abuse-control pipeline (§17.6) |
| Outbound domain event stream | An outbound notification port with a stable event vocabulary (§18.4) |
| Anomaly / risk scoring | A `risk_signal` evaluation hook invoked before session issuance (§17.7) |
| Granular purpose-level consent | `consent_record.purpose` column, nullable, defaulted (§14.5) |
| Multi-region data residency | `region` attribute on every principal + a single documented enforcement point (§5.7) |
| Organization/tenant membership | Ownership predicate indirection (§11.5) |
| User-issued personal API tokens | Reuse of the service-account credential model (§13.6) |

---

## 2. Technology binding (mandatory first step)

The implementation's concrete technology **MUST** be resolved by this exact procedure, in order. The generator **MUST NOT** silently assume a stack.

### 2.1 Resolution order

1. **Declared stack document.** Look for a tech-stack specification in the project, in this order: `docs/specs/stack-profile.md`, `docs/specs/tech-stack.md`, `specs/tech-stack.md`, `specs/tech_stack.md`, `docs/tech-stack.md`, `TECH-STACK.md`, or a `tech_stack` section in `CLAUDE.md`. If found, it is authoritative and overrides everything below.
2. **Inference from the repository.** If no declared document exists, infer from, in order of authority: dependency/package manifests; existing migration or schema directories; existing source under the project's conventional source root; build, container, and deployment configuration; lint/format configuration (for naming and style conventions).
3. **Ask.** If neither step yields an unambiguous answer for any dimension in §2.2, **stop and ask the user**. Do not guess, and do not proceed with a placeholder.

### 2.2 Dimensions that MUST be resolved before generation

| Dimension | Why it is required |
|---|---|
| Implementation language and runtime | Determines concurrency model, crypto library availability, KDF offloading strategy (§22.4) |
| Deployment topology: long-lived process vs. serverless/edge | Determines connection pooling strategy (§22.5) — this is a P0 performance concern |
| Primary persistence engine and its paradigm (relational / document / other) | Determines schema realization (§4.2) |
| Schema/migration tooling | Determines the deliverable format for §4 |
| Data access layer (query builder / ORM / driver) | Determines how ownership scoping is enforced and audited (§11.4) |
| Cache/volatile store availability | Determines session validation path (§6.6). If none is available, §6.6.3 fallback applies |
| Key management service availability | Determines §5. If no KMS exists, generation **MUST** stop and ask — §5 has no unmanaged-key fallback for deployed environments |
| Outbound email transport | Required for verification, OTP, recovery, and security notifications (§18) |
| Scheduled job / worker mechanism | Required for retention and deletion jobs (§23) |
| Test framework and CI runner | Required for the conformance gate (§27) |
| HTTP/API layer conventions | Determines routing, middleware, and error-envelope realization (§19) |

### 2.3 Binding rules

- **R2.1** — Generated code **MUST** match the surrounding project's existing conventions for naming, file layout, module boundaries, error handling, logging, and dependency injection. Where this specification and the project's conventions conflict on *style*, the project wins. Where they conflict on a **MUST** requirement of *behaviour or security*, this specification wins, and the conflict **MUST** be recorded in the configuration reference.
- **R2.2** — Prefer the project's already-adopted libraries over introducing new ones. New dependencies are permitted only for capabilities that cannot be responsibly hand-rolled: password hashing (KDF), WebAuthn attestation/assertion verification, SAML XML signature verification, JWT/JWS signing and verification, and constant-time comparison. Hand-rolling any of these is a defect.
- **R2.3** — Every abstract type in §4 **MUST** be mapped to the engine's most precise native equivalent (see §4.3). Do not degrade to a generic string type when a precise type exists.
- **R2.4** — Generation **MUST** be idempotent and deterministic: re-running against an unchanged project produces no diff. Ordering of generated declarations, routes, migrations, and catalog entries **MUST** be stable and explicitly sorted, never dependent on hash-map iteration order.
- **R2.5** — The framework **MUST** be generated as a **self-contained module** with an explicit public interface. Consuming application code depends only on that interface. Internals (schema, session records, credential material, KDF invocation) **MUST NOT** be reachable from application code.

---

## 3. Architecture

### 3.1 Principal model

A **principal** is any entity that can authenticate and be authorized. Three principal types exist, and they are **structurally disjoint**.

| Principal type | Identity store | Credential types | Session type | Purpose |
|---|---|---|---|---|
| `user` | User plane | password, passkey, email OTP/magic link, social OIDC, enterprise SAML, TOTP (as second factor) | User session | End users of the applications |
| `admin` | Admin plane | passkey/WebAuthn **only** | Admin session | Platform staff performing privileged operations |
| `service` | Service registry | client credential (secret or key pair) | Service token | Backend services, jobs, webhooks |

**Hard invariants — each is a P0 defect if violated:**

- **INV-1** — A user session **MUST NEVER** confer any admin-plane permission, under any role, flag, or configuration.
- **INV-2** — An admin session **MUST NEVER** be accepted by a user-plane endpoint, and vice versa. Session records carry an immutable `principal_type` that is verified on every validation, not merely at issuance.
- **INV-3** — A user record and an admin record **MUST** be separate rows in separate stores with separate credentials, even when they describe the same human being. There is no linkage, elevation, or promotion path between them.
- **INV-4** — There is no code path that mints a session for a principal other than the one that authenticated. (This is what forbids impersonation; see §12.6.)
- **INV-5** — Authorization **MUST** be computed server-side on every request from authoritative state. No decision may rely on a client-supplied role, permission, principal type, or identifier.

### 3.2 Identity space

A **single global user space**: a user is identified by a globally unique account, not scoped to any organization or tenant. Consequently, the isolation boundary that all authorization enforcement protects is **the individual account** (§11.4), not a tenant.

### 3.3 Component decomposition

The implementation **MUST** be structured as these logical components with these dependency directions. Names are illustrative; the project's naming conventions govern.

```
                      ┌──────────────────────────────┐
   web / mobile /     │        Auth API layer        │
   admin UIs  ───────▶│  (routing, envelope, rate    │
                      │   limiting, transport)       │
                      └───────────────┬──────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        ▼                             ▼                             ▼
┌───────────────┐            ┌─────────────────┐          ┌──────────────────┐
│ Authentication│            │  Authorization  │          │  Privacy &       │
│   flows       │            │  (permission    │          │  compliance      │
│ (§7–§10)      │            │   resolution)   │          │  (§14–§15)       │
└───────┬───────┘            └────────┬────────┘          └────────┬─────────┘
        │                             │                            │
        └─────────────┬───────────────┴──────────────┬─────────────┘
                      ▼                              ▼
            ┌───────────────────┐        ┌────────────────────────┐
            │  Session service  │        │  Audit trail service   │
            │  (§6)             │        │  (§16, append-only)    │
            └─────────┬─────────┘        └───────────┬────────────┘
                      │                              │
        ┌─────────────┴──────────────┬───────────────┘
        ▼                            ▼
┌───────────────┐          ┌──────────────────┐        ┌───────────────────┐
│  Cache tier   │          │  Persistence     │◀──────▶│  Crypto / KMS     │
│  (§6.6)       │          │  (§4)            │        │  provider (§5)    │
└───────────────┘          └──────────────────┘        └───────────────────┘
```

**Dependency rules:**

- **R3.1** — The Auth API layer **MUST NOT** access persistence directly. All access passes through a service component.
- **R3.2** — The crypto/KMS provider **MUST** be a single module with a narrow interface. No other component may invoke a cryptographic primitive directly, with the sole exception of constant-time comparison helpers.
- **R3.3** — The audit trail service **MUST** be write-only from the perspective of every other component. No component may expose an update or delete path to audit records (§16.3).
- **R3.4** — Every component **MUST** be independently testable with the persistence, cache, KMS, and email ports substituted.

### 3.4 Request lifecycle for an authenticated request

Every authenticated request **MUST** pass through these stages in this order. Skipping or reordering a stage is a defect.

1. **Transport validation** — TLS enforced; security headers applied (§19.8).
2. **Rate limit admission** — before any persistence access (§17).
3. **Credential extraction** — cookie (web) or `Authorization: Bearer` (native). Exactly one source per request; presenting both is rejected (§6.5.3).
4. **CSRF validation** — for cookie-borne, state-changing requests only (§6.5.4).
5. **Session resolution** — cache-first, schema-validated, with authoritative fallback (§6.6).
6. **Principal-type assertion** — the resolved `principal_type` must match the plane of the route (INV-2).
7. **Session state assertion** — not revoked, not expired (idle and absolute), principal not locked or pending deletion.
8. **Consent gate** — required legal document versions accepted (§14.4).
9. **Step-up assertion** — for routes declaring a step-up requirement (§8.5).
10. **Permission check** — required permission present in the resolved permission set (§11.3).
11. **Ownership check** — for any route touching a specific resource (§11.4).
12. **Handler execution.**
13. **Audit emission** — for every auditable action (§16.2).
14. **Response shaping** — error envelope and cache headers (§19.5, §19.8).

---

## 4. Persistence schema

### 4.1 Purpose

This section defines the **logical data model**. It is complete: an implementation needs no additional tables to satisfy this specification. Generate it into the project's native schema/migration tooling, resolved per §2.

### 4.2 Realization rules

- **R4.1** — For a relational engine, each entity below becomes a table; each attribute a column; each stated index a real index; each stated constraint a real constraint (not application-level validation alone).
- **R4.2** — For a document engine, each entity becomes a collection with an enforced schema/validator. Every stated uniqueness constraint **MUST** be realized as a unique index, and every stated foreign key as an application-enforced referential check **plus** a documented consistency job. Referential integrity that exists only in developer intention is a defect.
- **R4.3** — Every attribute marked **`[ENC]`** **MUST** be stored encrypted per §5.4. Every attribute marked **`[HASH]`** stores only an irreversible digest — the plaintext is never persisted. Every attribute marked **`[BIDX]`** is a keyed blind index used solely for equality lookup (§5.5).
- **R4.4** — Timestamps are UTC with at least microsecond precision. Never store local time or a naive timestamp.
- **R4.5** — Identifiers **MUST** be unguessable and non-sequential (UUIDv4/UUIDv7 or equivalent ≥122 bits of entropy). Auto-incrementing integers **MUST NOT** be exposed in any API response or URL. Where the engine benefits from a monotonic internal key, it **MUST** remain internal and never appear in an API contract.
- **R4.6** — Every table with growth proportional to traffic (`session`, `audit_event`, `auth_attempt`, `security_event`, `one_time_credential`) **MUST** have a retention job (§23) and an index supporting that job's delete predicate.
- **R4.7** — `SELECT *` / full-document fetches are forbidden on any hot path. Queries **MUST** project only the attributes consumed (§22.3).

### 4.3 Abstract type vocabulary

| Abstract type | Meaning | Mapping guidance |
|---|---|---|
| `id` | Opaque unique identifier | Native UUID type if available, else fixed-length 26–36 char string with a check constraint |
| `text` | Unicode text | Native text/varchar; specify a maximum where one is stated |
| `bytes` | Binary | Native binary/blob type; **not** base64 in a text column |
| `bool` | Boolean | Native boolean; never an integer flag |
| `timestamp` | UTC instant, ≥µs precision | Native timestamp-with-timezone |
| `int` | Signed integer | Native integer of sufficient width |
| `enum(...)` | Closed value set | Native enum, or text plus a check constraint. **MUST** be constrained at the storage layer |
| `json` | Structured document | Native JSON type with a validated shape; **MUST NOT** contain PII (§16.4) |

### 4.4 Entity: `user`

The user-plane principal.

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `email_ciphertext` | `bytes` **[ENC]** | The address; never stored in plaintext |
| `email_index` | `bytes` **[BIDX]** | Blind index over the normalized address (§5.5). **UNIQUE**, partial: only where `status <> 'erased'` |
| `email_verified_at` | `timestamp?` | Null until proven |
| `display_name_ciphertext` | `bytes?` **[ENC]** | Optional; PII |
| `status` | `enum(pending_verification, active, locked, pending_deletion, erased)` | See §4.4.1 |
| `locked_until` | `timestamp?` | Set by progressive lockout (§17.3) |
| `lock_reason` | `enum(failed_attempts, admin_action, security_hold)?` | |
| `dek_id` | `id?` | FK → `data_encryption_key`. Null once erased |
| `password_updated_at` | `timestamp?` | Drives credential-age reporting |
| `deletion_requested_at` | `timestamp?` | Starts the grace window (§15.4) |
| `erased_at` | `timestamp?` | Set when crypto-erasure completes |
| `created_at` | `timestamp` | |
| `updated_at` | `timestamp` | |

**Indexes:** unique on `email_index` (partial, excluding erased); on `status` where `status = 'pending_deletion'` (erasure job); on `deletion_requested_at` (erasure job).

#### 4.4.1 `status` semantics

| Status | Can authenticate | Sessions valid | Notes |
|---|---|---|---|
| `pending_verification` | **no — verification flow only** | none are issued | Entry state for a registration (§7.7). Purged after 7 days (R7.42) |
| `active` | yes | yes | Normal |
| `locked` | no | **no — existing sessions are rejected** | Lock **MUST** invalidate live sessions, not merely block new logins |
| `pending_deletion` | no | no | All sessions revoked at request time (§15.4) |
| `erased` | no | no | Tombstone only; all PII attributes are null and the DEK is destroyed |

- **R4.8** — A locked or pending-deletion principal **MUST** fail session validation at stage 7 of §3.4. Blocking only the login path while live sessions continue is a P0 authorization defect.
- **R4.8a** — `pending_verification` **MUST** be a `status` value rather than an inference from a null `email_verified_at`. R7.41 forbids an unverified account from authenticating beyond the verification flow, and R4.8's stage-7 check is where that is enforced; a state the status column cannot hold cannot be checked there, and the rule degrades into a per-endpoint convention. This state **MUST** fail stage 7 on the same terms as `locked`.

### 4.5 Entity: `admin`

The admin-plane principal. Structurally separate from `user` (INV-3).

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `email_ciphertext` | `bytes` **[ENC]** | |
| `email_index` | `bytes` **[BIDX]** | **UNIQUE** |
| `display_name_ciphertext` | `bytes` **[ENC]** | |
| `status` | `enum(pending_enrollment, active, suspended, offboarded)` | |
| `enrollment_completed_at` | `timestamp?` | Set only when ≥2 authenticators registered (§9.4) |
| `dek_id` | `id` | FK → `data_encryption_key` |
| `last_authenticated_at` | `timestamp?` | Feeds dormancy review |
| `created_at` / `updated_at` | `timestamp` | |

- **R4.9** — An `admin` **MUST NOT** have a password attribute of any kind. No password column, no password credential row, no reset path (§7.2, §9.4).
- **R4.10** — An admin in `pending_enrollment` **MUST NOT** be able to establish a session or exercise any permission.

### 4.6 Entity: `credential`

Polymorphic authentication credentials for `user` and `admin` principals.

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `principal_type` | `enum(user, admin)` | |
| `principal_id` | `id` | FK → `user.id` or `admin.id` |
| `kind` | `enum(password, passkey, totp, federated)` | |
| `label` | `text?` | User-supplied name, e.g. "YubiKey — work". PII-adjacent; treat as user content |
| `secret_material` | `bytes` **[ENC]** or **[HASH]** | See §4.6.1 |
| `public_key` | `bytes?` | Passkey only |
| `credential_ref` | `text?` | Passkey credential ID, or federated subject identifier |
| `provider` | `text?` | Federated only: the connection identifier |
| `aaguid` | `bytes?` | Passkey authenticator model identifier |
| `transports` | `json?` | Passkey transport hints |
| `sign_count` | `int?` | Passkey signature counter (§7.3.4) |
| `backup_eligible` | `bool?` | Passkey BE flag — governs admin acceptance (§7.3.5) |
| `backup_state` | `bool?` | Passkey BS flag |
| `is_verified` | `bool` | TOTP: enrollment confirmed. Federated: provider asserted a verified email |
| `last_used_at` | `timestamp?` | |
| `last_used_counter` | `int?` | TOTP replay prevention (R7.23) |
| `created_at` | `timestamp` | |
| `revoked_at` | `timestamp?` | Soft-revoke; the row remains for audit correlation until principal erasure |

**Indexes:** unique on (`kind`, `credential_ref`) where `kind IN ('passkey','federated')` and `revoked_at IS NULL`; on (`principal_type`, `principal_id`, `kind`) where `revoked_at IS NULL`.

**Constraints:** at most one active `password` credential per principal; at most one active `totp` credential per principal; zero `password` and zero `totp` credentials permitted where `principal_type = 'admin'` (**enforced at the storage layer**, not only in application code).

#### 4.6.1 `secret_material` by kind

| Kind | Content | Protection |
|---|---|---|
| `password` | KDF output including algorithm, parameters, and salt | **[HASH]** — a one-way KDF digest (§5.3). Never encrypted-and-reversible, never plaintext |
| `totp` | The shared secret | **[ENC]** — reversible encryption is required because verification needs the secret; wrapped by the principal's DEK |
| `passkey` | Unused (null) | Public key lives in `public_key`; no secret is held server-side |
| `federated` | Unused (null) | No provider tokens are retained (§7.6.5) |

### 4.7 Entity: `session`

The authoritative session record for `user` and `admin` principals.

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK. Never transmitted alone as a credential |
| `token_hash` | `bytes` **[HASH]** | SHA-256 of the presented session secret. **UNIQUE**. The plaintext secret is never stored |
| `principal_type` | `enum(user, admin)` | Immutable after creation (INV-2) |
| `principal_id` | `id` | |
| `device_id` | `id?` | FK → `device`. Required for native clients (§6.7) |
| `transport` | `enum(cookie, bearer)` | Fixed at issuance; a session **MUST NOT** be presentable over the other transport |
| `amr` | `json` | Authentication methods actually used, e.g. `["pwd","otp"]`. Ordered, deduplicated |
| `acr` | `enum(aal1, aal2)` | Assurance level reached (§8.6) |
| `csrf_token_hash` | `bytes?` **[HASH]** | Cookie transport only (§6.5.4) |
| `created_at` | `timestamp` | |
| `last_seen_at` | `timestamp` | Drives idle timeout; write-throttled (§6.6.4) |
| `absolute_expires_at` | `timestamp` | Never extended (§6.3) |
| `idle_expires_at` | `timestamp` | Recomputed on activity |
| `stepped_up_at` | `timestamp?` | Last successful step-up (§8.5) |
| `revoked_at` | `timestamp?` | |
| `revoked_reason` | `enum(logout, logout_all, admin_revoke, password_change, credential_change, deletion_request, lock, break_glass_close, rotation)?` | |
| `ip_hash` | `bytes?` **[HASH]** | Keyed hash of the origin address (§5.6) |
| `user_agent_hash` | `bytes?` **[HASH]** | Keyed hash |

**Indexes:** unique on `token_hash`; on (`principal_type`, `principal_id`) where `revoked_at IS NULL`; on `absolute_expires_at` (retention job); on `device_id`.

### 4.8 Entity: `device`

Per-principal device registry, enabling "sign out this phone" (§6.7).

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK. **Server-generated.** A client-supplied device identifier **MUST NOT** be trusted or persisted as the key |
| `principal_type` / `principal_id` | | |
| `platform` | `enum(web, ios, android, other)` | |
| `label` | `text?` | User-editable |
| `client_version` | `text?` | Coarse; no fingerprinting beyond what is displayed to the user |
| `first_seen_at` / `last_seen_at` | `timestamp` | |
| `revoked_at` | `timestamp?` | Revoking a device revokes all its sessions |

- **R4.11** — Only attributes shown back to the user in the device list may be stored. Collecting fingerprinting signals the user never sees violates data minimization (§25.5) and **MUST NOT** be done.

### 4.9 Entity: `one_time_credential`

Email OTP codes, magic links, email-verification tokens, password-reset tokens, admin-recovery approval tokens, and export download tokens.

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `purpose` | `enum(login_otp, magic_link, email_verify, email_change, password_reset, admin_recovery, export_download)` | |
| `principal_type` / `principal_id` | | Nullable for pre-account flows |
| `token_hash` | `bytes` **[HASH]** | **UNIQUE**. Plaintext never stored |
| `context_hash` | `bytes?` **[HASH]** | Binds the credential to its originating request context (R7.16) |
| `target_ciphertext` | `bytes?` **[ENC]** | For `email_change`: the new address |
| `attempts` | `int` | Default 0 |
| `max_attempts` | `int` | Default 5 |
| `expires_at` | `timestamp` | |
| `consumed_at` | `timestamp?` | Single-use enforcement |
| `created_at` | `timestamp` | |

**Indexes:** unique on `token_hash`; on `expires_at` (retention job); on (`purpose`, `principal_id`) where `consumed_at IS NULL`.

- **R4.12** — Consumption **MUST** be atomic: a single conditional write that sets `consumed_at` only where it is currently null. A read-then-write sequence permits a race that redeems one credential twice, which is a P1 defect.

### 4.10 Entity: `recovery_code`

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `principal_type` / `principal_id` | | |
| `code_hash` | `bytes` **[HASH]** | Hashed with the password KDF, not a bare digest — these are low-entropy relative to a random token |
| `consumed_at` | `timestamp?` | |
| `generation` | `int` | Regeneration invalidates every prior generation atomically |
| `created_at` | `timestamp` | |

### 4.11 Entity: `role`, `permission`, `role_permission`, `principal_role`

The authorization catalog (§11).

**`permission`** — `id`, `name` (`text`, **UNIQUE**, `resource.action` form), `plane` (`enum(user, admin, service)`), `description` (`text`), `is_sensitive` (`bool` — requires step-up, §8.5).

**`role`** — `id`, `name` (`text`, **UNIQUE** within plane), `plane`, `description`, `is_system` (`bool` — system roles are immutable at runtime).

**`role_permission`** — `role_id`, `permission_id`. Composite PK.

**`principal_role`** — `id`, `principal_type`, `principal_id`, `role_id`, `granted_by_type`, `granted_by_id`, `granted_at`, `expires_at?` (time-boxed grants, used by break-glass §12.5), `revoked_at?`.

**Indexes:** on (`principal_type`, `principal_id`) where `revoked_at IS NULL`; on `expires_at` where not null (expiry job).

- **R4.13** — The role↔permission catalog is **declared in code as the source of truth** and reconciled into the database by migration. It **MUST NOT** be editable through any runtime API. This makes the effective permission set reviewable in version control and diffable in an audit.

### 4.12 Entity: `audit_event`

Tamper-evident, append-only (§16).

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `seq` | `int` | Strictly monotonic, gap-free, per chain. **UNIQUE** |
| `chain_id` | `text` | Chain partition identifier (§16.5) |
| `occurred_at` | `timestamp` | |
| `actor_type` | `enum(user, admin, service, system)` | |
| `actor_id` | `id?` | Null for `system` |
| `action` | `text` | Stable dotted verb from the catalog (§16.6) |
| `target_type` | `text?` | |
| `target_id` | `id?` | |
| `outcome` | `enum(success, failure, denied)` | |
| `reason` | `text?` | Machine code, never free-form PII |
| `justification` | `text?` | Operator-supplied; required for break-glass (§12.5) |
| `request_id` | `text?` | Correlation identifier |
| `actor_ip_hash` | `bytes?` **[HASH]** | |
| `metadata` | `json?` | Identifiers and codes only — **never PII** (§16.4) |
| `prev_hash` | `bytes` | Hash of the preceding record in the chain |
| `record_hash` | `bytes` | This record's hash (§16.5) |

**Indexes:** unique on (`chain_id`, `seq`); on (`target_type`, `target_id`, `occurred_at`); on (`actor_type`, `actor_id`, `occurred_at`); on `occurred_at`.

- **R4.14** — The application's database principal **MUST** hold `INSERT` and `SELECT` privileges on this table and **MUST NOT** hold `UPDATE`, `DELETE`, or `TRUNCATE`. This is enforced by a grant in the migration, not by application discipline. Retention pruning (§23.3) runs under a separate, restricted maintenance principal.

### 4.13 Remaining entities

**`auth_attempt`** — `id`, `identifier_hash` **[HASH]**, `principal_type`, `principal_id?`, `method` (`enum(password, passkey, otp, totp, federated, recovery_code, service_credential)`), `outcome` (`enum(success, failure)`), `failure_code?`, `ip_hash` **[HASH]**, `occurred_at`. Indexes on (`identifier_hash`, `occurred_at`) and (`ip_hash`, `occurred_at`). Drives lockout (§17.3) and the user-visible security-event list.

**`security_event`** — `id`, `principal_type`, `principal_id`, `kind` (`enum(new_device_login, password_changed, password_reset_triggered, email_changed, mfa_enrolled, mfa_removed, passkey_added, passkey_removed, federated_linked, federated_unlinked, recovery_used, sessions_revoked, account_locked, account_unlocked, deletion_requested, deletion_cancelled)`), `occurred_at`, `notified_at?`, `metadata` `json?`. Backs both the notification pipeline (§18) and the user-facing security-events endpoint.

**`legal_document`** — `id`, `kind` (`enum(terms_of_service, privacy_policy, dpa)`), `version` (`text`), `locale` (`text`), `content_hash` (`bytes`), `effective_from` (`timestamp`), `requires_reconsent` (`bool`), `created_at`. Unique on (`kind`, `version`, `locale`).

**`consent_record`** — `id`, `principal_type`, `principal_id`, `document_kind`, `document_version`, `locale`, `accepted_at`, `method` (`enum(registration, reconsent_gate, settings)`), `ip_hash` **[HASH]**, `user_agent_hash` **[HASH]**, `purpose` (`text`, defaulted — the §14.5 seam), `withdrawn_at?`. Index on (`principal_type`, `principal_id`, `document_kind`).

**`data_encryption_key`** — `id`, `principal_type`, `principal_id`, `wrapped_key` (`bytes` — DEK wrapped by the KMS KEK), `kek_id` (`text`), `algorithm` (`text`), `created_at`, `rotated_at?`, `destroyed_at?`. See §5.4.

**`data_export`** — `id`, `principal_type`, `principal_id`, `status` (`enum(pending, running, ready, expired, failed)`), `requested_at`, `completed_at?`, `expires_at`, `artifact_ref?` (`text` — storage pointer, not content), `artifact_size_bytes?`, `download_count` (`int`), `error_code?`.

**`service_account`** — `id`, `name` (`text`, **UNIQUE**), `description`, `status` (`enum(active, suspended, retired)`), `owner_admin_id`, `created_at`, `last_used_at?`.

**`service_credential`** — `id`, `service_account_id`, `client_id` (`text`, **UNIQUE**), `secret_hash` **[HASH]** or `public_key` (`bytes`), `algorithm`, `created_at`, `expires_at`, `rotated_from_id?`, `revoked_at?`, `last_used_at?`. Index on `expires_at` (rotation warning job).

**`break_glass_activation`** — `id`, `admin_id`, `role_id`, `justification` (`text`, min 20 chars — enforced by constraint), `activated_at`, `expires_at`, `closed_at?`, `closed_by_admin_id?`, `review_status` (`enum(pending_review, reviewed, flagged)`), `reviewed_at?`, `reviewed_by_admin_id?`, `alert_sent_at?`.

**`admin_recovery_request`** — `id`, `admin_id`, `requested_at`, `verification_method` (`text`), `approver_admin_id?`, `approved_at?`, `enrollment_deadline?`, `status` (`enum(pending, approved, completed, rejected, expired)`), `justification` (`text`).

**`rate_limit_counter`** — only if no cache tier is available (§17.2). `key_hash` (`bytes`, PK), `window_start` (`timestamp`), `count` (`int`), `blocked_until` (`timestamp?`). Index on `window_start` for pruning.

### 4.14 Forward compatibility

- **R4.15** — Every table holding principal-owned data **MUST** carry `principal_type` alongside `principal_id`, even where only one type can currently appear. A bare `user_id` forecloses the admin plane and the future tenancy option.
- **R4.16** — Ownership checks **MUST** be routed through a single ownership predicate helper (§11.5). If tenancy is introduced later, exactly one function changes rather than every query site.
- **R4.17** — Every principal table **SHOULD** carry a `region` attribute defaulted to the single deployment region, so residency enforcement (§5.7) can be activated without a migration.

---

## 5. Cryptography and key management

### 5.1 Governing rules

- **R5.1** — All cryptographic operations **MUST** go through the single crypto provider module (R3.2). No cryptographic primitive is invoked elsewhere.
- **R5.2** — All randomness for tokens, secrets, salts, nonces, and identifiers **MUST** come from a cryptographically secure random source. A general-purpose PRNG used anywhere in the auth module is a P0 defect.
- **R5.3** — All comparisons of secrets, digests, tokens, and signatures **MUST** be constant-time. A short-circuiting equality operator on any secret is a defect.
- **R5.4** — Prohibited primitives: MD5, SHA-1 (except within the HIBP-style k-anonymity range protocol of §17.4, and TOTP's RFC-6238 HMAC-SHA-1 default), DES, 3DES, RC4, ECB mode, and any unauthenticated encryption mode. Encryption **MUST** be authenticated (AEAD).
- **R5.5** — When the deployment is designated FIPS-constrained, every primitive **MUST** be sourced from a FIPS-validated module and the FIPS variants in §5.3 apply. The active mode **MUST** be recorded in the configuration reference and asserted at startup (§24.3).

### 5.2 Key hierarchy

```
KMS/HSM root key (never leaves the KMS)
   │
   ├── KEK: data       → wraps per-principal DEKs                  (§5.4)
   ├── KEK: index      → derives the blind-index key               (§5.5)
   ├── KEK: pseudonym  → derives IP/user-agent hashing keys        (§5.6)
   └── Signing keys    → access assertions and audit checkpoints   (§5.8)
```

- **R5.6** — Root keys **MUST** reside in an external KMS/HSM and **MUST NOT** be exportable. There is no unmanaged-key mode for any deployed environment.
- **R5.7** — A local-development key provider **MAY** exist. It **MUST** be a distinct, clearly-named implementation; it **MUST** refuse to initialize when any indicator of a deployed environment is present; and startup validation (§24.3) **MUST** fail closed if it is active outside local development.

### 5.3 Password hashing

- **R5.8** — Default: **Argon2id**, minimum parameters `m = 19456 KiB`, `t = 2`, `p = 1`, 128-bit random salt, 256-bit output. Parameters are calibrated per deployment to a target of 100–250 ms on production hardware and recorded in the configuration reference.
- **R5.9** — FIPS-constrained deployments: **PBKDF2-HMAC-SHA-512**, minimum 600,000 iterations, 128-bit salt. Argon2id is not FIPS-validated; this substitution is the documented, required deviation.
- **R5.10** — The algorithm, its parameters, and the salt **MUST** be stored alongside the digest so parameters can be raised later. On a successful authentication with an outdated parameter set, the digest **MUST** be transparently recomputed at current parameters.
- **R5.11** — KDF invocation **MUST NOT** block the runtime's main execution thread, and concurrent KDF operations **MUST** be bounded by an explicit semaphore or worker pool. An unbounded memory-hard KDF is a trivial CPU/memory exhaustion vector — this is simultaneously a security and a P0 performance defect (§22.4).
- **R5.12** — Password policy: minimum 12 characters (15 recommended); maximum **not below** 64; all Unicode including spaces accepted; NFKC normalization before hashing; **no** composition rules; **no** forced periodic rotation; rejection only for breach-list membership (§17.4) or containment of the account identifier. Paste **MUST NOT** be blocked (§21.4).

### 5.4 Field encryption and envelope scheme

- **R5.13** — Every `[ENC]` attribute **MUST** be encrypted with **AES-256-GCM** (or an equivalently strong AEAD) using the owning principal's DEK.
- **R5.14** — The DEK is generated per principal, wrapped by the KMS `data` KEK, and stored only in wrapped form in `data_encryption_key.wrapped_key`. The unwrapped DEK **MUST NOT** be persisted anywhere, and **MUST NOT** be held in a process-global cache without a bounded-size, short-TTL eviction policy (§22.8).
- **R5.15** — Every encryption operation **MUST** bind additional authenticated data (AAD) composed of `entity_name || attribute_name || principal_id`. This makes a ciphertext structurally unusable if relocated to another row or column — without it, an attacker with write access can transplant one user's encrypted email onto another's record.
- **R5.16** — The stored ciphertext envelope **MUST** carry a version marker, the `kek_id`, and the IV/nonce, so key rotation and algorithm migration are possible without ambiguity.
- **R5.17** — Nonces **MUST** be unique per key. Never reuse a nonce with the same DEK.

### 5.5 Blind index for encrypted lookup

Encrypted email cannot be searched, but login requires exact-match lookup.

- **R5.18** — `email_index = HMAC-SHA-256(index_key, normalize(email))`, where `index_key` is derived from the KMS `index` KEK and is **distinct** from any DEK. `normalize` = trim, NFKC, lowercase the domain (and lowercase the local part, which **MUST** be applied consistently and documented as an intentional deviation from strict RFC 5321 local-part case sensitivity).
- **R5.19** — The blind index is a pseudonymous identifier and is therefore personal data. It **MUST** be deleted during erasure (§15.5); leaving it behind leaves a durable, correlatable identifier for a user who asked to be forgotten.
- **R5.20** — The blind index **MUST NOT** be used as a display value, returned in any API response, or written to any log.

### 5.6 IP address and user-agent handling

- **R5.21** — Raw IP addresses are personal data. They **MUST NOT** be stored in plaintext in any table in §4. Store `HMAC-SHA-256(pseudonym_key, ip)` truncated to 16 bytes.
- **R5.22** — The pseudonym key **MUST** be rotated on a schedule (default: 90 days), which structurally caps how far back addresses can be correlated. Rotation is a deliberate privacy control, not an inconvenience.
- **R5.23** — Raw addresses **MAY** exist transiently in memory for rate-limit evaluation within a single request. They **MUST NOT** be logged or persisted.

### 5.7 Data residency

- **R5.24** — Single deployment region. All persistence, cache, key management, backup, and log destinations **MUST** reside in that region.
- **R5.25** — Every outbound integration (email transport, breach-list provider, KMS) **MUST** be recorded in the third-party data-flow register (§25.6) with the categories of data it receives and its processing location.
- **R5.26** — The residency enforcement point **MUST** be a single documented location in the code, so activating multi-region is a change in one place, not an audit of every query.

### 5.8 Signing keys and rotation

- **R5.27** — Access assertions (§6.4) are signed with **EdDSA (Ed25519)** by default, or **ES256** in FIPS-constrained deployments. Symmetric signing (`HS*`) is forbidden for any assertion crossing a service boundary.
- **R5.28** — Verification **MUST** pin the expected algorithm from server configuration. The token header's `alg` **MUST NOT** select the verification algorithm. `alg: none` **MUST** be rejected unconditionally. Both are classic algorithm-confusion bypasses and are P0 defects.
- **R5.29** — Verification **MUST** additionally assert `iss`, `aud`, `exp`, `nbf` (with ≤60 s clock skew), and `typ`. A signature check alone is insufficient.
- **R5.30** — Signing keys rotate on a schedule (default 90 days) with an overlap window of at least the maximum assertion lifetime plus the JWKS cache TTL, so in-flight assertions never fail mid-rotation. Retired keys are removed from the published key set only after the overlap elapses.
- **R5.31** — Every key **MUST** carry a stable `kid`; assertions **MUST** include it; verifiers **MUST** select the key by `kid` and **MUST NOT** trust key material embedded in a token header (`jwk`, `jku`, `x5u` **MUST** be rejected).

---

## 6. Sessions and tokens

### 6.1 Model

Sessions are **authoritative server-side records** (§4.7). The credential the client holds is an opaque reference, never a self-describing bearer of authority. This yields immediate, complete revocation — which is what makes lock, logout-all, credential-change invalidation, and deletion actually effective.

### 6.2 Session secret

- **R6.1** — The session secret **MUST** be ≥256 bits of CSPRNG output, encoded URL-safely.
- **R6.2** — Only `SHA-256(secret)` is stored (`session.token_hash`). Lookup is by that digest. A database disclosure **MUST NOT** yield usable session credentials.
- **R6.3** — The secret **MUST NOT** appear in any URL, query parameter, log line, error message, analytics payload, or crash report.

### 6.3 Lifetimes

| Principal | Idle timeout | Absolute lifetime | Notes |
|---|---|---|---|
| `user` | 30 days, sliding | 90 days | Sliding renewal on activity |
| `admin` | **15 minutes** | **8 hours** | Non-negotiable ceiling |
| `service` | n/a | ≤15 minutes per token | Re-issued from client credentials (§13) |

- **R6.4** — `absolute_expires_at` is set once at issuance and **MUST NEVER** be extended. Activity extends only `idle_expires_at`. An absolute cap that renews is not an absolute cap.
- **R6.5** — Both timeouts **MUST** be enforced server-side on every validation. Client-side expiry handling is a UX affordance only.
- **R6.6** — Values are configuration with these as **defaults and hard ceilings**. Configuration may shorten them; it **MUST NOT** lengthen them past these values (§24.2).
- **R6.7** — Step-up freshness (§8.5) is independent and much shorter: 15 minutes for users, 5 minutes for admins.

### 6.4 OIDC-compatible access assertions

For internal service-to-service verification without a session-store round trip.

- **R6.8** — A short-lived signed assertion **MAY** be minted from a valid session, lifetime ≤5 minutes (default 120 s).
- **R6.9** — Claims: `iss`, `sub` (principal id), `aud`, `exp`, `iat`, `jti`, `sid` (session id), `principal_type`, `amr`, `acr`, and `permissions`. Claim names follow standard OIDC semantics so conventional libraries verify them.
- **R6.10** — Publish `/.well-known/openid-configuration` and `/.well-known/jwks.json` containing only public verification material. These are the **only** unauthenticated, publicly cacheable endpoints (§22.7).
- **R6.11** — Assertions **MUST NOT** be accepted for step-up-requiring, admin-plane, or privileged operations. Those paths **MUST** read the authoritative session record (§6.6.2).
- **R6.12** — Assertions **MUST NOT** be issued to browsers or native clients as their primary credential. They are an internal service-boundary mechanism.

### 6.5 Transport

#### 6.5.1 Web — `transport` is `cookie`

- **R6.13** — Attributes: `HttpOnly`, `Secure`, `SameSite=Lax` for the user plane and `SameSite=Strict` for the admin plane, `Path=/`, and the `__Host-` name prefix (which forbids `Domain` and mandates `Path=/` and `Secure`).
- **R6.14** — Cookies **MUST NOT** be scoped to a parent domain shared with untrusted subdomains.
- **R6.15** — Session cookies **MUST** be non-persistent for the admin plane.

#### 6.5.2 Native — `transport` is `bearer`

- **R6.16** — `Authorization: Bearer <secret>`. Never a cookie, never a query parameter, never a custom header that intermediaries may log.

#### 6.5.3 Transport binding

- **R6.17** — `session.transport` is fixed at issuance. A cookie-issued session presented as a bearer token (or vice versa) **MUST** be rejected. A request presenting both a session cookie and an `Authorization` header **MUST** be rejected outright rather than resolved by precedence — silent precedence is a session-fixation and CSRF-confusion vector.

#### 6.5.4 CSRF

- **R6.18** — Every state-changing request on the cookie transport **MUST** pass **both**: (a) `Origin`/`Sec-Fetch-Site` validation against an allowlist, and (b) a per-session CSRF token submitted in a header and compared constant-time against `session.csrf_token_hash`.
- **R6.19** — The CSRF token is issued at session creation, rotated on privilege-relevant events (step-up, credential change), and **MUST NOT** be readable by JavaScript from an `HttpOnly` cookie — it is delivered in the session-establishment response body and held in client memory.
- **R6.20** — Bearer-transport requests are exempt from CSRF token validation (they are not automatically attached by the browser) but **MUST** still validate `Origin` when one is present.

### 6.6 Validation path and performance

Target: **P95 ≤ 100 ms** for an authenticated read, **≤3 persistence round-trips** per request (§22.2).

#### 6.6.1 Cache-first resolution

1. Compute `token_hash`.
2. Read the cache under a namespaced key derived from that digest.
3. **On hit:** deserialize and **validate against a strict schema before any value reaches the authentication context.** A cache value that fails validation **MUST** be treated as a miss, evicted, and recorded as a security event. Trusting unvalidated cache content in an auth context is an explicit audit finding.
4. **On miss:** read the authoritative record, re-validate, populate the cache with TTL = min(60 s, remaining idle window).
5. Enforce all state assertions (§3.4 stages 6–8) against the resolved value.

#### 6.6.2 Mandatory authoritative reads

The cache **MUST** be bypassed and the authoritative record read for: any admin-plane request; any request requiring step-up; any permission or role mutation; any credential mutation; any deletion/erasure operation; and any break-glass-scoped action.

#### 6.6.3 No-cache fallback

If the project has no cache tier (§2.2), validation reads the authoritative store directly by the unique `token_hash` index. The connection-pool and statement-timeout requirements of §22.5 then become critical, and this **MUST** be recorded as a known scaling limitation in the configuration reference.

#### 6.6.4 Write amplification control

- **R6.21** — `last_seen_at` **MUST NOT** be written on every request. Write only when it has advanced by more than a threshold (default 60 s). Unthrottled, this converts every read into a write and is a P0 database-load defect.

#### 6.6.5 Invalidation

- **R6.22** — Every revocation path (§6.8) **MUST** invalidate the cache entry **before or atomically with** the authoritative write. A revocation that leaves a stale cache entry alive for up to 60 s is a real authorization bypass window.

### 6.7 Device binding

- **R6.23** — Native clients **MUST** be issued a **server-generated** device identifier on first authentication, stored in platform secure storage and presented on subsequent authentications. A client-asserted device identifier is advisory only and **MUST NOT** be trusted for authorization.
- **R6.23a** — `device.platform` is one of `web`, `ios`, `android`, `other`. It is set from the authenticated client's own registration, never from a request header — `other` exists so an unrecognised client is recorded honestly rather than mislabelled as `web`.
- **R6.24** — Every native session **MUST** reference a `device` row. Users **MUST** be able to list their devices and revoke any one, which revokes all of that device's sessions.
- **R6.25** — A first authentication from a previously unseen device **MUST** emit a `new_device_login` security event and notify the user (§18.2).

### 6.8 Revocation

- **R6.26** — These events **MUST** revoke sessions, with the stated scope, synchronously:

| Event | `revoked_reason` | Scope |
|---|---|---|
| Logout | `logout` | Current session |
| Logout-all | `logout_all` | All sessions for the principal |
| Password change or reset | `password_change` | All sessions except optionally the one performing the change |
| Passkey or TOTP added/removed | `credential_change` | All sessions except the one performing the change |
| Email change confirmed | `credential_change` | All sessions except the one performing the change |
| Account locked (any cause) | `lock` | All sessions |
| Deletion requested | `deletion_request` | All sessions |
| Admin revokes a user's sessions | `admin_revoke` | All sessions for that user |
| Device revoked | `admin_revoke` if an administrator revoked the device, else `logout_all` | All sessions bound to that device |
| Break-glass activation closed or expired | `break_glass_close` | All sessions carrying that grant |

`rotation` is the tenth value and is deliberately absent from this table: §6.9 rotation supersedes a session rather than revoking it, so it is recorded on the superseded row without being one of the revocation events above.

- **R6.27** — Revocation is a state transition on the authoritative record plus cache invalidation. It **MUST NOT** rely on token expiry.
- **R6.28** — Any outstanding access assertions (§6.4) minted from a revoked session remain valid for at most their ≤5-minute lifetime. This residual window is the documented reason R6.11 forbids assertions on privileged paths.

### 6.9 Session fixation and rotation

- **R6.29** — A new session secret **MUST** be minted (old record revoked with reason `rotation`) on: completion of authentication; completion of step-up/MFA; and any change to the principal's permission set.
- **R6.30** — A pre-authentication session identifier **MUST NEVER** be carried into the authenticated session.
- **R6.31** — The intermediate "authenticated with first factor, awaiting second factor" state **MUST** be represented by a distinct, short-lived (≤5 min), single-purpose credential that confers **no permissions whatsoever** and cannot be presented to any endpoint other than the MFA verification endpoints.

---

## 7. Authentication flows

### 7.1 Universal requirements

- **R7.1** — Every authentication attempt **MUST** be recorded in `auth_attempt` regardless of outcome, and **MUST** be admitted through rate limiting (§17) *before* any persistence access.
- **R7.2** — Failure responses **MUST** be uniform and non-enumerating (§19.5). The response **MUST NOT** reveal whether the account exists, which factor failed, whether the account is locked, or how many attempts remain.
- **R7.3** — Response timing **MUST** be substantially uniform between "no such account" and "wrong credential". Where a KDF would otherwise be skipped for a non-existent account, a dummy KDF of equal cost **MUST** be executed. Timing that discloses account existence is a user-enumeration oracle.
- **R7.4** — Successful authentication **MUST**, in order: record the attempt; mint a fresh session (§6.9); register/associate the device; evaluate the consent gate (§14.4); emit the audit event; emit a security event if the device is new.
- **R7.5** — All authentication responses **MUST** carry `Cache-Control: no-store` (§19.8).

### 7.2 Method availability by plane

| Method | `credential.kind` | User plane | Admin plane |
|---|---|---|---|
| Email + password | `password` | yes | **never** |
| Passkey / WebAuthn | `passkey` | yes | **required — sole method** |
| Magic link / email OTP | — (a `one_time_credential`, §7.4) | yes | **never** |
| Social OIDC | `federated` | yes | **never** |
| Enterprise SAML | `federated` | yes | **never** |
| TOTP | `totp` | as second factor | **never** (not phishing-resistant) |

- **R7.6** — The admin plane accepts **exactly one** authentication method: WebAuthn assertion with user verification. Every other method **MUST** be absent from the admin routing table — not merely disabled by configuration. Any code path that could authenticate an admin by password, OTP, or TOTP is a P0 defect against the phishing-resistance mandate (NIST SP 800-63B AAL3 / IA-2).

### 7.3 Passkey / WebAuthn

#### 7.3.1 Registration

1. Authenticated principal requests registration options.
2. Server generates a ≥16-byte random challenge, stores it server-side bound to the session with a ≤5-minute TTL, and returns options including RP ID, user handle, `excludeCredentials` (existing credentials, to prevent duplicate registration), and the required authenticator criteria.
3. Client produces an attestation response.
4. Server verifies: challenge matches and is unconsumed; `origin` is in the allowlist; RP ID hash matches; `type` is `webauthn.create`; user-present flag set; user-verified flag set where required; attestation statement verified per its format; the credential ID is not already registered.
5. Server persists a `credential` row with `kind = 'passkey'`.

- **R7.7** — The challenge **MUST** be server-generated, server-stored, single-use, and expiring. A client-supplied or stateless challenge defeats the entire protocol.
- **R7.8** — `origin` and RP ID **MUST** be validated against configuration, never derived from the request.

#### 7.3.2 Authentication

Same verification with `type = 'webauthn.get'`, plus signature verification against the stored public key and the sign-counter check of §7.3.4.

#### 7.3.3 User verification

- **R7.9** — Admin plane: `userVerification: "required"`, and the UV flag **MUST** be asserted in the response. An admin assertion without UV **MUST** be rejected.
- **R7.10** — User plane: `"preferred"`. When UV is present, the session records `acr = aal2` (§8.6).

#### 7.3.4 Signature counter

- **R7.11** — If the stored counter is non-zero and the presented counter is not greater, the assertion **MUST** be rejected and a security event emitted. This is the specified cloned-authenticator signal. Authenticators legitimately reporting 0 are exempt.

#### 7.3.5 Backup eligibility — admin constraint

- **R7.12** — Admin credentials **MUST** be device-bound: `backup_eligible = false`. A synced/multi-device passkey (`BE = true`) extends the admin trust boundary into a consumer cloud account and **MUST** be rejected at admin enrollment unless explicitly approved and recorded as a documented deviation in the configuration reference.

#### 7.3.6 Enrollment minimum

- **R7.13** — An admin **MUST** register **at least two** (`2`) authenticators before `status` leaves `pending_enrollment`. This is the primary defense against the admin lockout scenario (§9.4).

### 7.4 Magic link and email OTP

Every short-lived, single-use credential in this specification is a `one_time_credential` row, whatever flow issues it. `purpose` is the closed set of those flows:

| `purpose` | Issued by | Redeemed for |
|---|---|---|
| `login_otp` | A user requesting an email code to sign in | A session |
| `magic_link` | A user requesting a sign-in link | A session |
| `email_verify` | Registration (§7.7) | Marking `email_verified_at` |
| `email_change` | An email-change request (§7.8) | Confirming the new address |
| `password_reset` | A reset request (§9.1) or an admin trigger (§12.4) | Setting a new password |
| `admin_recovery` | An approved admin recovery request (§9.4) | Re-enrolling authenticators |
| `export_download` | A completed export (§15.2) | One artifact download |

- **R7.13a** — A flow needing a single-use credential **MUST** add a `purpose` value rather than reuse an unrelated one. Sharing a purpose across flows means a credential minted for one can be redeemed by another, which is a privilege-escalation path — an `export_download` credential accepted as a `password_reset` hands over the account.
- **R7.14** — Codes: ≥8 digits, or ≥256-bit tokens for links. Both stored only as `token_hash`.
- **R7.15** — TTL ≤10 minutes (default 5 minutes). Single-use, consumed atomically (R4.12). Maximum 5 verification attempts, after which the credential is destroyed.
- **R7.16** — **Cross-device binding:** the credential is bound to its originating request context via `context_hash`. Redeeming it from a different context **MUST** either be refused or require the user to confirm a displayed correlation value shown on both the requesting screen and in the email. Unbound magic links are directly phishable — an attacker induces the victim to request a code and relays it.
- **R7.17** — Requesting a code for a non-existent address **MUST** return the identical response, in comparable time, as for an existing one, and **MUST NOT** send mail.
- **R7.18** — Send-rate caps per §17.5 apply.
- **R7.19** — The email **MUST** state the purpose, the expiry, and an explicit "if you did not request this, ignore it" instruction. It **MUST NOT** contain any other personal data.

### 7.5 TOTP (second factor, user plane only)

- **R7.20** — RFC 6238; 6 digits; 30-second step; validation window of ±1 step (never wider — each extra step linearly increases guess surface).
- **R7.21** — Secret: ≥160 bits, generated server-side, stored `[ENC]` under the principal's DEK. Displayed to the user exactly once at enrollment.
- **R7.22** — Enrollment is confirmed only after the user successfully verifies a code. An unconfirmed TOTP credential **MUST NOT** be usable and **MUST NOT** count toward MFA satisfaction.
- **R7.23** — **Replay prevention:** the accepted time-step counter is stored in `last_used_counter`; a counter less than or equal to it **MUST** be rejected. Without this, an intercepted code is reusable for up to 90 seconds.
- **R7.24** — TOTP attempts are rate-limited independently of password attempts (§17.3). A 6-digit code is brute-forceable without a dedicated limit.
- **R7.25** — Enrolling or removing TOTP requires step-up (§8.5) and emits a security event and notification.

### 7.6 Social OIDC and enterprise SAML

#### 7.6.1 OIDC

- **R7.26** — Authorization Code flow with **PKCE (S256) mandatory for every client type**, including confidential web clients.
- **R7.27** — `state` **MUST** be cryptographically random, server-stored, single-use, and expiring, and validated on callback. `nonce` **MUST** be sent and validated against the ID token claim.
- **R7.28** — ID token validation: signature against the provider's published keys (fetched over TLS, cached with a bounded TTL); `iss` exact match; `aud` contains this client; `exp`/`iat` within ≤60 s skew; `nonce` matches; `azp` where present.
- **R7.29** — Redirect URIs **MUST** be exact-matched against a configured allowlist. Prefix, wildcard, or substring matching is an open-redirect and token-theft vector.
- **R7.30** — Native clients **MUST** use verified platform deep links (Universal Links / App Links). Custom URL schemes **MUST NOT** be used for OAuth callbacks — any other installed app can claim the scheme and intercept the authorization code (§20.6).

#### 7.6.2 SAML

- **R7.31** — Assertion signatures **MUST** be verified against a pre-configured IdP certificate. Certificates **MUST NOT** be accepted from the assertion itself.
- **R7.32** — The signature **MUST** cover the assertion; `SubjectConfirmationData` recipient, `Destination`, `Audience`, and `NotBefore`/`NotOnOrAfter` **MUST** all be validated; `InResponseTo` **MUST** match a stored, single-use request identifier; the assertion ID **MUST** be recorded to prevent replay.
- **R7.33** — XML processing **MUST** disable external entity resolution and DTD processing (XXE), and **MUST** use a signature-verification implementation resistant to XML Signature Wrapping. This is the single most historically exploited area of SAML and **MUST NOT** be hand-implemented (R2.2).

#### 7.6.3 Identity linking

- **R7.34** — On federated authentication where the asserted email matches an existing account:
  - If the provider asserts the email is **verified**, and the provider is in the trusted-verifier configuration list → link automatically, record `credential.is_verified = true`, emit a security event, notify the user.
  - Otherwise → **MUST NOT** link. Return a response directing the user to sign in with an existing method and add the provider explicitly from settings.
- **R7.35** — Provider trust for email verification is **explicit configuration per connection**, not an assumption. An `email_verified` claim from an unvetted provider is attacker-controlled, and auto-linking on it is the classic pre-registration account takeover.
- **R7.36** — Linking a new provider to an existing account from settings requires step-up (§8.5).
- **R7.37** — Unlinking **MUST** be refused when it would leave the account with no usable authentication method.

#### 7.6.4 Just-in-time provisioning

- **R7.38** — Creating a new account from a federated login **MUST** run the full registration path including the consent gate (§14.2). A federated user who never accepted the terms is a compliance gap.

#### 7.6.5 Provider tokens

- **R7.39** — Provider access and refresh tokens **MUST NOT** be persisted. They are consumed within the callback and discarded. Retaining them creates a high-value secret store with no authentication purpose (data minimization, §25.5).

### 7.7 Registration (user plane)

1. Rate-limit admission.
2. Validate the address format; normalize (R5.18).
3. Validate the password against R5.12 including the breach check (§17.4), where a password is being set.
4. Verify acceptance of the currently required legal documents; **reject** if absent (§14.2).
5. Create the DEK, then the `user` row, then the credential, then the consent records — in a single atomic transaction.
6. Issue an `email_verify` one-time credential and send it.
7. Return a **uniform** response.

- **R7.40** — The registration response **MUST** be identical whether or not the address was already registered. A distinguishable response is a user-enumeration oracle. Where the address exists, send a "someone tried to register with your address" notice to the existing owner instead of a verification link.
- **R7.41** — An unverified account **MUST NOT** be able to authenticate beyond the verification flow itself.
- **R7.42** — Unverified registrations **MUST** be purged after 7 days (§23.3).

### 7.8 Email change

- **R7.43** — Requires step-up. Sends a confirmation credential to the **new** address and a notice to the **old** address with a cancellation link. The change applies only on confirmation from the new address. Revokes all other sessions on completion. Emits a security event.

---

## 8. Multi-factor authentication and step-up

### 8.1 Policy

| Principal | Requirement |
|---|---|
| `admin` | **Mandatory.** Passkey with user verification is both the primary and the sole factor. There is no password to which a second factor is added |
| `user` | **Optional.** TOTP and/or passkeys may be enrolled voluntarily |

### 8.2 User-plane MFA

- **R8.1** — When a user has any confirmed second factor, password authentication **MUST** transition to the pending-MFA state (R6.31) and **MUST NOT** issue a full session until a factor is satisfied.
- **R8.2** — A passkey authentication with user verification satisfies both factors in one step; a second factor **MUST NOT** additionally be demanded.
- **R8.3** — The user **MUST** be able to enroll multiple factors and, where more than one exists, choose among them at the challenge.
- **R8.4** — Removing the last second factor requires step-up and emits a notification.

### 8.3 Admin-plane MFA

- **R8.5** — Every admin authentication is a WebAuthn assertion with UV. No fallback exists.
- **R8.6** — TOTP **MUST NOT** be registrable for an admin (enforced by the §4.6 storage constraint).

### 8.4 Recovery codes

- **R8.7** — 10 single-use codes, ≥128 bits of entropy each, issued when a user enrolls their first second factor, displayed exactly once, stored hashed with the password KDF (see §4.10: they are lower-entropy than random tokens and warrant KDF protection).
- **R8.8** — Regeneration invalidates every prior generation atomically.
- **R8.9** — Consuming a recovery code emits a security event, notifies the user, and **MUST** prompt for re-enrollment of a factor.
- **R8.10** — Recovery-code attempts are rate-limited on their own counter (§17.3).

### 8.5 Step-up authentication

Sensitive operations require a **fresh** authentication, not merely a valid session.

- **R8.11** — Freshness window: **15 minutes** (user), **5 minutes** (admin), measured from `session.stepped_up_at`.
- **R8.12** — Operations requiring step-up (permission rows carry `is_sensitive = true`):

| Operation | Plane |
|---|---|
| Change password | user |
| Change email address | user |
| Enroll or remove any second factor / passkey | both |
| Regenerate recovery codes | user |
| Link or unlink a federated provider | user |
| Request data export | user |
| Request account deletion | user |
| Revoke all sessions or a device | user |
| **Any** admin-plane mutation | admin |
| View another principal's personal data | admin |
| Activate break-glass | admin |
| Create, rotate, or revoke a service credential | admin |

- **R8.13** — Step-up **MUST** re-verify a real authentication factor. Re-entering the current password satisfies it only where the user has no stronger factor enrolled; where a passkey or TOTP exists, the stronger factor **MUST** be used.
- **R8.14** — Step-up **MUST** be enforced server-side at the route. A client that merely displays a confirmation dialog satisfies nothing.
- **R8.15** — Successful step-up updates `stepped_up_at` and rotates the CSRF token; it does **not** extend `absolute_expires_at`.

### 8.6 Assurance levels

| `acr` | Meaning |
|---|---|
| `aal1` | Single factor: password, email OTP, or federated without a verified strong factor |
| `aal2` | Multi-factor, or a single phishing-resistant factor with user verification (passkey + UV) |

- **R8.16** — Admin sessions **MUST** always be `aal2`. An admin session recorded at `aal1` is a defect.
- **R8.17** — `acr` and `amr` **MUST** be recorded on the session and propagated into access assertions so downstream services can enforce their own assurance requirements.

---

## 9. Account recovery

Recovery is the documented bypass of every factor above. It is specified with matching rigor.

### 9.1 User password reset

1. Request accepted for any submitted address; response is uniform and timing-comparable (R7.3), whether or not the account exists.
2. If the account exists, issue a `password_reset` one-time credential: ≥256 bits, TTL ≤15 minutes, single-use, stored hashed.
3. On redemption, the new password is validated per R5.12.
4. **If the account has any confirmed second factor, that factor MUST be satisfied before the reset completes** (R9.1).
5. All sessions are revoked; a security event is emitted; the user is notified at the previous address.

- **R9.1** — A password reset **MUST NOT** bypass enrolled MFA. Email possession alone resetting a fully-protected account reduces the entire security posture to the strength of the user's mail provider, and is an explicit MFA-bypass finding.
- **R9.2** — A reset **MUST NOT** remove, disable, or reset any second factor. Password recovery and factor recovery are separate problems with separate paths (§9.2).
- **R9.3** — Redeeming a reset credential **MUST NOT** by itself establish a session. The user re-authenticates.
- **R9.4** — Outstanding reset credentials for a principal **MUST** be invalidated when any one is consumed, and when the password changes by any other route.

### 9.2 User factor recovery (lost second factor)

- **R9.5** — Priority order: (a) another enrolled factor; (b) a recovery code; (c) if neither, **no self-service path exists** — the request goes to the administrative exception path (§15.6) with identity verification, full audit, and user notification.
- **R9.6** — Factor recovery **MUST NOT** be achievable by email possession alone.

### 9.3 Cooling-off and notification

- **R9.7** — Every recovery action **MUST** notify the principal at all verified contact points, including one it cannot itself invalidate where possible (§18.2).
- **R9.8** — Recovery-code consumption and administrative factor reset **MUST** additionally emit a `recovery_used` security event visible in the user's own security-events list.

### 9.4 Admin recovery (no password exists)

The scenario: an admin has lost every registered authenticator.

- **R9.9** — **Prevention first:** enrollment is incomplete until ≥2 authenticators are registered (R7.13), and admins **SHOULD** be periodically prompted to verify that a second authenticator is still in their possession.
- **R9.10** — **No self-service recovery path exists for the admin plane.** No email reset, no recovery codes, no support-initiated reset.
- **R9.11** — Total loss follows this path: (1) the admin submits an out-of-band request through a documented, identity-verified channel; (2) an `admin_recovery_request` is created; (3) **a different privileged operator** holding `admin.recovery.approve` verifies identity out-of-band and approves — self-approval **MUST** be structurally impossible; (4) approval opens a single-use, ≤15-minute enrollment window permitting **only** registration of new authenticators and nothing else; (5) both actors, the justification, and the outcome are audited; (6) all existing sessions and credentials for that admin are revoked.
- **R9.11a** — `admin_recovery_request.status` follows that path: `pending` on creation, then `approved` when a second operator authorizes it, then `completed` once the window is used. It terminates at `rejected` (identity not established) or `expired` (approved but unused before `enrollment_deadline`). `expired` **MUST NOT** be reopened — a new request is required, so that a stale approval cannot be redeemed later.
- **R9.12** — The enrollment window **MUST NOT** grant any permission other than authenticator registration. It is not a session.
- **R9.13** — Where organizational structure cannot guarantee a second available approver, the break-glass path (§12.5) is the designated fallback, with all of its alerting and mandatory post-use review. This dependency **MUST** be documented in the operational runbook (§26.4).

---

## 10. Account states and lifecycle

| State | Entered by | Can authenticate | Sessions | Exit |
|---|---|---|---|---|
| `pending_verification` | Registration | No (verification flow only) | None | Verify email → `active`; 7 days → purge |
| `active` | Verification / JIT provisioning | Yes | Valid | Lock, deletion request |
| `locked` | Failed-attempt threshold (`failed_attempts`), admin action (`admin_action`), or security hold (`security_hold`) — recorded in `user.lock_reason` | No | **Revoked** | Lockout elapses, or admin unlock |
| `pending_deletion` | User request or admin action | No | **Revoked** | Cancel → `active`; grace elapses → `erased` |
| `erased` | Erasure job | No | None | **Terminal** |

The admin plane has its own states — `admin.status` is a different enum from `user.status`, because an admin is enrolled rather than registered and is offboarded rather than erased:

| `admin.status` | Entered by | Can authenticate | Exit |
|---|---|---|---|
| `pending_enrollment` | Admin created by another admin | **No** — and holds no permissions (R4.10) | ≥2 authenticators registered (§9.4) → `active` |
| `active` | Enrollment completed | Yes | Suspension or offboarding |
| `suspended` | Admin action — a reversible hold, e.g. during an investigation | **No** | Reinstated → `active`, or → `offboarded` |
| `offboarded` | Admin action, when the person leaves | **No** | **Terminal.** Credentials revoked and service accounts repointed (R15.15b) |

- **R10.0a** — `suspended` and `offboarded` are distinct on purpose. Reusing one for the other either leaves a departed administrator reinstatable or destroys the ability to hold an account pending review. Neither state deletes the `admin` row; erasure of an admin as a data subject is R15.15b.
- **R10.1** — Every transition **MUST** emit an audit event and, where the principal is a user, a security event.
- **R10.2** — Automatic lockout **MUST** be time-bounded and self-releasing (§17.3). Indefinite automatic lockout converts a rate-limit control into a denial-of-service vector against legitimate users.
- **R10.3** — The `erased` state is terminal and irreversible. No code path may transition out of it.

---

## 11. Authorization

### 11.1 Model

**Roles expand to fine-grained named permissions.** Endpoints declare a required **permission**, never a role name.

- **R11.1** — No authorization check anywhere in the codebase may test a role name. `role == "admin"` is a defect. Every check tests permission membership.
- **R11.2** — The effective permission set is the union of permissions from all of the principal's non-revoked, non-expired role grants, computed **server-side from authoritative state** on every request.

### 11.2 Permission catalog

Permissions are named `resource.action` and declared in code (R4.13).

**User plane** (held implicitly by every active user for their own resources):

`profile.read`, `profile.write`, `credential.read`, `credential.write`, `session.read`, `session.revoke`, `device.read`, `device.revoke`, `consent.read`, `consent.write`, `data.export`, `account.delete`

**Admin plane:**

| Permission | Sensitive | Grants |
|---|---|---|
| `admin.user.list` | no | List users (identifiers and status only, never full PII) |
| `admin.user.read_pii` | **yes** | View a user's personal data — **audited on every read** (§16.2) |
| `admin.user.lock` | **yes** | Lock / unlock an account |
| `admin.user.revoke_sessions` | **yes** | Force sign-out |
| `admin.user.reset_mfa` | **yes** | Administrative factor reset (§9.2 exception path) |
| `admin.user.trigger_password_reset` | **yes** | Initiate a reset to the user's verified address |
| `admin.user.delete` | **yes** | Initiate deletion on a user's behalf |
| `admin.audit.read` | no | Read the audit trail |
| `admin.service_account.manage` | **yes** | Create / rotate / revoke service credentials |
| `admin.recovery.approve` | **yes** | Approve an admin recovery request (R9.11) |
| `admin.break_glass.activate` | **yes** | Activate emergency access (§12.5) |
| `admin.break_glass.review` | **yes** | Close and review an activation |
| `admin.role.grant` | **yes** | Grant / revoke admin roles |

- **R11.3** — Note that `admin.user.read_pii` is **separate** from `admin.user.list`. Bundling them would mean routine operational listing grants bulk personal-data access, which is a minimum-necessary-access failure under HIPAA and a data-minimization failure under GDPR.

### 11.3 System roles

| Role | Plane | Permissions |
|---|---|---|
| `user` | user | The implicit self-scoped set |
| `support_readonly` | admin | `admin.user.list`, `admin.audit.read` |
| `support_agent` | admin | + `admin.user.read_pii`, `admin.user.revoke_sessions`, `admin.user.trigger_password_reset` |
| `account_operator` | admin | + `admin.user.lock`, `admin.user.reset_mfa`, `admin.user.delete` |
| `security_admin` | admin | + `admin.service_account.manage`, `admin.recovery.approve`, `admin.break_glass.review`, `admin.role.grant` |
| `break_glass` | admin | Time-boxed superset; **grantable only through §12.5** |

- **R11.4** — `break_glass` **MUST NOT** be grantable through the ordinary role-grant path. It is issued exclusively by the break-glass activation flow with a mandatory `expires_at`.

### 11.4 Enforcement

- **R11.5** — **Every** endpoint declares its required permission, including endpoints believed to be safe. An endpoint with no declaration **MUST** fail closed (deny) and **MUST** fail the build. Absence of a declaration is never interpreted as "public"; public endpoints declare themselves public explicitly.
- **R11.6** — Permission checks execute **server-side, statelessly, per request**. UI-level hiding of controls is never an authorization control.
- **R11.7** — **Ownership is a second, independent gate.** Any endpoint touching a specific resource **MUST** verify that the resource belongs to the requesting principal — in the same query that fetches it, as a predicate. Fetch-then-compare is a defect: it discloses existence, invites time-of-check/time-of-use races, and is the exact pattern that produces insecure-direct-object-reference findings.
- **R11.8** — Every mutation **MUST** carry the ownership predicate in its `WHERE`/filter clause. An update or delete keyed solely on a resource identifier is a P0 cross-account mutation vector.
- **R11.9** — Admin permissions grant access **across** accounts by design. Each such access **MUST** therefore emit an audit event naming actor, action, target, and timestamp (§16.2). This is the compensating control that makes the cross-boundary grant defensible.

### 11.5 Ownership predicate indirection

- **R11.10** — All ownership checks **MUST** route through a single ownership-predicate helper that takes the principal context and the target entity and returns the storage-layer predicate. No query site constructs its own ownership condition. This makes the boundary auditable in one location and makes the future tenancy extension (§1.3) a single-site change.

### 11.6 Denial semantics

- **R11.11** — Authorization denial returns the generic error envelope. It **MUST NOT** distinguish "resource does not exist" from "you may not access it", because that distinction is an enumeration oracle across account boundaries.
- **R11.12** — Every denial **MUST** be audited with `outcome = 'denied'`. Denials are the primary signal of both attack and misconfiguration.

---

## 12. Admin plane

### 12.1 Isolation

- **R12.1** — The admin plane **MUST** be served on a separate route namespace (default `/v1/admin/*`) and **SHOULD** be served on a separate hostname so cookie scope is structurally disjoint (§6.5.1).
- **R12.2** — Admin endpoints **MUST** verify `principal_type == 'admin'` at stage 6 of §3.4, before any permission evaluation.
- **R12.3** — Admin routes **SHOULD** additionally be network-restricted (allowlist or private ingress) where deployment permits. This is defense in depth, never a substitute for authentication.
- **R12.4** — Admin sessions **MUST NOT** be cached for validation (§6.6.2) — always authoritative.

### 12.2 Session posture

15-minute idle, 8-hour absolute, 5-minute step-up freshness, non-persistent cookie, `SameSite=Strict`.

### 12.3 Reading user personal data

- **R12.5** — Every read of another principal's personal data **MUST** emit an audit event **before the data is returned**, and the emission failing **MUST** fail the request. Audit-then-serve, not serve-then-audit-best-effort: a lost audit write on a successful PII disclosure is precisely the non-repudiation failure the compliance framework prohibits.
- **R12.6** — Bulk listing (`admin.user.list`) **MUST** return only identifiers and status. It **MUST NOT** return decrypted personal data. Bulk PII retrieval **MUST NOT** be possible through any list endpoint.
- **R12.7** — List endpoints **MUST** be cursor-paginated with a maximum page size of 100 (§22.3).
- **R12.8** — Every list and search **MUST** be audited with the query parameters used, so a mass-enumeration pattern is reconstructable after the fact.

### 12.4 Account lifecycle actions

| Action | Permission | Step-up | Effect | Notifies user |
|---|---|---|---|---|
| Lock | `admin.user.lock` | yes | `status = locked`, all sessions revoked | yes |
| Unlock | `admin.user.lock` | yes | `status = active` | yes |
| Revoke sessions | `admin.user.revoke_sessions` | yes | All sessions revoked | yes |
| Reset MFA | `admin.user.reset_mfa` | yes | Second factors revoked; re-enrollment forced at next login | yes |
| Trigger password reset | `admin.user.trigger_password_reset` | yes | Reset credential sent **to the user's verified address only** | yes |
| Initiate deletion | `admin.user.delete` | yes | Enters `pending_deletion` (§15.4) | yes |

- **R12.9** — An administrator **MUST NOT** be able to set a user's password, read a user's password, read a TOTP secret, or receive a reset credential. Reset credentials go only to the user's own verified address. Any path where an operator both triggers and receives a credential is an account-takeover path.
- **R12.10** — Every one of these actions **MUST** notify the affected user (§18.2). Silent administrative action on an account is not defensible in a privacy audit.
- **R12.11** — Administrative MFA reset is a high-risk operation and **MUST** additionally emit a staff alert (§18.3).

### 12.5 Break-glass emergency access

- **R12.12** — Activation requires: the `admin.break_glass.activate` permission; step-up authentication; and a free-text justification of at least 20 characters (constraint-enforced).
- **R12.13** — Activation grants the `break_glass` role with a hard `expires_at` of **60 minutes** maximum. Expiry is enforced at permission resolution, not by a cleanup job — an expired grant **MUST** stop working immediately even if no job has run.
- **R12.14** — Activation **MUST** immediately alert a second party through a channel outside the application (§18.3). Alert dispatch failure **MUST NOT** silently succeed: if the alert cannot be sent, the activation is recorded and flagged for review, and this behaviour **MUST** be documented in the runbook.
- **R12.15** — Every action performed while a break-glass grant is active **MUST** be audited with the activation identifier attached, so the full blast radius is reconstructable.
- **R12.16** — On expiry or closure, all sessions carrying the grant are revoked (R6.26).
- **R12.16a** — Every activation **MUST** be reviewed after the fact. `review_status` starts at `pending_review` and a second party moves it to `reviewed` (the use was justified) or `flagged` (it was not, or could not be confirmed). `flagged` **MUST** raise a staff alert (§18.3). An activation that sits at `pending_review` indefinitely means the control exists on paper only — R12.14's alert is what makes the use visible, and this is what makes it answered.
- **R12.17** — Every activation enters `review_status = 'pending_review'` and **MUST** be closed out by a different operator holding `admin.break_glass.review`. Unreviewed activations older than 7 days **MUST** be surfaced as an operational alert.
- **R12.18** — Break-glass **MUST NOT** be usable as a routine workflow. Frequency **MUST** be reported in the operational runbook's review cadence.

### 12.6 Impersonation — prohibited

- **R12.19** — The framework **MUST NOT** implement user impersonation, "log in as", "view as user", or any mechanism producing a user-plane session for an administrative actor. Support workflows are served by audited PII reads (§12.3) and lifecycle actions (§12.4).
- **R12.20** — Should impersonation ever be required, it is a specification amendment, not an implementation detail. It would require at minimum: a distinct session type flagged as impersonated; a mandatory, non-dismissible UI indicator; a hard time limit; structural exclusion of credential, MFA, and export operations; dual-actor audit recording; and user notification. None of that is in scope here, and a partial implementation is worse than none.

---

## 13. Service accounts (machine-to-machine)

### 13.1 Model

- **R13.1** — Non-human callers authenticate as `service` principals with their own scoped permissions. Running a job as a shared administrative user destroys attribution and grants far more authority than the job needs; it **MUST NOT** be done.

### 13.2 Credentials

- **R13.2** — Either a high-entropy client secret (≥256 bits, stored only as a KDF digest) or an asymmetric key pair (public key stored; private key never transmitted to the server). Asymmetric is preferred.
- **R13.3** — Credentials **MUST** carry an `expires_at`, default 90 days, maximum 365. Non-expiring credentials are forbidden.
- **R13.4** — Rotation **MUST** support an overlap period during which both the old and new credential are valid, so rotation never requires downtime. `rotated_from_id` records the lineage.
- **R13.5** — Credential material is displayed **exactly once**, at creation. There is no retrieval endpoint.

### 13.3 Tokens

- **R13.6** — Service tokens are short-lived (≤15 minutes) signed assertions (§6.4) with `principal_type = 'service'`. Service principals **MUST NOT** be issued session records.
- **R13.7** — Every token request is rate-limited and audited.

### 13.4 Authorization

- **R13.8** — Service accounts use the same permission catalog. They **MUST** be granted the minimum permission set required and **MUST NOT** be granted any `is_sensitive` admin permission except by explicit, documented, reviewed exception.
- **R13.9** — A service principal **MUST NOT** hold `admin.break_glass.activate` or `admin.recovery.approve`. These require a human actor.

### 13.5 Hygiene

- **R13.10** — `last_used_at` is maintained (write-throttled per R6.21). Credentials unused for 90 days **MUST** be reported for review.
- **R13.10a** — `service_account.status` is `active`, `suspended`, or `retired`. `suspended` is a reversible hold that **MUST** cause immediate token rejection, not merely block new issuance. `retired` is terminal: its credentials are revoked and the identifier **MUST NOT** be reused, because audit history already refers to it.
- **R13.11** — Credentials approaching expiry (30/7/1 days) **MUST** raise operational alerts.

### 13.6 Extension seam

- **R13.12** — User-issued personal API tokens, if later required, reuse this model with `owner_principal_type = 'user'` and a permission set that is a **subset** of the issuing user's own — never a superset. The `service_account` table carries the owner columns to make this a non-breaking addition.

---

## 14. Consent and legal document versioning

### 14.1 Model

- **R14.1** — Legal documents are versioned records (`legal_document`) with an immutable content hash. Consent is recorded per principal, per document kind, per version (`consent_record`).
- **R14.1a** — `legal_document.kind` is `terms_of_service`, `privacy_policy`, or `dpa`. `consent_record.method` records **where** the consent was captured — `registration` (§14.2), `reconsent_gate` (§14.4), or `settings` (§14.5) — because a regulator asking how consent was obtained is asking for exactly this, and "the user accepted at some point" is not an answer.

### 14.2 Registration gate

- **R14.2** — Registration **MUST** verify acceptance of every currently-required document **server-side** before creating the account, and **MUST** persist a `consent_record` for each in the same transaction. A client-side checkbox with no server-side record is explicitly non-compliant.
- **R14.3** — Acceptance records the exact version, the timestamp, the acceptance method, and hashed origin metadata (§5.6) — enough to demonstrate what was agreed to and when.

### 14.3 Federated and native flows

- **R14.4** — Just-in-time provisioning (§7.6.4) and any native registration path **MUST** apply the identical gate. A path that creates accounts without consent records is a compliance gap regardless of how the user arrived.

### 14.4 Re-consent gate

- **R14.5** — When a document version with `requires_reconsent = true` becomes effective, middleware **MUST** block access at stage 8 of §3.4 for any principal lacking acceptance of that version.
- **R14.6** — The gate returns a distinct, machine-readable response (`consent_required`) enumerating which documents are outstanding, so any UI can render the flow.
- **R14.7** — The gate **MUST NOT** block: reading the outstanding documents; recording acceptance; data export; account deletion; or logout. **Withholding a data subject's rights until they accept new terms is itself a violation.**
- **R14.8** — The gate is server-enforced. A client that merely displays a modal satisfies nothing.

### 14.5 Withdrawal and granularity

- **R14.9** — `consent_record.purpose` exists and is defaulted, so purpose-level consent (marketing, analytics, optional processing) can be added without migration.
- **R14.10** — Where purpose-level consent is later enabled, withdrawal **MUST** be exactly as easy as granting — same number of steps, same surface.
- **R14.11** — Consent to the terms required to operate the service cannot be withdrawn while retaining the account; the withdrawal path for those is account deletion (§15.4), and the UI **MUST** state this plainly.

---

## 15. Data subject rights

### 15.1 Principle

- **R15.1** — Access, rectification, export, and erasure **MUST** be **self-service** for authenticated users, exercisable without human intervention. Architectures forcing administrative mediation for routine rights are a documented compliance deficit.

### 15.2 Right of access and portability (export)

- **R15.2** — Export **MUST** be complete: profile data; all credentials as metadata (kind, label, created, last used — **never** secret material); sessions; devices; consent records; security events; authentication attempt history; audit events where the principal is the target; and every application-domain record linked to the principal. Exporting only the profile row is a documented deficit.
- **R15.3** — Machine-readable, structured format with a documented schema.
- **R15.4** — Export **MUST** run as an asynchronous background job. Building an export inline in a request handler blocks the runtime and risks timeout.
- **R15.5** — The artifact **MUST** be produced by **streaming**, never by accumulating the full data set in memory. Buffering a full export is a memory-exhaustion vector proportional to the largest account.
- **R15.5a** — `data_export.status` tracks one request through `pending` (accepted, queued), `running` (artifact being built), and then exactly one terminal state: `ready` (downloadable until `expires_at`), `expired` (artifact purged, row kept so the request stays auditable), or `failed` (with `error_code`). The row **MUST** outlive the artifact — deleting it on expiry loses the record that a subject exercised the right at all.
- **R15.6** — Delivery is by a time-limited, single-use, unguessable download credential (≥256 bits) valid ≤7 days, requiring an authenticated session, and audited on every access.
- **R15.7** — The artifact **MUST** be encrypted at rest and **MUST** be destroyed on expiry by the retention job (§23.3). An export is a concentrated copy of everything about a person and is the highest-value object in the system.
- **R15.8** — Export requests are rate-limited (default: 1 per 24 hours per principal).
- **R15.9** — Requesting an export requires step-up (§8.5).

### 15.3 Right to rectification

- **R15.10** — Users **MUST** be able to correct their own profile data through authenticated endpoints. Identifier changes (email) follow the verification flow of §7.8.
- **R15.11** — Every rectification is audited with the field changed — **never the before/after values**, which would write the corrected personal data into an immutable 6-year store.

### 15.4 Right to erasure — grace period then cryptographic erasure

**Phase 1 — Request (immediate):**

1. Requires step-up.
2. `status = 'pending_deletion'`, `deletion_requested_at` set.
3. **All sessions revoked immediately.**
4. Login blocked, except a dedicated cancellation path.
5. Security event emitted; confirmation notification sent, stating the exact date of irreversible erasure.
6. Audit event emitted.

**Phase 2 — Grace window (default 30 days, configurable 0–30):**

- The user may cancel by authenticating through the cancellation path. Cancellation restores `active`, emits a security event, and notifies.
- No processing beyond retention occurs during the window.

**Phase 3 — Erasure (automatic, at window end):**

1. Destroy the principal's DEK: mark `destroyed_at` and remove the wrapped key material. **Every `[ENC]` attribute across every table becomes permanently undecryptable, including in every backup taken before this moment.** This is what makes erasure real rather than aspirational.
2. Null all `[ENC]` columns, all `[BIDX]` values (R5.19), and all `[HASH]` values derived from personal data.
3. Apply §15.4.1 to every table: delete every row it marks **delete**, and leave every row it marks **retain** in place with its principal reference rewritten to the tombstone.
4. Retain the `user` row as a **tombstone**: `id`, `status = 'erased'`, `erased_at`. It holds no personal data and exists solely to keep audit references non-dangling.
5. Rewrite `audit_event.actor_id`/`target_id` references — see R15.13.
6. Emit a final `user.erased` audit event with the tombstone identifier only.
7. Record completion so the erasure is demonstrable.

- **R15.12** — A pure soft-delete (a flag or timestamp leaving plaintext personal data recoverable) **MUST NOT** be used as the erasure mechanism. It is a direct violation of the right to erasure.
- **R15.13** — Audit records **MUST** survive erasure — they are required for 6 years (§23.2) and are the evidence that erasure occurred. Because they reference the tombstone identifier and contain **no personal data by construction** (R16.4), they become non-identifying automatically once the tombstone holds nothing. **This is the specific reason R16.4 forbids personal data in audit metadata**: any personal data written there would be unerasable, creating a direct and irreconcilable conflict between the retention obligation and the erasure obligation.
- **R15.14** — Downstream systems holding copies **MUST** be notified. Absent the deferred event stream (§1.3), the erasure job **MUST** invoke a documented, synchronous purge interface for every such system, and failure **MUST** raise an operational alert rather than being swallowed.
- **R15.15** — Erasure is idempotent and resumable. A partial failure **MUST** be retryable without corrupting a partially-erased record, and **MUST NOT** leave the account in a state where it is neither usable nor erased.

#### 15.4.1 Erasure disposition — every §4 table

Erasure is only real if it is exhaustive, and "delete the obvious tables" is how personal data survives an erasure job. This table answers the question once for every entity §4 declares. **not affected** is a positive finding — the table holds no personal data — not an omission.

| Table | Plane | Disposition | Reason |
|---|---|---|---|
| `user` | user | **retain** — tombstone | Phase 3 step 4. Holds `id`, `status`, `erased_at` and nothing else |
| `data_encryption_key` | both | **retain** — destroyed | Step 1 sets `destroyed_at` and drops `wrapped_key`. Deleting the row would destroy the evidence that the key was destroyed, which is the whole proof of erasure |
| `audit_event` | both | **retain** — rewritten | 6-year obligation (§23.2); contains no personal data by construction (R16.4); references point at the tombstone (R15.13) |
| `consent_record` | both | **retain** — rewritten | The record that consent was given and withdrawn is the accountability evidence for having processed the data at all. `ip_hash` and `user_agent_hash` are nulled by step 2; what remains is a document version, timestamps, and the tombstone reference |
| `credential` | both | **delete** | |
| `session` | both | **delete** | Already revoked in phase 1; the rows go here |
| `device` | user | **delete** | |
| `one_time_credential` | both | **delete** | |
| `recovery_code` | user | **delete** | |
| `principal_role` | both | **delete** | |
| `auth_attempt` | both | **delete** | Matched on `principal_id` **and** on `identifier_hash` for every address the principal held — a failed attempt carries no `principal_id`, so deleting by principal alone leaves the pre-identification rows behind |
| `security_event` | both | **delete** | It exists to notify the account holder and to populate their security-events view; both purposes end with the account. `audit_event` is the compliance record, not this |
| `data_export` | both | **delete** — row **and** artifact | The artifact behind `artifact_ref` is a complete copy of the principal's personal data. Deleting only the row leaves that copy in object storage; the purge **MUST** cover both |
| `admin_recovery_request` | admin | **delete** | `justification` is admin-authored free text about a named person |
| `break_glass_activation` | admin | **retain** — rewritten | Emergency-access evidence; `justification` is about the access, not the person, and the review trail is required independently of whether the admin still exists |
| `rate_limit_counter` | — | **not affected** | Keyed by `key_hash` with no principal reference; expires under §23.3 |
| `legal_document` | — | **not affected** | Product content — the terms themselves, not anyone's acceptance of them |
| `role` | — | **not affected** | Authorization catalog, declared in code (R4.13) |
| `permission` | — | **not affected** | Authorization catalog (R4.13) |
| `role_permission` | — | **not affected** | Authorization catalog (R4.13) |
| `service_account` | service | **not affected** | No natural person. `owner_admin_id` is repointed by R15.15b, not erased |
| `service_credential` | service | **not affected** | No natural person |
| `admin` | admin | **retain** — tombstone | Same shape as `user`; reached through R15.15b, not the user-plane path |

- **R15.15a** — This table **MUST** name every entity declared in §4. An entity that appears in §4 and not here is an unanswered erasure question, and CI fails on it (`authspec_check.py --only erasure`). When §4 gains an entity, this table gains a row in the same change — that is the point of the check.
- **R15.15b** — Admins are data subjects. An admin erasure **MUST** run the same phase 3 against the admin-plane rows of this table, with two additions: `service_account.owner_admin_id` **MUST** be repointed to a surviving admin **before** erasure (an ownerless service account is unrotatable), and any open `break_glass_activation` **MUST** be closed and reviewed first. There is no self-service admin erasure path; it is an operator procedure.

### 15.5 Backups

- **R15.16** — Cryptographic erasure is the designated mechanism for backup coverage. Backups **MUST NOT** retain unwrapped DEKs, and DEK destruction **MUST** occur in the key store, not merely in the application database — otherwise a database restore resurrects the key and undoes the erasure.
- **R15.17** — Backup retention and the restore procedure's interaction with erasure **MUST** be documented in the operational runbook (§26.4), including the requirement to re-apply pending erasures after any restore.

### 15.6 Administrative exception path

- **R15.18** — For a data subject locked out of their own account, an administrative path exists with: out-of-band identity verification; the `admin.user.delete` permission; step-up; full audit; and notification to the account's verified address.
- **R15.19** — This path **MUST NOT** be the default route. Its usage rate is a review metric — high usage indicates the self-service path is failing.

---

## 16. Audit trail

### 16.1 Requirements

- **R16.1** — Append-only and tamper-evident: a hash-chained record set the application can insert into but cannot modify (R4.14).

### 16.2 Auditable actions

Every one of these **MUST** emit an audit event, on both success and failure. `outcome` records which: `success` or `failure`. Emitting only the successes is the common shortcut and it removes exactly the evidence an investigation needs — a denied request and a failed step-up are findings, not noise.

`actor_type` names who acted — `user`, `admin` or `service` for a principal, and `system` for an action no principal initiated: the erasure job (§15.4), the retention pruners (§23.3), automatic lockout and its self-release (§17.3), and credential expiry. `system` exists so an automated write is never misattributed to whichever principal it happened to affect.

**Authentication:** login success/failure (per method), logout, logout-all, session revocation, step-up success/failure, MFA challenge success/failure, recovery code consumption.

**Credentials:** password set/change/reset, passkey registered/removed, TOTP enrolled/removed, recovery codes generated, federated provider linked/unlinked.

**Account:** created, email verified, email changed, profile rectified, locked, unlocked, deletion requested, deletion cancelled, erased.

**Authorization:** every **denied** request; every role granted, revoked, or expired.

**Administrative:** every admin login; **every read of another principal's personal data**; every list/search with its parameters; every lifecycle action; break-glass activation, use, expiry, closure, and review; every admin recovery request and approval.

**Service accounts:** created, credential issued, rotated, revoked, permission changed.

**Privacy:** export requested, completed, downloaded, expired; consent recorded and withdrawn.

**Configuration:** legal document version published; any change to a security-relevant configuration value.

### 16.3 Immutability

- **R16.2** — The application's database principal holds `INSERT` and `SELECT` only (R4.14), granted in the migration.
- **R16.3** — No API, service method, or administrative endpoint may expose update or delete on audit records. Retention pruning (§23.3) runs under a distinct maintenance principal, is itself audited, and prunes only by age.

### 16.4 Content rules

- **R16.4** — Audit records **MUST NOT** contain personal data. Store identifiers, action codes, and outcome codes. Never an email address, name, password, token, secret, or raw IP. (See R15.13 for why this is structural, not stylistic.)
- **R16.5** — `metadata` **MUST** pass a serializer that strips or rejects any value matching sensitive-field patterns, so a future careless call site cannot write personal data into an immutable store.
- **R16.6** — Record `actor_ip_hash`, never a raw address (§5.6).

### 16.5 Hash chain

- **R16.7** — `record_hash = SHA-256( canonical_serialization( seq ‖ chain_id ‖ occurred_at ‖ actor_type ‖ actor_id ‖ action ‖ target_type ‖ target_id ‖ outcome ‖ metadata ‖ prev_hash ) )`. The serialization **MUST** be canonical (deterministic key ordering, fixed encoding) or verification is not reproducible.
- **R16.8** — `seq` is strictly monotonic and gap-free within a chain. Assignment **MUST** be serialized (a transactional sequence or an equivalent guarantee) — concurrent inserts producing duplicate or out-of-order sequence numbers break verification.
- **R16.9** — `chain_id` partitions the chain (default: a single chain; optionally per-day) so sequence assignment does not become a global write bottleneck. Each partition is independently verifiable, and partition boundaries are linked by a checkpoint.
- **R16.10** — A periodic checkpoint (default hourly) records the latest `seq` and `record_hash` and is **signed with a KMS key** (§5.8). This anchors the chain against an attacker who can rewrite records *and* recompute the whole chain — without a signed checkpoint, a full rewrite is undetectable.
- **R16.11** — A verification job **MUST** run at least daily, re-walking the chain since the last verified checkpoint and raising a **critical** alert on any mismatch, gap, or checkpoint signature failure.
- **R16.12** — Audit writes **MUST NOT** be silently droppable. For actions where the audit record is the compensating control for a cross-boundary grant (§12.3), a write failure **MUST** fail the request.

### 16.6 Action vocabulary

- **R16.13** — Action names are stable, dotted, lowercase, and declared in a single catalog in code: `auth.login.success`, `auth.login.failure`, `auth.mfa.challenge.failure`, `admin.user.pii.read`, `admin.break_glass.activate`, `privacy.export.download`, `account.erased`, and so on. Ad-hoc string literals at call sites are forbidden — they make the trail unqueryable, which defeats its purpose.

---

## 17. Abuse prevention and rate limiting

### 17.1 Placement

- **R17.1** — Rate-limit admission runs at stage 2 of §3.4, **before** any persistence access and before any KDF invocation. Limiting after the expensive work has already happened prevents nothing.

### 17.2 State

- **R17.2** — Counters **MUST** live in shared state (the cache tier, or `rate_limit_counter` if no cache exists). **Per-process in-memory counters are ineffective** the moment more than one instance runs, and are a defect in any horizontally-scaled or serverless deployment.
- **R17.3** — Counters **MUST** be keyed on a hashed identifier, never a raw address or email (§5.6).
- **R17.4** — On counter-store unavailability, auth endpoints **MUST fail closed** (reject) rather than open. An unlimited authentication endpoint is strictly worse than a briefly unavailable one.

### 17.3 Limits

- **R17.4a** — Every authentication attempt **MUST** write an `auth_attempt` row, whether it succeeded or not, with `outcome` of `success` or `failure` and `method` naming how it was attempted: `password`, `passkey`, `otp` (email OTP or magic link), `totp`, `recovery_code`, `federated`, or `service_credential`. Every counter below is derived from those rows, so an authentication path that does not write one is invisible to rate limiting and to lockout — the control silently does not cover it.

Independent counters. Exceeding any one triggers its own response.

| Endpoint / action | Per identifier | Per source | On exceed |
|---|---|---|---|
| Password login | 5 failures / 15 min | 20 failures / 15 min | Progressive lockout |
| TOTP verification | 5 failures / 15 min | 30 / 15 min | Progressive lockout |
| Recovery code | **3 failures / 60 min** | 10 / 60 min | Lock + notify |
| Passkey assertion | 10 failures / 15 min | 50 / 15 min | Temporary block |
| Email OTP / magic link verify | 5 attempts / credential | 30 / 15 min | Destroy credential |
| Email OTP / magic link request | 3 / 10 min, 10 / day | 30 / hour | Silent throttle |
| Password reset request | 3 / hour | 10 / hour | Silent throttle |
| Registration | — | 5 / hour | Challenge seam (§17.6) |
| Email verification resend | 3 / hour | 20 / hour | Silent throttle |
| **Admin login** | **3 failures / 15 min** | 10 / 15 min | Lock + **staff alert** |
| Data export request | 1 / 24 h | — | Reject |
| Service token issuance | 60 / min per client | — | Reject |
| Session validation (authenticated) | 1000 / min | — | Reject |

- **R17.5** — Progressive lockout escalates: 1 min → 5 min → 15 min → 60 min, and it **MUST** self-release (R10.2).
- **R17.6** — Both identifier-scoped and source-scoped counters are required. Identifier-only limits do not stop password spraying across many accounts; source-only limits do not stop distributed attacks on one account.
- **R17.7** — Rate-limited responses use the generic envelope with `Retry-After`. They **MUST NOT** reveal which limit was hit, the remaining budget, or whether the account exists.

### 17.4 Breached-credential checking

- **R17.8** — Passwords **MUST** be checked against a known-breach corpus at set and change time.
- **R17.9** — The check **MUST** use a k-anonymity range protocol: send only a short hash prefix and match candidates locally. The full hash or the password itself **MUST NEVER** leave the system. This is also the §25.6 third-party data-flow entry.
- **R17.10** — On provider unavailability, the check fails **open** (permit) with a logged security event and a metric. A password-set path that hard-fails on a third-party outage is a self-inflicted denial of service. This is the one deliberate fail-open in the specification, and the asymmetry is intentional: §17.4 protects against a probabilistic quality issue, while §17.2 protects against active attack.
- **R17.11** — Passwords **MUST** additionally be rejected if they contain the account identifier or the service name.

### 17.5 Outbound send caps

- **R17.12** — Hard caps on outbound messages per address and per account (§17.3). Without them, the auth system is an open relay for spam and a cost-amplification target.
- **R17.13** — A global outbound rate ceiling **MUST** exist as a circuit breaker; exceeding it raises an operational alert and throttles rather than continuing to send.
- **R17.14** — Repeated sends to an address that never verifies **MUST** be suppressed after the daily cap and flagged.

### 17.6 Challenge seam (deferred)

- **R17.15** — A `challenge` verification port **MUST** exist in the abuse pipeline for registration, password reset, and repeated failed logins, with a no-op default implementation. Adding a provider later is a configuration change, not a refactor.
- **R17.16** — Any challenge provider adopted becomes a third-party data flow requiring registration in §25.6.

### 17.7 Risk signal seam (deferred)

- **R17.17** — A `risk_signal` evaluation hook **MUST** be invoked before session issuance, with a default implementation returning "no signal". Any future signals stored become personal data requiring a documented lawful basis and retention period.

---

## 18. Notifications and alerting

### 18.1 Rules

- **R18.1** — Notifications **MUST NOT** contain credentials, tokens, session identifiers, or personal data beyond what the recipient already holds about themselves.
- **R18.2** — Delivery **MUST** be asynchronous. A failed or slow mail transport **MUST NOT** fail or delay the security action itself.
- **R18.3** — Every notification is derived from a `security_event` row, so what was sent is reconstructable and duplicate sends are preventable.

### 18.2 User security notifications

Every user-facing notification is derived from a `security_event` row (R18.3), so this table is also the closed set of `security_event.kind`. A kind with no row here is a value nothing sends; a row with no kind is a notification nothing can record. Both are defects, and R18.8 makes that binding.

| `kind` | Sent when |
|---|---|
| `new_device_login` | A session is established from a device not previously seen (§6.7) |
| `password_changed` | The password credential is replaced (§9.1) |
| `password_reset_triggered` | An administrator triggers a reset (§12.4). The credential itself reaches only the user's own verified address (R12.9) |
| `email_changed` | The address changes (§7.8). Sent to **both** the old and the new address — see R18.5 |
| `mfa_enrolled` | A second factor is registered (§8) |
| `mfa_removed` | A second factor is revoked, including by administrative reset (§12.4) |
| `passkey_added` | A passkey is registered (§7.3) |
| `passkey_removed` | A passkey is revoked |
| `federated_linked` | A federated provider is linked (§7.6) |
| `federated_unlinked` | A federated provider is unlinked |
| `recovery_used` | A recovery code is consumed (§9.2) |
| `sessions_revoked` | Every session is revoked at once, by the user or by an administrator (§6.8) |
| `account_locked` | The account enters `locked`, by progressive lockout (§17.3) or administrative action (§12.4) |
| `account_unlocked` | The account returns to `active` from `locked` (§12.4) |
| `deletion_requested` | Erasure is requested (§15.4). **MUST** state the exact date of irreversible erasure |
| `deletion_cancelled` | Erasure is cancelled inside the grace window |

- **R18.4** — Each **MUST** include a "this wasn't me" action leading to a documented flow: revoke all sessions, force credential reset, and lock the account pending verification.
- **R18.5** — For email changes, the notice to the **old** address **MUST** include a cancellation action, because that address is the one an attacker is trying to sever.
- **R18.6** — Notifications **MUST NOT** be suppressible by the user. They are security-critical, not marketing, and are therefore outside the marketing-consent regime.
- **R18.6a** — The table above **MUST** cover every `security_event.kind` §4 declares, in both directions. It is checked (`authspec_check.py --only enum-values`), and it is the reason four kinds exist: §12.4 requires notifying the user of every administrative action (R12.10) and federated link/unlink was listed as a notification, but `password_reset_triggered`, `account_unlocked`, `federated_linked` and `federated_unlinked` had no value to record against. A mandated notification with no `kind` contradicts R18.3.

### 18.3 Staff alerts

Immediate alerts, on a channel outside the application (R12.14), for: break-glass activation; admin login from a new device; admin login failures exceeding the threshold; any admin role grant or revocation; administrative MFA reset; admin recovery request and approval; audit chain verification failure (**critical**); service credential creation or rotation; rate-limit counter store unavailability; and detection of an active development key provider in a deployed environment.

- **R18.7** — Alert delivery **MUST** be independent of the application's own database and mail path where possible; an alert that depends on the compromised system is not an alert.

### 18.4 Outbound event seam (deferred)

- **R18.8** — A stable event vocabulary (`user.created`, `user.erased`, `session.revoked`, `credential.changed`, `consent.recorded`) **MUST** be defined and emitted through an outbound port with a no-op default. Note that `user.erased` is not optional in practice — R15.14 requires downstream purge notification by some documented mechanism.

---

## 19. API contract

### 19.1 Form

- **R19.1** — Resource-oriented HTTP with a versioned path prefix (`/v1/`). Conventional method semantics; conventional status codes.
- **R19.2** — The contract is normative **in this document** (§19.4) **and** the implementation **MUST** emit a machine-readable interface description that CI verifies against the running routes (§19.9). Drift between the two fails the build.

### 19.2 Planes

| Prefix | Plane | Credential |
|---|---|---|
| `/v1/auth/*` | user, unauthenticated | none, or pending-MFA credential |
| `/v1/me/*` | user, authenticated | user session |
| `/v1/admin/*` | admin | admin session |
| `/v1/oauth/token` | service | client credentials |
| `/.well-known/*` | public | none |

### 19.3 Conventions

- **R19.3** — Request and response bodies are JSON. Every request body is validated against a strict schema; unknown fields are **rejected**, not ignored — silently ignoring unknown fields lets a client believe a security-relevant parameter was honored when it was dropped.
- **R19.4** — Timestamps are RFC 3339 UTC. Identifiers are opaque strings; clients **MUST NOT** parse them.
- **R19.5** — Every mutating request **MUST** accept an idempotency key and **MUST** return the original response for a repeated key within a bounded window (§22.9).
- **R19.6** — Every list endpoint is **cursor-paginated**: default page size 25, maximum 100. Offset pagination **MUST NOT** be used (it degrades and produces inconsistent pages under concurrent writes). An unbounded list endpoint is a P0 defect.

### 19.4 Endpoints

**Discovery (public):**

| Method | Path | Notes |
|---|---|---|
| GET | `/.well-known/openid-configuration` | Public metadata; cacheable |
| GET | `/.well-known/jwks.json` | Public verification keys; cacheable |

**User authentication (unauthenticated):**

| Method | Path | Permission | Notes |
|---|---|---|---|
| POST | `/v1/auth/register` | public | Uniform response (R7.40); consent required |
| POST | `/v1/auth/email/verify` | public | Consumes `email_verify` credential |
| POST | `/v1/auth/email/verify/resend` | public | Rate-limited; uniform response |
| POST | `/v1/auth/login/password` | public | → session or pending-MFA |
| POST | `/v1/auth/login/otp/request` | public | Uniform response |
| POST | `/v1/auth/login/otp/verify` | public | Context-bound (R7.16) |
| POST | `/v1/auth/login/passkey/options` | public | Server-generated challenge |
| POST | `/v1/auth/login/passkey/verify` | public | → session |
| GET | `/v1/auth/federated/{connection}/start` | public | OIDC (PKCE) or SAML |
| POST | `/v1/auth/federated/{connection}/callback` | public | Exact-match redirect validation |
| POST | `/v1/auth/mfa/challenge` | pending-MFA | Lists available factors |
| POST | `/v1/auth/mfa/verify` | pending-MFA | TOTP, passkey, or recovery code |
| POST | `/v1/auth/password/reset/request` | public | Uniform response |
| POST | `/v1/auth/password/reset/confirm` | public | MFA still required (R9.1) |

**User session and profile (authenticated):**

| Method | Path | Permission | Step-up |
|---|---|---|---|
| GET | `/v1/auth/session` | authenticated | no |
| POST | `/v1/auth/logout` | authenticated | no |
| POST | `/v1/auth/logout/all` | `session.revoke` | **yes** |
| GET | `/v1/me` | `profile.read` | no |
| PATCH | `/v1/me` | `profile.write` | no |
| POST | `/v1/me/email/change/request` | `profile.write` | **yes** |
| POST | `/v1/me/email/change/confirm` | public (token) | — |
| POST | `/v1/me/email/change/cancel` | public (token) | — |
| POST | `/v1/me/password` | `credential.write` | **yes** |
| GET | `/v1/me/credentials` | `credential.read` | no |
| POST | `/v1/me/credentials/passkey/options` | `credential.write` | **yes** |
| POST | `/v1/me/credentials/passkey` | `credential.write` | **yes** |
| DELETE | `/v1/me/credentials/passkey/{id}` | `credential.write` | **yes** |
| POST | `/v1/me/credentials/totp` | `credential.write` | **yes** |
| POST | `/v1/me/credentials/totp/confirm` | `credential.write` | **yes** |
| DELETE | `/v1/me/credentials/totp` | `credential.write` | **yes** |
| POST | `/v1/me/credentials/federated/{connection}` | `credential.write` | **yes** |
| DELETE | `/v1/me/credentials/federated/{id}` | `credential.write` | **yes** |
| POST | `/v1/me/recovery-codes` | `credential.write` | **yes** |
| GET | `/v1/me/sessions` | `session.read` | no |
| DELETE | `/v1/me/sessions/{id}` | `session.revoke` | **yes** |
| GET | `/v1/me/devices` | `device.read` | no |
| DELETE | `/v1/me/devices/{id}` | `device.revoke` | **yes** |
| GET | `/v1/me/security-events` | `profile.read` | no |
| GET | `/v1/me/consents` | `consent.read` | no |
| POST | `/v1/me/consents` | `consent.write` | no |
| POST | `/v1/me/exports` | `data.export` | **yes** |
| GET | `/v1/me/exports` | `data.export` | no |
| GET | `/v1/me/exports/{id}/download` | `data.export` | no |
| POST | `/v1/me/deletion` | `account.delete` | **yes** |
| DELETE | `/v1/me/deletion` | `account.delete` | no (cancellation must stay reachable) |

**Admin plane:**

| Method | Path | Permission | Step-up |
|---|---|---|---|
| POST | `/v1/admin/auth/login/passkey/options` | public | — |
| POST | `/v1/admin/auth/login/passkey/verify` | public | — |
| GET | `/v1/admin/auth/session` | authenticated | no |
| POST | `/v1/admin/auth/logout` | authenticated | no |
| POST | `/v1/admin/auth/step-up` | authenticated | — |
| GET | `/v1/admin/users` | `admin.user.list` | no |
| GET | `/v1/admin/users/{id}` | `admin.user.read_pii` | **yes** |
| POST | `/v1/admin/users/{id}/lock` | `admin.user.lock` | **yes** |
| POST | `/v1/admin/users/{id}/unlock` | `admin.user.lock` | **yes** |
| POST | `/v1/admin/users/{id}/sessions/revoke` | `admin.user.revoke_sessions` | **yes** |
| POST | `/v1/admin/users/{id}/mfa/reset` | `admin.user.reset_mfa` | **yes** |
| POST | `/v1/admin/users/{id}/password-reset` | `admin.user.trigger_password_reset` | **yes** |
| POST | `/v1/admin/users/{id}/deletion` | `admin.user.delete` | **yes** |
| GET | `/v1/admin/audit-events` | `admin.audit.read` | no |
| GET | `/v1/admin/audit-events/verify` | `admin.audit.read` | no |
| POST | `/v1/admin/break-glass` | `admin.break_glass.activate` | **yes** |
| GET | `/v1/admin/break-glass` | `admin.break_glass.review` | no |
| POST | `/v1/admin/break-glass/{id}/close` | `admin.break_glass.review` | **yes** |
| POST | `/v1/admin/recovery-requests/{id}/approve` | `admin.recovery.approve` | **yes** |
| GET/POST | `/v1/admin/service-accounts` | `admin.service_account.manage` | **yes** |
| POST | `/v1/admin/service-accounts/{id}/credentials` | `admin.service_account.manage` | **yes** |
| DELETE | `/v1/admin/service-accounts/{id}/credentials/{cid}` | `admin.service_account.manage` | **yes** |
| GET/POST | `/v1/admin/admins` | `admin.role.grant` | **yes** |
| POST | `/v1/admin/admins/{id}/roles` | `admin.role.grant` | **yes** |

**Service:**

| Method | Path | Notes |
|---|---|---|
| POST | `/v1/oauth/token` | Client credentials → ≤15 min assertion |

### 19.5 Error envelope

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Authentication failed.",
    "correlation_id": "01J8Z9X4K7Q2M5N8P3R6T1V4W7"
  }
}
```

- **R19.7** — Exactly one envelope shape for every error, on every endpoint.
- **R19.8** — `message` is generic and safe to display. It **MUST NOT** contain personal data, internal identifiers, stack traces, query text, or file paths.
- **R19.9** — `correlation_id` is always present and always logged server-side, so support can investigate without the client being told anything sensitive.
- **R19.10** — **Non-enumerating codes.** These distinct internal conditions **MUST** all surface as `invalid_credentials` with an identical response and comparable timing: unknown account; wrong password; wrong TOTP; wrong recovery code; unverified account; locked account; pending-deletion account; failed passkey assertion.
- **R19.11** — Field-level validation detail **MAY** be returned only for non-security input (profile fields, format errors), and **MUST NOT** be returned for any credential, identifier-existence, or authorization condition.

**Permitted codes:** `invalid_request`, `invalid_credentials`, `mfa_required`, `step_up_required`, `consent_required`, `unauthorized`, `forbidden`, `not_found`, `conflict`, `rate_limited`, `unavailable`, `internal_error`.

- **R19.12** — `not_found` and `forbidden` **MUST NOT** be distinguishable across an ownership boundary (R11.11).
- **R19.13** — Production **MUST NOT** emit framework error pages, stack traces, or database errors. Unhandled exceptions surface as `internal_error` with a correlation identifier only.

### 19.6 Response bodies

- **R19.14** — Responses return only what the consumer renders. Never return credential material, secrets, blind indexes, `token_hash` values, internal sequence numbers, or another principal's data.
- **R19.15** — The session-establishment response returns: principal identifier, `principal_type`, `acr`, effective permissions, session expiry timestamps, the CSRF token (cookie transport), and — for bearer transport only — the session secret.

### 19.7 Versioning

- **R19.16** — Breaking changes require a new path version. Within a version: no field removal, no type change, no semantic change, no new required request field, and no new mandatory error code a client cannot handle.
- **R19.17** — Additive changes are permitted, which is why R19.3's strict request validation is paired with tolerant client-side response parsing (§20.7).

### 19.8 Transport and headers

- **R19.18** — TLS 1.2 minimum, 1.3 preferred. Plaintext HTTP **MUST** be redirected, never served.
- **R19.19** — `Strict-Transport-Security: max-age=31536000; includeSubDomains` (with `preload` once verified).
- **R19.20** — Also required: `X-Content-Type-Options: nosniff`; `Referrer-Policy: strict-origin-when-cross-origin`; `Cross-Origin-Opener-Policy: same-origin`; `Cross-Origin-Resource-Policy: same-origin`; a restrictive `Content-Security-Policy` for any served HTML; `Permissions-Policy` denying unused features.
- **R19.21** — `Cache-Control: no-store` on **every** authenticated response and every authentication response. Only `/.well-known/*` is publicly cacheable (§22.7).
- **R19.22** — CORS: exact-match origin allowlist, credentials permitted only for allowlisted origins. `Access-Control-Allow-Origin: *` combined with credentials **MUST NOT** occur.
- **R19.23** — Responses over 1 KB **MUST** be compressed. Compression **MUST NOT** be applied to any response whose body contains a secret alongside attacker-influenced content (BREACH mitigation); the session-establishment response therefore carries `Cache-Control: no-store` and **MUST NOT** be compressed.

### 19.9 Machine-readable description

- **R19.24** — The implementation **MUST** emit a machine-readable interface description covering every route, request schema, response schema, error code, required permission, and step-up requirement.
- **R19.25** — CI **MUST** verify that the description matches the registered routes and that every route declares a permission (R11.5). Any drift fails the build.
- **R19.26** — Client SDKs **SHOULD** be generated from or validated against this description so no consuming app hand-writes a request shape.

---

## 20. Client SDK contract

Every consuming web and mobile application implements this contract. It exists so behaviour cannot drift between applications.

### 20.1 Interface

```
authenticate(method, params)      → Session | MfaRequired | Error
completeMfa(factor, params)       → Session | Error
getSession()                      → Session | null
stepUp(params)                    → Session | Error
logout(scope: current | all)      → void
onSessionChange(listener)         → unsubscribe
onConsentRequired(listener)       → unsubscribe
onStepUpRequired(listener)        → unsubscribe
```

### 20.2 Credential storage

| Platform | Storage | Forbidden |
|---|---|---|
| Web | `HttpOnly` cookie managed by the server; the SDK never sees the secret | `localStorage`, `sessionStorage`, non-`HttpOnly` cookies, JS-accessible memory persistence |
| iOS | Keychain, `WhenUnlockedThisDeviceOnly`, not synchronized to iCloud | `UserDefaults`, plist, plaintext files |
| Android | Keystore-backed EncryptedSharedPreferences or equivalent | plain SharedPreferences, plaintext files, external storage |

- **R20.1** — On native platforms the session secret **MUST** reside only in platform secure storage.
- **R20.2** — The secret **MUST NOT** be written to any log, crash report, analytics payload, breadcrumb, or debug output — including in development builds, because development habits become production leaks.
- **R20.3** — Secrets **MUST** be purged from storage on logout, on any `unauthorized` response, and on account deletion.

### 20.3 Session handling

- **R20.4** — A single-flight guard **MUST** ensure that concurrent requests encountering an expired session trigger **exactly one** re-authentication or refresh. Without it, N concurrent requests produce N simultaneous auth calls — a self-inflicted retry storm (§22.6).
- **R20.5** — Requests blocked during re-authentication are queued and replayed once, or failed cleanly. They **MUST NOT** be retried indefinitely.
- **R20.6** — On `unauthorized`, the SDK purges local state and emits a session-change event. It **MUST NOT** attempt to repair the session by guessing.

### 20.4 Retry policy

- **R20.7** — Retries are permitted **only** for idempotent requests and **only** on transport errors or `unavailable`. Never on `unauthorized`, `forbidden`, `invalid_credentials`, or `rate_limited`.
- **R20.8** — Exponential backoff with full jitter, maximum 3 attempts, honoring `Retry-After`. Unjittered retries synchronize clients into a thundering herd — a P0 load-amplification pattern.
- **R20.9** — Non-idempotent requests **MUST** carry an idempotency key (R19.5) if they are to be retried at all.

### 20.5 Error mapping

- **R20.10** — The SDK maps every error code to a defined client state. Unknown codes map to a generic failure — never to a crash, and never to silent success.
- **R20.11** — `consent_required` and `step_up_required` **MUST** be surfaced as first-class, handleable states, not treated as generic failures. Every consuming UI handles them identically.

### 20.6 Native platform requirements

- **R20.12** — OAuth and magic-link callbacks **MUST** use verified platform deep links (Universal Links / App Links). Custom URL schemes **MUST NOT** be used — any installed app can register the same scheme and intercept the authorization code.
- **R20.13** — Federated flows **MUST** use the platform's secure authentication session API (`ASWebAuthenticationSession` / Custom Tabs). An embedded web view **MUST NOT** be used: it lets the host application observe credentials and defeats the IdP's own protections.
- **R20.14** — PKCE (S256) is mandatory on every native authorization exchange (R7.26).
- **R20.15** — Certificate validation **MUST NOT** be relaxed in any build configuration. Certificate pinning **MAY** be added with a documented rotation and failure plan.

### 20.7 Biometric gate

- **R20.16** — Local biometric confirmation **MAY** gate sensitive actions in the UI. It is a **local UX control only**.
- **R20.17** — The server **MUST NOT** treat a client's assertion of biometric success as an authentication factor or as step-up satisfaction. A client claim is attacker-controlled on a compromised device. Server-side step-up (§8.5) is still required, and the biometric gate simply decides whether the app asks for it.

### 20.8 Compatibility

- **R20.18** — Clients tolerate unknown response fields (forward compatibility, R19.17) while the server rejects unknown request fields (R19.3). The asymmetry is deliberate.
- **R20.19** — Clients **MUST** tolerate ≤60 s clock skew and **MUST NOT** rely on local time for security decisions. The server is authoritative on expiry.

---

## 21. Interface (UI) requirements

Normative for **every** visual interface built against this API. Accessibility is validated by the compliance audit; an inaccessible auth screen fails it regardless of how correct the API is.

### 21.1 Baseline

- **R21.1** — WCAG 2.2 Level **AA** is the floor for every authentication, recovery, consent, and account-deletion flow. Level **AAA** contrast (7:1 for normal text, 4.5:1 for large text) **MUST** be met on error messages, validation feedback, status indicators, and primary actions.
- **R21.2** — Every flow **MUST** be completable using the keyboard alone.
- **R21.3** — No focus traps. Modals return focus to the invoking element on close (WCAG 2.1.2).
- **R21.4** — Focus indicators **MUST** be visible and **MUST NOT** be suppressed by a reset stylesheet (WCAG 2.4.7, 2.4.11).

### 21.2 Semantics

- **R21.5** — Native form semantics: real `<form>`, real `<label>` associated with every input, real `<button>`. A `<div>` with a click handler is not a button.
- **R21.6** — Errors **MUST** be programmatically associated with their field (`aria-describedby`, `aria-invalid`) and announced through a live region (WCAG 3.3.1).
- **R21.7** — Errors **MUST NOT** be conveyed by color alone (WCAG 1.4.1).
- **R21.8** — Loading and success states **MUST** be announced to assistive technology, not conveyed only by a spinner.

### 21.3 Accessible authentication (WCAG 2.2 SC 3.3.8 / 3.3.9)

- **R21.9** — No step may require a cognitive function test (memorizing, transcribing, solving a puzzle) without an accessible alternative. This is precisely why passkeys and email OTP satisfy 3.3.8 more readily than password-plus-puzzle flows.
- **R21.10** — Paste **MUST** be permitted in every field, including password and OTP inputs. Blocking paste breaks password managers and directly violates 3.3.8.
- **R21.11** — Correct `autocomplete` attributes are mandatory: `username`, `current-password`, `new-password`, `one-time-code`, `email`. These make the flow work with password managers and platform autofill, which is both an accessibility and a security improvement.
- **R21.12** — OTP fields **MUST** accept a full pasted code into a single input. Split single-character boxes that reject a paste are an accessibility failure.

### 21.4 Password fields

- **R21.13** — A show/hide toggle **MUST** be provided, keyboard-operable, with its state announced.
- **R21.14** — Minimum and maximum length **MUST** be stated **before** submission, not discovered through rejection.
- **R21.15** — Password strength feedback **MUST NOT** block submission of a policy-compliant password.
- **R21.16** — Breach rejection **MUST** be explained plainly ("this password has appeared in a known data breach") with a clear path forward.

### 21.5 Timeouts (WCAG 2.2.1, 2.2.6)

- **R21.17** — Users **MUST** be warned before an idle session expires, with at least 20 seconds to extend, and the warning **MUST** be announced to assistive technology.
- **R21.18** — Where session expiry could lose entered data, the interface **MUST** either preserve that data or warn about the loss on entry to the flow.
- **R21.19** — For the admin plane's 15-minute idle timeout, the warning is mandatory — a silent 15-minute timeout mid-task is a genuine usability failure that drives operators toward unsafe workarounds.

### 21.6 Redundant entry (WCAG 2.2 SC 3.3.7)

- **R21.20** — Multi-step flows (registration, MFA enrollment, recovery) **MUST NOT** require re-entering information already provided in the same process, except where re-entry is itself the security control (password confirmation).

### 21.7 Consent interfaces

- **R21.21** — Consent **MUST** be an unchecked-by-default affirmative action. Pre-ticked boxes and implied consent are non-compliant.
- **R21.22** — The exact document version being accepted **MUST** be identified and linked, and the link **MUST** be reachable without accepting.
- **R21.23** — The re-consent gate **MUST** keep export, deletion, and logout reachable (R14.7).
- **R21.24** — Where purpose-level consent exists, withdrawing **MUST** take no more steps than granting (R14.10).

### 21.8 Privacy interfaces

- **R21.25** — Export and deletion **MUST** be discoverable in account settings within two navigation steps. Burying them is a dark pattern and a compliance finding.
- **R21.26** — The deletion flow **MUST** state plainly: what is erased, what is retained (audit records and why), the exact date of irreversible erasure, and how to cancel.
- **R21.27** — Deletion **MUST NOT** use confirm-shaming or asymmetric button prominence.

### 21.9 Client-side data hygiene

- **R21.28** — Personal data **MUST NOT** be written to browser console, `localStorage`, analytics payloads, session-replay tools, or crash reports. Session-replay tooling **MUST** be disabled entirely on authentication and account-settings screens, or masked at the DOM level with verified coverage.
- **R21.29** — Third-party scripts (analytics, tag managers, support widgets) **MUST NOT** load on any authentication screen. They are a credential-theft vector and, absent consent, an ePrivacy violation (§25.4).

---

## 22. Performance requirements

### 22.1 Latency budgets (P95, server-side)

| Operation | Budget | Notes |
|---|---|---|
| Session validation (cache hit) | ≤5 ms | Hot path on every request |
| Authenticated read (`GET /v1/me`) | ≤100 ms | Core read SLA |
| Session validation (cache miss) | ≤30 ms | Single indexed lookup |
| Password authentication | ≤500 ms | KDF-dominated (100–250 ms by design) |
| Passkey authentication | ≤150 ms | Signature verification |
| Token/assertion issuance | ≤50 ms | |
| Any write operation | ≤250 ms | Write SLA |
| Admin list (100 rows) | ≤200 ms | Cursor-paginated |

- **R22.1** — Any endpoint exceeding its budget **MUST** be either optimized, cached, or moved to a background job. Export (§15.2) is background by design for exactly this reason.

### 22.2 Round-trip budget

- **R22.2** — **Maximum 3 persistence round-trips per request** on any hot path. Login is the documented exception at ≤5.
- **R22.3** — Independent reads **MUST** execute concurrently, never as sequential awaits. N sequential queries × network latency is avoidable time-to-first-byte with no N+1 pattern present.
- **R22.4** — No query inside a loop. Permission resolution, role expansion, and credential listing **MUST** be single set-based queries. Fetching a principal's roles then querying permissions per role is the canonical N+1 in an auth system.
- **R22.5** — Within a request, an identical query **MUST NOT** execute twice. Memoize per request context.

### 22.3 Query discipline

- **R22.6** — Project only the attributes used (R4.7). Never select encrypted blobs that will not be decrypted — they are the largest columns in the schema.
- **R22.7** — Every filter, sort, and join attribute named in §4 **MUST** have a supporting index. Required index inventory:

| Table | Index | Serves |
|---|---|---|
| `user` | unique(`email_index`) partial | Login lookup |
| `user` | (`status`, `deletion_requested_at`) | Erasure job |
| `session` | unique(`token_hash`) | **Every authenticated request** |
| `session` | (`principal_type`, `principal_id`) partial on active | Logout-all, session list |
| `session` | (`absolute_expires_at`) | Retention job |
| `session` | (`device_id`) | Device revocation |
| `credential` | (`principal_type`, `principal_id`, `kind`) partial on active | Factor lookup |
| `credential` | unique(`kind`, `credential_ref`) partial | Passkey/federated lookup |
| `one_time_credential` | unique(`token_hash`) | Redemption |
| `one_time_credential` | (`expires_at`) | Retention job |
| `audit_event` | unique(`chain_id`, `seq`) | Chain verification |
| `audit_event` | (`target_type`, `target_id`, `occurred_at`) | Subject-centric queries |
| `audit_event` | (`occurred_at`) | Retention job |
| `auth_attempt` | (`identifier_hash`, `occurred_at`) | Lockout evaluation |
| `auth_attempt` | (`ip_hash`, `occurred_at`) | Source rate limiting |
| `principal_role` | (`principal_type`, `principal_id`) partial on active | Permission resolution |
| `service_credential` | unique(`client_id`) | Token issuance |

- **R22.8** — Counting, filtering, sorting, and aggregation **MUST** execute in the persistence engine, never by loading rows into application memory.
- **R22.9** — Every list endpoint is cursor-paginated (R19.6).

### 22.4 Compute

- **R22.10** — KDF operations **MUST NOT** block the main execution thread and **MUST** be bounded by a concurrency limiter (R5.11). This is both the primary CPU-exhaustion vector and the primary event-loop stall in an auth service.
- **R22.11** — Signature verification (WebAuthn, SAML, JWS) **MUST** likewise be offloaded or bounded where the runtime is single-threaded.
- **R22.12** — No synchronous filesystem, DNS, or blocking socket operation inside a request handler.
- **R22.13** — Permission resolution **MUST** be O(roles + permissions), never nested iteration over the catalog.
- **R22.14** — Public verification keys (JWKS) **MUST** be cached in-process with a bounded TTL. Fetching keys per verification is an avoidable network round-trip on a hot path.

### 22.5 Connections

- **R22.15** — **Serverless/edge deployments MUST route through an external connection pooler.** Opening a direct persistence connection per invocation exhausts the engine's connection limit under load and is a P0 cascading-failure vector.
- **R22.16** — Long-lived processes **MUST** bound pool size below `max_connections ÷ instance_count`, with headroom for maintenance.
- **R22.17** — Every pool **MUST** define an acquisition timeout (default 2 s). Without it, a saturated pool queues requests until memory is exhausted.
- **R22.18** — **Every query path MUST enforce a statement/query timeout** (default 3 s for request paths, 30 s for background jobs). One slow query without a timeout pins a connection, drains the pool, and stalls every unrelated request queued behind it.
- **R22.19** — Transactions **MUST NOT** remain open across network I/O — no KMS call, no email send, no breach-list lookup inside a transaction. Encrypt before opening; send after committing.
- **R22.20** — Transactions **MUST** be short and **MUST NOT** hold locks across multiple statements on high-write tables.

### 22.6 Retries and failure isolation

- **R22.21** — Every outbound call (KMS, email, breach list, alerting, IdP) **MUST** have an explicit timeout, exponential backoff **with full jitter**, a hard retry cap (default 3), and a circuit breaker. Uncapped retries against a degraded dependency multiply load precisely when the system can least absorb it.
- **R22.22** — Circuit-breaker open state **MUST** fail fast. Queuing behind a degraded dependency exhausts memory and sockets.
- **R22.23** — KMS unwrap results **MAY** be cached in a bounded, short-TTL, LRU-evicted structure. The cache **MUST** be bounded — an unbounded key cache is both a memory leak and a widening of the key exposure window.

### 22.7 Caching

- **R22.24** — Session cache TTL = min(60 s, remaining idle window), with mandatory invalidation on revocation (R6.22).
- **R22.25** — Permission sets **MAY** be cached per session with the same TTL and **MUST** be invalidated on any role change.
- **R22.26** — `/.well-known/*` are the **only** publicly cacheable endpoints: `Cache-Control: public, max-age=300, s-maxage=600, stale-while-revalidate=60`.
- **R22.27** — Every other auth response is `no-store` (R19.21). An intermediary caching an authenticated response is a cross-user data-disclosure vector.
- **R22.28** — All cache reads are schema-validated before use (§6.6.1).

### 22.8 Memory

- **R22.29** — Every in-process cache (sessions, permissions, JWKS, DEKs, rate-limit buckets) **MUST** enforce a maximum size **and** an eviction policy. An unbounded map in a long-lived process is a guaranteed memory leak.
- **R22.30** — Exports and any bulk operation **MUST** stream (R15.5).
- **R22.31** — Every timer, listener, subscription, and background loop **MUST** have a cleanup path and **MUST** be released on shutdown.
- **R22.32** — Logging **MUST NOT** deep-clone or fully serialize large object graphs per request on hot paths.

### 22.9 Concurrency safety

- **R22.33** — Idempotency keys (R19.5) are stored with their response for a bounded window (default 24 h) so a retried mutation returns the original result rather than executing twice.
- **R22.34** — One-time credential consumption is atomic (R4.12).
- **R22.35** — Audit sequence assignment is serialized (R16.8), with `chain_id` partitioning (R16.9) available to relieve contention.
- **R22.36** — Rate-limit counter increments **MUST** be atomic operations, never read-modify-write, which under concurrency lets an attacker exceed the limit by a wide margin.
- **R22.37** — There **MUST** be no `SELECT ... FOR UPDATE` or serializable transaction on any hot authentication path.

### 22.10 Payloads

- **R22.38** — Auth responses **SHOULD** stay under 4 KB and **MUST** stay under 50 KB.
- **R22.39** — Permission lists in responses **MUST** be compact names, not nested objects with descriptions.
- **R22.40** — Compression per R19.23.

---

## 23. Retention and scheduled jobs

### 23.1 Principle

- **R23.1** — Every table with unbounded growth or a legal retention limit **MUST** have an automated job enforcing it. A documented policy with no job is not a control.

### 23.2 Schedule

| Data | Retention | Rationale |
|---|---|---|
| `audit_event` | **6 years** | HIPAA § 164.316(b)(2) floor; satisfies SOC 2 and NIST |
| `security_event` | 1 year | Security operations |
| `auth_attempt` | 1 year | Abuse investigation; **90 days** if not needed for compliance evidence |
| `session` (expired/revoked) | 30 days after expiry | Investigation window |
| `one_time_credential` (consumed/expired) | 24 hours | No value after consumption |
| `data_export` artifacts | 7 days | Highest-value object in the system |
| `rate_limit_counter` | Window duration + 1 hour | Operational only |
| Unverified registrations | 7 days | Data minimization |
| `user` PII | Account lifetime, then §15.4 | |
| `device` | 90 days after last session | |
| Backups | Per runbook; erasure applies via §15.5 | |

- **R23.2** — Where a deployment is not HIPAA-subject, audit retention **MAY** be shortened by configuration — but **MUST NOT** be silently lengthened past a legal maximum. Over-retention is itself a finding.

### 23.3 Required jobs

| Job | Cadence | Function |
|---|---|---|
| Erasure worker | Hourly | Executes §15.4 phase 3 for grace-elapsed accounts |
| Session pruner | Daily | Removes expired/revoked `session` rows past their window |
| One-time credential pruner | Hourly | Removes consumed/expired `one_time_credential` rows |
| Export pruner | Hourly | Destroys expired artifacts, marks `expired` |
| Unverified registration pruner | Daily | Purges per R7.42 |
| Audit chain verifier | Daily | Re-walks and verifies the chain (R16.11) |
| Audit checkpointer | Hourly | Writes a KMS-signed checkpoint (R16.10) |
| Audit pruner | Monthly | Prunes `audit_event` past 6 years under the maintenance principal |
| Attempt/security-event pruner | Daily | Drains `auth_attempt` and `security_event` per §23.2 |
| Role grant expirer | Every 5 min | Marks expired grants (belt-and-braces to R12.13) |
| Key rotation | Per schedule | Signing keys 90 d, pseudonym key 90 d, DEK rotation as configured |
| Credential expiry notifier | Daily | Service credential 30/7/1-day warnings |
| Break-glass review monitor | Daily | Alerts on activations unreviewed >7 days |
| Dormant service account reporter | Weekly | Flags credentials unused >90 days |

- **R23.3** — Jobs **MUST** be idempotent, resumable, and batched with bounded batch size. An erasure job that loads every pending account at once is a memory-exhaustion vector.
- **R23.4** — Jobs **MUST NOT** poll hot tables on tight intervals. Use the stated cadences with indexed predicates; where the platform supports change notification, prefer it (constant polling produces baseline query load and lock churn).
- **R23.5** — Every job run **MUST** emit an audit event with counts and outcome. A silent job is an unverifiable control.
- **R23.6** — Job failures **MUST** raise operational alerts. A silently failing erasure worker is an ongoing, undetected compliance violation.

---

## 24. Configuration

### 24.1 Rules

- **R24.1** — Every security-relevant value is explicit configuration with a documented secure default. No security value is hardcoded at a call site.
- **R24.2** — Configuration may **tighten** but never **loosen** past the ceilings in §6.3, §8.5, and §17.3. Ceilings are enforced in code, not by convention.
- **R24.3** — Secrets are supplied by the environment or a secrets manager, never committed. The repository **MUST** carry secret-scanning in pre-commit and CI.

### 24.2 Reference

| Key | Default | Ceiling | Section |
|---|---|---|---|
| `session.user.idle` | 30 d | 30 d | §6.3 |
| `session.user.absolute` | 90 d | 90 d | §6.3 |
| `session.admin.idle` | 15 min | 15 min | §6.3 |
| `session.admin.absolute` | 8 h | 8 h | §6.3 |
| `session.cache_ttl` | 60 s | 60 s | §6.6 |
| `session.last_seen_write_threshold` | 60 s | — | §6.6.4 |
| `stepup.user.freshness` | 15 min | 15 min | §8.5 |
| `stepup.admin.freshness` | 5 min | 5 min | §8.5 |
| `assertion.lifetime` | 120 s | 300 s | §6.4 |
| `password.kdf.*` | §5.3 | — | §5.3 |
| `password.min_length` | 12 | — (floor) | R5.12 |
| `otp.ttl` | 5 min | 10 min | §7.4 |
| `otp.max_attempts` | 5 | 5 | §7.4 |
| `password_reset.ttl` | 15 min | 15 min | §9.1 |
| `deletion.grace_period` | 30 d | 30 d | §15.4 |
| `export.ttl` | 7 d | 7 d | §15.2 |
| `export.rate` | 1 / 24 h | — | §15.2 |
| `breakglass.max_duration` | 60 min | 60 min | §12.5 |
| `admin.recovery.enrollment_window` | 15 min | 15 min | R9.11 |
| `admin.min_authenticators` | 2 | — (floor) | R7.13 |
| `ratelimit.*` | §17.3 | §17.3 | §17.3 |
| `retention.audit` | 6 y | legal max | §23.2 |
| `keys.signing.rotation` | 90 d | 90 d | R5.30 |
| `keys.pseudonym.rotation` | 90 d | 90 d | R5.22 |
| `db.statement_timeout` | 3 s | 10 s | §22.5 |
| `db.pool.acquire_timeout` | 2 s | 5 s | §22.5 |
| `outbound.retry.max` | 3 | 5 | §22.6 |
| `fips_mode` | false | — | §5.5 |

### 24.3 Startup validation

- **R24.4** — The implementation **MUST** validate configuration at startup and **fail closed** — refusing to start — when any of these hold in a deployed environment: the development key provider is active; no KMS is reachable; any ceiling in §24.2 is exceeded; TLS enforcement is disabled; the CORS allowlist contains a wildcard while credentials are permitted; the audit table grants include `UPDATE` or `DELETE` for the application principal; any required signing key is absent; the rate-limit counter store is unreachable; or `SameSite`/`Secure`/`HttpOnly` cookie attributes are weakened.
- **R24.5** — Failed validation **MUST** log which check failed (never the value) and exit non-zero. Starting in a degraded but running state is worse than not starting.

---

## 25. Privacy engineering

### 25.1 Data inventory

- **R25.1** — The implementation **MUST** ship a data inventory naming every stored attribute, its classification (identifier / authentication secret / behavioural / derived), its lawful basis, its retention period, and its protection (`[ENC]`, `[HASH]`, `[BIDX]`, plaintext). This is a deliverable (§26.4), and it is the first artifact any auditor asks for.

### 25.2 Minimization

- **R25.2** — No attribute may be collected without a stated operational purpose in the inventory. "It might be useful later" is not a purpose and is a documented violation.
- **R25.3** — Specifically **MUST NOT** be collected by this framework: date of birth, gender, postal address, government identifiers, or any special-category data. None serves authentication.
- **R25.4** — Optional profile attributes **MUST** be genuinely optional — no server-side requirement, no UI dark pattern implying obligation.

### 25.3 Purpose limitation

- **R25.5** — Authentication data **MUST NOT** be repurposed for analytics, marketing, or profiling. Security telemetry serves security operations only.

### 25.4 Tracking

- **R25.6** — No analytics, tag manager, session-replay, or behavioural SDK on any authentication screen (R21.29).
- **R25.7** — Anywhere else in a consuming app, non-essential tracking **MUST** remain inert until server-recorded affirmative consent exists. A client-side consent flag with no server record satisfies nothing.

### 25.5 Access minimization

- **R25.8** — Administrative personal-data access is a separate, sensitive, audited permission (§11.3), never bundled with routine operational access. This is the "minimum necessary" control.

### 25.6 Third-party data flow register

- **R25.9** — Every outbound flow **MUST** be registered with recipient, data categories, purpose, lawful basis, processing location, and safeguards. At minimum this framework's flows are:

| Recipient | Data | Purpose | Notes |
|---|---|---|---|
| Email transport | Address, message content | Verification, OTP, security notices | Processor agreement required |
| KMS provider | Wrapped key material only | Key management | No personal data |
| Breach-list provider | **Hash prefix only** | Credential quality | k-anonymity; no personal data leaves (R17.9) |
| Identity providers (OIDC/SAML) | Whatever the user's IdP asserts | Federated authentication | Per-connection documentation |
| Alerting channel | Operational codes only, **no personal data** | Staff alerts | |

- **R25.10** — Adding any recipient not in this register is a specification amendment, not a configuration change.

---

## 26. Deliverables

A conforming implementation produces all four.

### 26.1 Server implementation and persistence schema

- Component structure per §3.3, each independently testable.
- Complete schema from §4 in the project's native migration tooling, including every index and constraint, plus the audit-table grant restriction (R4.14).
- A reversible migration path where the tooling supports it; the audit grant change is documented as requiring privileged execution.
- The permission and role catalog declared in code and reconciled by migration (R4.13).

### 26.2 Client SDK contract

- The §20 interface for web and for each native platform in use.
- Platform-appropriate secure storage (§20.2).
- Single-flight re-authentication, jittered capped retry, complete error-code mapping.
- Generated from or validated against the machine-readable description (R19.26).

### 26.3 Test suite

Per §27.2.

### 26.4 Runbooks and configuration reference

| Document | Contents |
|---|---|
| Configuration reference | Every key from §24.2, its default, ceiling, effect, and every recorded deviation from a **SHOULD** |
| Data inventory | §25.1 |
| Third-party register | §25.6 |
| Key management runbook | Rotation for signing, pseudonym, and data keys; overlap windows; emergency rotation; KMS unavailability |
| Break-glass runbook | Activation criteria, alert recipients, review procedure, the R12.14 alert-failure behaviour, frequency review cadence |
| Admin recovery runbook | Out-of-band identity verification, approver rotation, the R9.13 break-glass dependency |
| Incident runbook | Credential compromise, audit-chain verification failure, session-store compromise, KMS compromise, mass-revocation procedure |
| Erasure and backup runbook | Grace period, job monitoring, R15.17 restore interaction, downstream purge interfaces |
| Retention operations | Every job from §23.3, its cadence, alerting, and failure handling |

---

## 27. Conformance gate

**Generation is not complete until every item below passes.** This is the acceptance criterion.

### 27.1 Audit gate

Run all three audits against the generated code:

```
/audits:security-audit
/audits:compliance-audit
/audits:performance-audit
```

- **R27.1** — All three **MUST** report zero findings — `[OK]`, `[COMPLIANCE OK]`, `[PERF OK]` respectively. Any finding at any severity blocks completion.
- **R27.2** — If an audit reports a finding the implementer believes to be a false positive, the resolution is to make the code unambiguous — not to argue with the finding. The audits read execution paths; if a control is not traceable in the code, it is indistinguishable from an absent control.
- **R27.3** — The audits **MUST** be re-run after any subsequent change to the auth module.

### 27.2 Test gate

All of these **MUST** exist and pass.

**Authorization and isolation:**
- Cross-account read of every user-scoped resource is denied.
- Cross-account **mutation** of every user-scoped resource is denied (R11.8).
- A user session is rejected by every admin endpoint (INV-1, INV-2).
- An admin session is rejected by every user endpoint.
- Every route declares a permission; a route without one fails the build (R11.5).
- Denial responses do not distinguish absence from prohibition (R11.11).
- Every `is_sensitive` permission enforces step-up freshness server-side.
- An expired break-glass grant stops working immediately without a job run (R12.13).

**Session:**
- A revoked session is rejected on the very next request, including with a warm cache (R6.22).
- Absolute expiry is not extended by activity (R6.4).
- Idle expiry is enforced.
- A cookie session presented as a bearer token is rejected, and vice versa (R6.17).
- Presenting both a cookie and a bearer header is rejected outright.
- A state-changing cookie request without a valid CSRF token is rejected.
- The pre-auth session identifier is not reused post-authentication (R6.30).
- The pending-MFA credential grants no permission at any endpoint (R6.31).
- Locking an account invalidates live sessions (R4.8).

**Authentication:**
- Timing and response body are indistinguishable for unknown account vs. wrong password (R7.3, R19.10).
- Registration response is identical for new vs. existing address (R7.40).
- A one-time credential cannot be redeemed twice, including under concurrent redemption (R4.12).
- A TOTP code cannot be replayed within its window (R7.23).
- A WebAuthn assertion with a non-increasing sign counter is rejected (R7.11).
- An admin authentication attempt via password, OTP, or TOTP has no reachable route (R7.6).
- An admin passkey with `backup_eligible = true` is rejected at enrollment (R7.12).
- An admin cannot leave `pending_enrollment` with fewer than two authenticators (R7.13).
- Password reset does not bypass enrolled MFA (R9.1).
- Password reset does not remove a second factor (R9.2).
- Federated auto-link is refused when the provider does not assert a verified email (R7.34).
- Federated auto-link is refused for a provider not in the trusted-verifier list (R7.35).
- `alg: none` and algorithm substitution are rejected (R5.28).
- Tokens with embedded key material (`jwk`/`jku`/`x5u`) are rejected (R5.31).
- An admin cannot self-approve their own recovery request (R9.11).

**Abuse:**
- Per-identifier lockout engages at the threshold and self-releases (R17.5).
- Per-source limiting engages independently (R17.6).
- Recovery-code attempts are limited on their own counter.
- Rate limiting is effective across multiple process instances (R17.2).
- Auth endpoints fail closed when the counter store is unavailable (R17.4).
- Outbound send caps engage.
- Breached passwords are rejected; the provider never receives the full hash (R17.9).
- Rate-limit responses do not reveal which limit or remaining budget (R17.7).

**Privacy:**
- Erasure destroys the DEK, and previously encrypted values are unrecoverable afterward.
- Erasure removes the blind index (R5.19).
- Erasure leaves audit records intact and non-identifying (R15.13).
- Erasure is idempotent and resumable (R15.15).
- Export includes every category in R15.2.
- Export streams rather than buffering (R15.5).
- The export download credential is single-use and expires.
- The re-consent gate blocks ordinary access but never blocks export, deletion, or logout (R14.7).
- Registration without consent records is impossible, including via federated JIT provisioning (R14.4).
- No audit record contains personal data (R16.4, R16.5).

**Audit trail:**
- The application principal cannot `UPDATE` or `DELETE` an audit record (R4.14).
- Chain verification detects a modified record, a deleted record, and a resequenced record.
- Checkpoint signature verification detects a wholesale chain rewrite (R16.10).
- Sequence assignment produces no duplicates or gaps under concurrent insertion (R16.8).
- Every administrative personal-data read produces an audit record before the response is sent (R12.5).
- An audit write failure on a PII read fails the request (R16.12).

**Performance:**
- Every hot path stays within its round-trip budget (R22.2), asserted by query counting in tests.
- Permission resolution issues no per-role query (R22.4).
- Every list endpoint enforces a maximum page size (R19.6).
- Concurrent KDF operations are bounded (R5.11).
- Every outbound call has a timeout and a capped, jittered retry (R22.21).
- Every in-process cache is bounded and evicts (R22.29).
- Every query path enforces a statement timeout (R22.18).
- No transaction remains open across an outbound network call (R22.19).

**Configuration:**
- Startup fails closed for each condition in R24.4 (one test per condition).
- No ceiling in §24.2 can be exceeded by configuration (R24.2).

### 27.3 Static gate

- **R27.4** — Secret scanning passes on the working tree **and** on git history.
- **R27.5** — Dependency vulnerability scanning reports no known-exploitable vulnerability in the auth module's dependency tree.
- **R27.6** — The machine-readable description matches the registered routes (R19.25).
- **R27.7** — No route lacks a permission declaration.
- **R27.8** — No prohibited primitive from R5.4 appears anywhere in the module.
- **R27.9** — No non-constant-time comparison is applied to a secret, digest, or token.
- **R27.10** — No log statement, at any level, emits a value from an `[ENC]`, `[HASH]`, or `[BIDX]` attribute, or a session secret, password, token, or raw IP address.
- **R27.11** — **Retired identifier registry.** A requirement identifier that is withdrawn is recorded here and **MUST NOT** be cited or redefined anywhere in this document. Numbering is append-only: a retired number is never reused for new meaning, because a stale citation that resolves to the *wrong* requirement is worse than one that fails to resolve. Retired to date: *none*. `tools/authspec_check.py --only retired` reads this list, so an entry added here is enforced from the next run; an empty registry is the correct state for a document that has retired nothing, not a missing one.

### 27.4 Coverage map

Each audit checklist section maps to the controls that satisfy it. Use this when triaging a finding.

**Security audit:**

| Checklist section | Controls |
|---|---|
| Boundary leakage | §3.1 INV-1..5, §11.4, §11.5 |
| Zero-trust access control | §11.4 R11.5–R11.9, §3.4 |
| Session mutation hardening | §5.8, §6.2, §6.3, §6.9 |
| Data at rest | §5.3, §5.4, R5.13–R5.17 |
| Cryptographic shredding | §15.4 phase 3, §15.5 |
| In-transit integrity | §19.8 R19.18–R19.19 |
| Immutable security trails | §16.3, §16.5 |
| Log sanitation | §16.4, R5.21, R27.10 |
| Production error handling | §19.5 R19.13 |
| Dependency hardening | §27.3 R27.5 |
| Injection prototyping | §19.3 R19.3, §7.6.2 R7.33, §7.6.1 R7.29 |
| Tenant scoping on mutations | §11.4 R11.7–R11.8, §11.5 R11.10 |
| Cache/session-store validation | §6.6.1 step 3, §22.7 R22.28 |
| Erasure execution | §15.4, §15.5 |

**Compliance audit:**

| Checklist section | Controls |
|---|---|
| Right to erasure | §15.4, R15.12 |
| Portability / access | §15.2 |
| Rectification | §15.3 |
| Server-side consent enforcement | §14.2, §14.4 |
| Tracking and cookie gating | §25.4, R21.29 |
| Re-consent triggers | §14.4 |
| Administrative non-repudiation | §12.3, §16.2 |
| Tamper-resistant logging | §16.3, §16.5 |
| PII leakage in logs | §16.4, R5.21, R27.10 |
| Absolute and idle timeouts | §6.3 |
| RBAC integrity | §11 |
| Data residency | §5.7 |
| Data minimization | §25.2, R4.11, R7.39 |
| Retention schedules | §23 |
| Vendor data flows | §25.6 |
| Keyboard navigation and focus | §21.1, §21.2 |
| Semantic / ARIA structure | §21.2 |
| Contrast on critical UI | §21.1 R21.1 |

**Performance audit:**

| Checklist section | Controls |
|---|---|
| N+1 queries | §22.2 R22.4 |
| Missing indexes | §22.3 R22.7 |
| Unbounded cursors | §19.3 R19.6 |
| Over-fetching | §22.3 R22.6 |
| Transaction lifespan | §22.5 R22.19–R22.20 |
| Sequential waterfalls | §22.2 R22.3 |
| Round-trip budget | §22.2 R22.2 |
| Pool exhaustion | §22.5 R22.15–R22.17 |
| Statement timeouts | §22.5 R22.18 |
| Retry storms | §22.6 R22.21, §20.4 R20.8 |
| Database-as-queue polling | §23.3 R23.4 |
| Lock contention | §22.9 R22.37 |
| Computation in wrong tier | §22.3 R22.8 |
| Cache-control and SWR | §22.7 R22.26–R22.27 |
| Request dedup | §22.2 R22.5, §20.3 R20.4 |
| Cache invalidation | §6.6.5, §22.7 R22.25 |
| Volatile store batching | §6.6.1, §22.7 |
| Latency budgets | §22.1 |
| Payload budgets | §22.10 |
| Compression | §19.8 R19.23 |
| Idempotency | §19.3 R19.5, §22.9 R22.33 |
| Connection reuse | §22.6 R22.21 |
| Blocking I/O | §22.4 R22.12 |
| Logging overhead | §22.8 R22.32 |
| Circuit breaking | §22.6 R22.22 |
| Thread starvation | §22.4 R22.10–R22.11 |
| Algorithmic complexity | §22.4 R22.13 |
| Unbounded concurrency | §22.6 R22.21, §23.3 R23.3 |
| Unevicted global collections | §22.8 R22.29 |
| Buffered storage | §22.8 R22.30, §15.2 R15.5 |
| Listener lifecycle | §22.8 R22.31 |

---

## 28. Design rationale

Decisions most likely to be questioned later, and why they were made.

| Decision | Rationale |
|---|---|
| Server-side sessions over stateless tokens | Immediate, complete revocation. Lock, logout-all, credential-change invalidation, and deletion are all only as real as revocation is. The cache tier (§6.6) recovers the performance a stateless design would have given. |
| Separate admin plane | INV-1 makes admin compromise structurally independent of user compromise. A role flag on a shared user table means one user-plane bug can reach admin scope. |
| Passkey-only admins | FedRAMP High / NIST SP 800-63B require phishing-resistant MFA for privileged access. TOTP is not phishing-resistant — it is relayable in real time. Admitting TOTP for admins would be a knowing deviation. |
| No impersonation | It is the single most dangerous feature in an auth system and was not requested. A partial implementation is worse than none (R12.20). |
| Crypto-erasure after a grace period | The grace period prevents irreversible loss from a moment's frustration; crypto-erasure makes deletion real across backups, which soft-delete and row-delete both fail to do. |
| No personal data in audit records | Audit records must survive erasure for 6 years. Personal data there would be unerasable, creating a direct and unresolvable conflict between two mandatory obligations (R15.13). |
| Blind index on email | Encrypted email cannot be searched, but login requires exact-match lookup. A keyed HMAC gives lookup without a reversible plaintext copy — and is itself deleted on erasure. |
| Auto-link only on verified email from a trusted provider | An unverified `email_verified` claim is attacker-controlled. Auto-linking on it is the classic pre-registration account takeover. |
| Fail-closed rate limiting, fail-open breach check | Asymmetric on purpose: §17.2 defends against active attack, where an unlimited endpoint is worse than an unavailable one. §17.4 defends against a probabilistic quality issue, where a third-party outage should not break password changes. |
| Bounded KDF concurrency | An unbounded memory-hard KDF is simultaneously the strongest password defense and the easiest CPU/memory exhaustion vector. Bounding it is what makes it safe to use. |
| Cursor pagination only | Offset pagination degrades linearly and produces inconsistent pages under concurrent writes — both a performance and a correctness problem on exactly the admin list endpoints most likely to be enumerated. |
| Strict request validation, tolerant response parsing | Rejecting unknown request fields prevents a client from believing a security parameter was honored when it was dropped. Tolerating unknown response fields lets the server add fields without breaking deployed clients. |
| Ownership predicate indirection | Puts the account isolation boundary in exactly one reviewable place, and makes future tenancy a one-site change rather than an audit of every query. |
```
