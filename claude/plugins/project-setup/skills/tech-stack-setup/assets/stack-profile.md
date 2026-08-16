# Stack Profile — `<PRODUCT>`

**Status:** Binding for this product
**Conforms to:** `STACKSPEC <VERSION>`, `AUTHSPEC <VERSION>`
**Last reviewed:** `<YYYY-MM-DD>` by `<NAME>`

This is the declared stack document for this product. It is what `AUTHSPEC §2.1`
resolves to, and it is authoritative for this product's technology choices.

The specs themselves are **not** vendored here — they are maintained in the
`luismc-project-setup` plugin, `STACKSPEC` with the `tech-stack-setup` skill and
`AUTHSPEC` with `auth-setup`. This profile records only what is specific to this
product, plus the spec versions it conforms to. Everything not recorded below is
governed by the spec at the version named above.

> Replace every `<...>` placeholder. A placeholder left in place is a
> conformance failure, not a formatting nit — `STACKSPEC §15` requires services
> to refuse to boot on a placeholder value, and the same standard applies here.

**Sections 1–15 mirror `STACKSPEC §18` item for item.** Keep the numbering
aligned so a conformance run can check them positionally.

---

## 1. Spec versions

| Spec | Version implemented | Notes |
|---|---|---|
| `STACKSPEC` | `<x.y.z>` | |
| `AUTHSPEC` | `<x.y.z>` | |

## 2. Track and selections

Every `CHOICE` the spec defers (`§0.2`). **Recording a selection here is not a
deviation** — it is the only thing required of it. Section 15 is for graded
clauses only.

| Role | Selection | Notes |
|---|---|---|
| Server language / runtime | `<...>` | |
| API framework | `<...>` | |
| Web framework | `<...>` | or `none` for an API-only product |
| Hosting — API | `<...>` | |
| Hosting — web | `<...>` | may differ; split hosting is normal |
| Database engine | `<...>` | |
| Database host | `<...>` | |
| Data access / ORM | `<...>` | |
| Migration tool | `<...>` | |
| Queue substrate | `<...>` | derived from the engine — see §7.2 and section 11 |
| Cache | `<...>` | or `none` |
| Object storage | `<...>` | or `none` |
| Mail provider | `<...>` | transport class is fixed by `§8.1` |
| Error / crash tracker | `<...>` | |
| Uptime checker | `<...>` | must survive an outage of what it watches (`§10.1`) |
| CI platform | `<...>` | |
| Package manager | `<...>` | |
| Task runner | `<...>` | |
| Lint / format | `<...>` | |
| Test runner | `<...>` | |
| Boundary check | `<...>` | `§3.2` requires enforcement, not the tool |

Four roles are choices constrained by a property. Record the selection **and how
it satisfies the property** — a selection alone does not show the bar was met:

| Role | Selection | How it satisfies the property | Clause |
|---|---|---|---|
| API contract format | `<...>` | generators for `<languages>` | `§4.1` |
| Push transport | `<...>` | who holds device tokens, and their register entry | `§8.3` |
| Mail feedback loop | `<...>` | how bounce/complaint reaches the suppression list | `§8.1` |
| Product analytics | `<...>` | where consent is enforced at ingestion | `§10.3` |

## 3. Pinned versions

Exact versions, no ranges. The lockfile is authoritative for libraries; these are
the toolchain pins.

| Component | Version |
|---|---|
| `<runtime>` | `<x.y.z>` |
| `<language>` | `<x.y.z>` |
| `<api framework>` | `<x.y.z>` |
| `<web framework>` | `<x.y.z>` |
| `<package manager>` | `<x.y.z>` |
| `<task runner>` | `<x.y.z>` |
| `<data access>` | `<x.y.z>` |
| Swift / Xcode | `<x.y>` / `<x.y>` |
| Kotlin / Gradle / AGP | `<x.y>` / `<x.y>` / `<x.y>` |

## 4. Minimum supported OS versions

A product decision, not a default (`§0.3`). Changing one is a deliberate,
recorded act.

| Platform | Minimum | Set on | Review due |
|---|---|---|---|
| iOS | `<x.0>` | `<YYYY-MM-DD>` | `<YYYY-MM-DD>` |
| Android | API `<nn>` | `<YYYY-MM-DD>` | `<YYYY-MM-DD>` |
| Browsers | `<baseline>` | `<YYYY-MM-DD>` | `<YYYY-MM-DD>` |

