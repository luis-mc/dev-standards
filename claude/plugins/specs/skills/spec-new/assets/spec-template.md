<!--
==============================================================================
  SPECIFICATION TEMPLATE
==============================================================================

  HOW TO USE THIS FILE

  1. Copy it to `specs/<feature-name>.md`.
  2. Delete this comment block.
  3. Delete every section marked [CONDITIONAL] or [OPTIONAL] that does not
     apply. A spec padded with empty sections is worse than a short one —
     readers learn to skim, and skimming is how requirements get missed.
  4. Fill placeholders written as [LIKE THIS].
  5. Keep the requirement-ID scheme. It is the single most load-bearing
     convention in this template.

  ---------------------------------------------------------------------------
  SECTION TIERS — what to keep
  ---------------------------------------------------------------------------

  A small feature spec (one component, a few endpoints) needs only the CORE
  sections and will land around 150–400 lines. That is a good spec. Do not
  inflate it.

  CORE (always)              §0, §1, §3, §4, §5+, Failure modes,
                             Configuration, Test gate, Conformance gate,
                             Design rationale
  CONDITIONAL (when it applies)
                             Decision record — when choices were contested
                             §2 Technology binding — when the spec must stay
                               stack-neutral, or a generator will implement it
                             Threat model — anything handling credentials,
                               personal data, money, or third-party input
                             Adoption — when the target system already has
                               data or users
                             Retention & jobs — when the feature stores
                               anything with a lifecycle
                             Error taxonomy — when the feature has an API
  OPTIONAL (nice to have)    Appendix A reference flows, Appendix B
                             anti-patterns, Observability, Performance budgets

  ---------------------------------------------------------------------------
  AUTHORING RULES — the ones that actually decide whether a spec works
  ---------------------------------------------------------------------------

  1. EVERY REQUIREMENT GETS AN ID. `R<section>.<n>`. A requirement without an
     ID cannot be cited by a test, a review comment, or an audit finding, and
     will therefore be silently dropped by at least one of them.

  2. IF YOU CANNOT NAME THE TEST, IT IS NOT A REQUIREMENT — it is a wish.
     Move it to the rationale section or cut it. This single rule removes most
     of the bulk from a bad spec.

  3. NO REQUIREMENT SATISFIABLE BY INTENT ALONE. "Handle errors carefully" is
     unimplementable and untestable. "On timeout, retry with jittered backoff
     to a maximum of 3 attempts, then fail closed" is both.

  4. STATE FAIL-OPEN vs FAIL-CLOSED FOR EVERY DEPENDENCY, deliberately, with
     the reason. Left unstated it gets decided by whoever writes the catch
     block, and they will pick whichever makes the test pass.

  5. CEILINGS, NOT JUST DEFAULTS. Say which direction config may move. "30
     days default" invites someone to set 3 years; "30 days default, 90 days
     ceiling, may only be shortened" does not.

  6. RATIONALE LIVES SEPARATELY FROM REQUIREMENTS. Requirements say what;
     rationale says why. Mixing them makes requirements unquotable and
     rationale unfindable — and the *why* is what stops a future reader
     deleting a control they don't understand.

  7. PROHIBITIONS CARRY THEIR REASON INLINE. "MUST NOT cache this response"
     gets removed by the next person optimising latency. "MUST NOT cache this
     response — it is user-scoped and a shared cache would cross accounts"
     does not.

  8. WRITE THE OUT-OF-SCOPE LIST, AND THE SEAM. For anything deliberately not
     built, name the single place a future implementation would change. That
     converts "we'll do it later" from a rewrite into an edit.

  9. ONE CONCEPT, ONE NAME, EVERYWHERE. Pick the term in §1 and never
     synonym-drift. A generator will create two entities if you use two words.

  10. DEFINE THE VERIFICATION COMMAND. A spec that cannot end in a pass/fail
      check makes the reader the verification loop.

  11. NUMBERING IS AN INTERFACE, NOT FORMATTING. Every reference in this spec,
      in its tests, and in every future review comment resolves through the
      numbering. It is checked mechanically; these are the rules it is checked
      against.

      (a) `§` AND `R` ARE DIFFERENT NAMESPACES.
            `§4.2` = a heading.  `R4.2` = a requirement.
          One existing does not imply the other. Do not write `§4.2` meaning
          requirement `R4.2`. A three-component `R6.6.1` is always wrong — a
          requirement identifier has exactly two components, so you meant §6.6.1.

          A bare `§4.2` also means *this* document. To cite another one, name
          it: `OTHERSPEC §4.2`. Without the prefix the reference resolves
          against your own headings — and if both documents happen to number a
          §4.2, it resolves silently to the wrong section.

      (b) HEADING DEPTH MATCHES THE NUMBER.
            `## 4. Title`      one component,  two hashes
            `### 4.2 Title`    two components, three hashes
            `#### 4.2.1 Title` three components, four hashes
          Every subsection has a parent heading: no `### 4.2` without a `## 4`.
          Headings appear in ascending order, and no number is used twice.

      (c) A REQUIREMENT'S FIRST COMPONENT IS ITS SECTION. `R4.x` is defined in
          `§4` — always. Within a section, requirements are numbered from 1,
          ascending, in document order. Moving a requirement to another section
          means giving it that section's number.

      (d) DEFINE EACH REQUIREMENT EXACTLY ONCE, in this shape, so it can be
          found and cited mechanically:
            - **R4.7** — [the requirement].
          One dash-terminated bolded identifier. Citing it elsewhere is just
          `R4.7` in prose — unbolded, so a citation is never mistaken for a
          second definition.

      (e) NUMBERING IS APPEND-ONLY. NEVER RENUMBER.
          - Deleting §5 leaves §5 retired and the sequence jumping §4 → §6.
            Leave the gap. Renumbering §6 to §5 invalidates every `R6.x`
            identifier and every citation of them, silently.
          - Inserting between `R4.9` and `R4.10` uses a letter suffix: `R4.9a`.
          - A retired number is never reused for a new requirement. A stale
            citation that resolves to the WRONG requirement is worse than one
            that fails to resolve.
          This applies when you delete the [CONDITIONAL] and [OPTIONAL] sections
          below: leave the gaps in the section numbering. A spec that runs
          §0, §1, §3, §7 is correct.

      Verify with the `spec-check` skill, which ships the checker alongside
      it in the luismc-specs plugin: `python3 assets/spec_check.py <this-file>`
      from that skill's directory. It
      checks every rule above and reports gaps separately from errors, because
      only the author knows whether a gap was deliberate. Pass --external
      NAME=path for each document this spec cites by name.
==============================================================================
-->

# [FEATURE NAME] Specification

**Status:** Normative
**Version:** 0.1.0
**Applies to:** [WHICH SYSTEMS / APPLICATIONS THIS BINDS]
**Audience:** [e.g. Claude Code as a generation guide, and human implementers/reviewers]
**Owner:** [NAME OR TEAM]
**Last reviewed:** [DATE]

---

## 0. How to use this document

### 0.1 What this document is

[ONE PARAGRAPH: what problem this specifies a solution to, and what a reader
should be able to build or verify from it.]

**What this document is not:** [NAME THE ADJACENT THINGS IT DOES NOT COVER, so
a reader who needs those stops looking here. e.g. "It does not specify the UI,
the deployment topology, or the data warehouse export."]

### 0.2 Reading order

1. [FIRST THING TO READ — usually scope, or a binding/discovery step]
2. [...]
3. [LAST — usually the conformance gate]

[IF A GENERATOR WILL IMPLEMENT THIS: state explicitly what must not be
generated before which step completes.]

### 0.3 Requirement language

**MUST** / **MUST NOT** are binding. **SHOULD** / **SHOULD NOT** may be
deviated from only with a recorded justification and a named approver (see
Deliverables). **MAY** is genuinely optional.

Requirements are numbered `R<section>.<n>` and are individually citable.
Letter suffixes (`R<section>.<n>a`) mark requirements added after first
publication, so existing citations stay valid. Numbering is append-only: a
retired number is never reused, and sections are never renumbered to close a
gap. Invariants are numbered `INV-<n>` and are
distinguished from requirements: an invariant is a property that must hold at
every instant, not an action to take.

---

## Decision record  <!-- [CONDITIONAL] Include when choices were contested, or when merging sources -->

| # | Question | Resolution | Consequence |
|---|---|---|---|
| D1 | [THE QUESTION] | [WHAT WAS DECIDED] | [WHAT NOW FOLLOWS FROM IT] |

> **Reading note on D[n].** [WHERE A DECISION WAS CLOSE, REVERSED, OR IS LIKELY
> TO BE RELITIGATED: record the argument. State the one condition that would
> legitimately reopen it. This is what stops the same debate recurring in six
> months with less context than you have now.]

---

## 1. Scope

### 1.1 In scope

| Area | Covered |
|---|---|
| [AREA] | [WHAT SPECIFICALLY] |

### 1.2 Out of scope

- **[THING].** [WHY it is excluded — capacity, risk, or deliberate deferral.
  "Not now" and "not ever" are different and should read differently.]

### 1.3 Deferred extension points

| Deferred capability | The seam that keeps it cheap |
|---|---|
| [CAPABILITY] | [THE SINGLE PLACE A FUTURE IMPLEMENTATION WOULD CHANGE] |

### 1.4 Definitions

| Term | Meaning |
|---|---|
| [TERM] | [PRECISE MEANING — the one used everywhere below, without synonyms] |

---

## 2. Technology binding  <!-- [CONDITIONAL] Keep only if this spec is deliberately stack-neutral -->

### 2.1 Resolution order

1. [WHERE TO LOOK FIRST for an already-declared stack]
2. [WHAT TO INFER FROM]
3. **Stop and ask.** [WHAT MUST NEVER BE ASSUMED]

### 2.2 Dimensions that MUST be resolved before implementation

| Dimension | Why it matters here |
|---|---|
| [e.g. persistence engine] | [WHICH REQUIREMENTS DEPEND ON IT] |

### 2.3 Binding rules

- **R2.1** — Generated code **MUST** match the surrounding project's existing
  conventions. Where this specification and project convention conflict on
  *style*, the project wins. Where they conflict on a **MUST** of *behaviour*,
  this specification wins and the conflict **MUST** be recorded.
- **R2.2** — Prefer already-adopted libraries. New dependencies only for
  [CAPABILITIES THAT MUST NOT BE HAND-ROLLED].
- **R2.3** — Implementation **MUST** be idempotent and deterministic:
  re-running against an unchanged project produces no diff.

### 2.4 Capability fallbacks

| Assumed capability | Used by | If unavailable |
|---|---|---|
| [CAPABILITY] | [WHICH REQUIREMENT] | [EQUIVALENT GUARANTEE, or **blocking gap — surface it**] |

[Mark at least one as a blocking gap if one exists. A fallback table with no
blocking gaps usually means the hard question wasn't asked.]

### 2.5 Stack Profile — REQUIRED written artifact

- **R2.4** — Implementation **MUST** produce a Stack Profile document recording
  how each abstraction here was bound to concrete technology: entity → table,
  attribute → column with native type and nullability, [OTHER MAPPINGS]. It is
  written **before** code and updated when a binding changes.
- **R2.5** — It **MUST** carry a **Deviations** section. Empty is a valid
  outcome; *absent* means the question was never asked.
- **R2.6** — It is required reading for any subsequent implementation run
  against the same project. Without it, a second run re-derives bindings and
  may derive them differently.

---

## 3. Architecture

### 3.1 Components

[WHAT EXISTS AND WHAT EACH IS RESPONSIBLE FOR. Prose or a table. Keep it to
what a reader needs before §4 makes sense.]

### 3.2 Invariants

Properties that hold at every instant. Each **MUST** be independently testable.

- **INV-1** — [PROPERTY]. Verified by `[TEST NAME]`.
- **INV-2** — [PROPERTY]. Verified by `[TEST NAME]`.

### 3.3 Operation lifecycle

Every [REQUEST / JOB / TRANSACTION] passes through these stages in order:

1. [STAGE] — [WHAT IS CHECKED OR DONE]
2. [...]

- **R3.1** — Stages [N] through [M] are **deny gates**: each either passes or
  terminates the operation. None may be skipped for an input believed safe, and
  none may be satisfied by a client-supplied value.

### 3.4 Trust boundaries

| Boundary | What crosses it | What is validated on arrival |
|---|---|---|
| [BOUNDARY] | [DATA] | [VALIDATION] |

---

## 4. Data model  <!-- [CONDITIONAL] Keep if the feature persists anything -->

### 4.1 Type conventions

| Abstract type | Meaning | Binding note |
|---|---|---|
| `id` | [OPAQUE IDENTIFIER — state whether it is guessable and whether that matters] | |
| `timestamp` | [PRECISION AND TIMEZONE — state both, or someone will pick] | |

Markers used below: `[ENC]` encrypted at rest · `[HASH]` stored only as a
digest · [ADD YOUR OWN]

### 4.2 Entity: `[NAME]`

[ONE LINE: what it represents.]

| Attribute | Type | Notes |
|---|---|---|
| `id` | `id` | PK |
| `[NAME]` | `[TYPE]` | [CONSTRAINT, DEFAULT, WHY IT EXISTS] |

**Indexes:** [EACH INDEX AND THE QUERY IT SERVES — an index without a named
query is speculation]

**Constraints:** [ENFORCED AT THE STORAGE LAYER WHERE POSSIBLE. State which
are storage-level and which are application-level; the difference is whether
a bug can violate them.]

- **R4.1** — [ANY RULE THE TABLE CANNOT EXPRESS]

### 4.3 Forward compatibility

- **R4.n** — [WHAT MUST NOT BE ASSUMED, so a deferred extension stays cheap.
  e.g. "no query may assume a single [SCOPE]; all access goes through the
  predicate helper of §[N]".]

---

## 5. [FIRST DOMAIN SECTION]

<!--
  Everything specific to this feature goes in sections 5..N. Structure each
  the same way:
    - a short prose paragraph on what this part does and why it is shaped
      this way
    - numbered requirements
    - a table where the content is tabular

  Order sections by dependency: a reader should never need a later section
  to understand an earlier one.
-->

---

## [N]. Failure modes

**Every external dependency gets a row.** Left unstated, this is decided by
whoever writes the catch block.

| Dependency | Unavailable → | Rationale |
|---|---|---|
| [DEPENDENCY] | **fail closed** / **fail open** | [WHY THIS DIRECTION. Asymmetry between rows is normal and should be explained — it is usually the most considered decision in the document.] |

- **R[N].1** — Each failure mode above **MUST** have a distinct, alertable
  signal. A dependency failure indistinguishable from normal operation cannot
  be operated.
- **R[N].2** — [WHAT MUST NOT DEGRADE SILENTLY]

---

## [N]. Error taxonomy  <!-- [CONDITIONAL] Keep if this feature has an API -->

**Permitted codes:** [CLOSED LIST]

| Code | Status | Raised by | Notes |
|---|---|---|---|
| `[code]` | [STATUS] | §[N] | [WHEN] |

- **R[N].1** — The mapping is **exhaustive and closed**. A response pairing a
  code with a status not listed here is a defect, asserted by
  `test_error_status_mapping_exhaustive`.
- **R[N].2** — [WHAT MUST NOT APPEAR IN AN ERROR RESPONSE: internal
  identifiers, stack traces, query text, personal data, existence signals.]

---

## [N]. Configuration reference

| Key | Default | Ceiling | Direction | Section |
|---|---|---|---|---|
| `[key]` | [VALUE] | [MAX] | may only [tighten / loosen] | §[N] |

- **R[N].1** — Configuration may **tighten** a value below its default; it
  **MUST NOT** loosen one past its ceiling. A configuration that would is a
  **startup failure**, not a warning.
- **R[N].2** — **Startup validation.** The system **MUST** refuse to start
  when: [ENUMERATE EVERY CONDITION — a missing secret, a placeholder value, a
  value past a ceiling, a required dependency unreachable. Each condition gets
  its own test.]

---

## [N]. Observability  <!-- [OPTIONAL but recommended] -->

- **R[N].1** — [WHAT MUST BE EMITTED — the signals needed to answer "is this
  working?" without database access]
- **R[N].2** — [WHAT MUST NOT BE LOGGED — secrets, personal data, full
  payloads. Be specific; "don't log sensitive data" is not actionable.]
- **R[N].3** — [WHAT MUST ALERT, and at what threshold]

---

## [N]. Threat model and control mapping  <!-- [CONDITIONAL] -->

| # | Threat | Controls |
|---|---|---|
| T1 | [THREAT] | [REQUIREMENT IDS THAT ANSWER IT] |

- **R[N].1** — The implementation **MUST** ship this table instantiated, each
  control mapped to its concrete code location. An unmapped threat is an
  unimplemented control until proven otherwise.

---

## [N]. Adoption in an existing system  <!-- [CONDITIONAL] Keep whenever the target already has data or users -->

### [N].1 Inventory first

- **R[N].1** — Before any migration code, document: [WHAT EXISTS TODAY, ITS
  SHAPE, AND ITS KNOWN DATA-QUALITY PROBLEMS]. A migration planned without this
  discovers its data problems in production.

### [N].2 Import rules

- **R[N].2** — Fields this spec requires but the legacy system lacks become
  **gates**, not blockers to import. Blocking import locks out the entire
  existing population on cutover day.
- **R[N].3** — [COLLISIONS AND AMBIGUITIES] **MUST** be resolved before import
  through a documented, audited procedure. Automatic silent merging **MUST
  NOT** happen.

### [N].3 Cutover and verification

- **R[N].4** — Dual-run period with [WHICH SYSTEM IS AUTHORITATIVE FOR WRITES],
  a documented rollback point, and advance notice to affected users.
- **R[N].5** — At completion, legacy paths are **deleted, not disabled**.
  Disabled code is re-enabled by the next person who doesn't know why it was
  disabled.
- **R[N].6** — Re-run the full test gate **against migrated data**, not only
  freshly created data. Migrated rows exercise different paths.

---

## [N]. Deliverables

| Document | Contents |
|---|---|
| Stack Profile | §2.5 |
| Configuration reference | Every key, default, ceiling, and recorded deviation |
| Test coverage manifest | Every test-gate line → test name → source location |
| Deviation register | Every recorded **SHOULD** deviation, its approver, its review date. **This specification ships with none** |
| [RUNBOOK] | [DETECTION, PROCEDURE, RESTORATION, DECISION AUTHORITY] |

[One runbook per way this can fail in production. If a requirement says "fail
closed", there is an operational incident behind it that needs a procedure.]

---

## [N]. Test gate

All of these **MUST** exist and pass.

- **R[N].1** — **Every line below corresponds to a test that exists by name.**
  A prose checklist is not machine-checkable: CI can assert
  `test_x_does_y` exists and passes; it cannot assert a bullet is "covered in
  spirit".
- **R[N].2** — Naming: `test_<subject>_<expected_behaviour>`. Names **MUST**
  be stable across changes — a renamed test silently drops coverage.
- **R[N].3** — A **coverage manifest** maps every line here to its test name
  and location. CI fails when a line has no test, when a named test is absent,
  **or when a test claims a line no longer present**.

### [N].1 Canonical test names — normative

| Test name | Asserts | Requirement |
|---|---|---|
| `test_[...]` | [WHAT] | R[N].[N] |

<!-- Cover at minimum: every invariant; every deny gate; every fail-open /
     fail-closed decision; every prohibition; the concurrent case for anything
     enforced transactionally; and the boundary of every ceiling. -->

---

## [N]. Conformance gate

Implementation is **not complete** until:

- [ ] Every **MUST** implemented or recorded as an approved deviation
- [ ] Every canonical test present by name and passing
- [ ] Coverage manifest complete and CI-enforced
- [ ] Stack Profile written, Deviations section present
- [ ] Every deliverable above exists
- [ ] `[THE ACTUAL COMMAND THAT RETURNS PASS/FAIL]` runs clean
- [ ] [ANY REVIEW OR AUDIT THAT MUST PASS]

---

## [N]. Design rationale

Why, not what. Kept separate so requirements stay quotable and reasoning stays
findable — and so a future reader doesn't delete a control they don't
understand.

| Decision | Rationale |
|---|---|
| [WHAT WAS DECIDED] | [WHY, INCLUDING THE ALTERNATIVE REJECTED AND THE COST ACCEPTED] |

---

## Appendix A — Reference flows  <!-- [OPTIONAL] -->

**[FLOW NAME]**

1. [STEP] ([REQUIREMENT ID])
2. [...]

[Include a flow only where the requirement text alone leaves ordering ambiguous.]

---

## Appendix B — Anti-patterns  <!-- [OPTIONAL, high value] -->

Real, recurring implementation shapes. Presence of any is a finding regardless
of how the surrounding code reads.

| Anti-pattern | Why it fails |
|---|---|
| [THE SHAPE] | [THE CONSEQUENCE] (R[N].[N]) |

[Populate this from code review as you go. It becomes the fastest available
self-review — a reader can grep for each shape before running the gate.]