Mobile ships: `<yes / no / later>`. The rules apply either way (`§0.3`).

## 5. Environment inventory

| Tier | URLs | Datastore | Secrets scope |
|---|---|---|---|
| preview/dev | `<...>` | `<...>` | `<...>` |
| staging | `<...>` | `<...>` | `<...>` |
| production | `<...>` | `<...>` | `<...>` |

## 6. Provisioning ledger

**Statuses only. Never record a credential value here.**

| Service | Dev | Staging | Production | Stored in | Owner |
|---|---|---|---|---|---|
| `<database>` | `<have/pending>` | `<...>` | `<...>` | `<...>` | `<...>` |
| `<cache>` | | | | | |
| `<object storage>` | | | | | |
| `<mail provider>` | | | | | |
| `<error tracker>` | | | | | |
| `<push — APNs>` | | | | | |
| `<push — FCM>` | | | | | |

Open rows block nothing structurally, but a `pending` production row means the
product cannot deploy to that tier. Track them here rather than in a chat log.

## 7. Data-collection inventory

Location: `<path>` (`§9.7`). Single source for privacy artifacts and the
processing record.

## 8. Data residency

| Vendor | Processing region | Transfer basis |
|---|---|---|
| `<...>` | `<...>` | `<...>` |

Jurisdictional boundary this product commits to: `<...>`

## 9. Resilience

| Measure | Value |
|---|---|
| RPO — acceptable data loss | `<...>` |
| RTO — acceptable downtime | `<...>` |
| PITR retention window | `<...>` |
| Backup retention window | `<...>` |
| Last successful restore drill | `<YYYY-MM-DD>` |

Backup retention is the outer bound on the erasure guarantee given to data
subjects (`§5.5`). The restore runbook replays the erasure suppression list.

## 10. Classification and retention

Field classification: `<path>`
Per-table retention declarations: `<path>`

## 11. Queue economics

| Property | Value |
|---|---|
| Substrate | `<datastore-resident / external + outbox>` |
| Trigger | `<...>` |
| Drain schedule | `<...>` |
| Batch size | `<...>` |
| Steady-state load | `<...>` |

If the substrate is external, the outbox and relay design belongs in section 14
as a capability gap.

## 12. Certificate pinning

| Platform | Pins? | Rationale | Rotation procedure |
|---|---|---|---|
| iOS | `<yes/no>` | `<...>` | `<... or n/a>` |
| Android | `<yes/no>` | `<...>` | `<... or n/a>` |

A declared decision, not a default (`§9.8`). Unrotatable pins have bricked more
apps than they have saved.

## 13. Assurance cadence

| Item | Value |
|---|---|
| Dependency-advisory triage window | `<...>` |
| Security review / pen-test cadence | `<...>` |
| Last review | `<YYYY-MM-DD>` |
| Vulnerability disclosure contact | `<...>` |

## 14. Capability gaps

Every place a `CHOICE` could not supply a capability the spec requires (`§0.4`),
and the compensating control adopted. **A gap with no control recorded is a
violation**, not a gap.

| Clause | Capability missing | Compensating control | Approved by | Date |
|---|---|---|---|---|
| `<§7.2>` | `<transactional enqueue>` | `<outbox + relay>` | `<...>` | `<...>` |

Gaps this spec anticipates: non-transactional enqueue (`§7.2`), absent datastore
constraints (`§5.2`), absent PITR (`§5.5`), absent statement timeouts (`§5.6`),
absent per-PR previews (`§13.2`).

## 15. Deviations

Every `SHOULD` not followed and every `MUST` waived. **`CHOICE`s do not belong
here** — they go in section 2. Keeping this table small is what keeps it
meaningful.

| Clause | Level | What we do instead | Reason | Approved by | Date |
|---|---|---|---|---|---|
| `<§n.n>` | `<SHOULD/MUST>` | `<...>` | `<...>` | `<...>` | `<...>` |

Two things that are **never** recordable here:

- **Third-party analytics** (`§10.3`). A consent-lawfulness rule, not a vendor
  preference. There is no approver who can waive it.
- **A third-party push vendor** (`§8.3`). Server-owned delivery is a `MUST`.
