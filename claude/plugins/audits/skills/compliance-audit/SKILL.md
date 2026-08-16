---
description: Advanced, production-grade regulatory and data privacy compliance audit of the current repo. Grounded in GDPR, CCPA/CPRA, HIPAA, SOC 2 Type II, NIST SP 800-53 Rev. 5, FedRAMP High, and NIS2 frameworks. Produces severity-ranked, statutory-mapped engineering findings. Does not auto-fix. Use when the user requests a compliance audit, privacy review, GDPR assessment, or invokes /luismc-audits:compliance-audit.
---

# Expert-Level Regulatory & Data Privacy Compliance Audit

Execute a deep architectural and regulatory compliance sweep across the repository codebase. This skill **identifies, maps, and reports—it does not remediate**. Remediation is a deliberate follow-up step so compliance gaps can be triaged, reviewed with legal or product teams, and prioritized before code modifications are executed.

This is an advanced technical engineering review of application logic, data flow, and architecture—it does not constitute final legal counsel. Flag structural gaps with high cryptographic and logical precision, linking findings explicitly to statutory controls when code structures directly reveal non-compliance.

## Process

1. **Regulatory Scoping & Data Taxonomy:** Identify the application's data ingestion footprint. Map all vectors processing Personal Identifiable Information (PII), Protected Health Information (PHI), financial markers, or authentication metadata. Determine active jurisdictional boundaries (e.g., EU data residency vs. US sovereignty). Skip irrelevant checks to eliminate noise (e.g., no third-party tracking -> skip cookie-consent enforcement).
2. **Server-Side Enforcement Validation:** Never trust client-side abstractions. Verify that data subject requests, consent gates, and access controls are strictly validated, bound, and enforced at the server runtime, API controller, or database level.
3. **Token-Optimized Evaluation:** Use Claude Code's native file-viewing tools to preserve your **Prompt Cache** and prevent heavy, redundant context expansion. Keep terminal outputs concise and focused on high-severity architecture gaps.

## Severity & Regulatory Rubric

Classify findings strictly based on regulatory exposure, statutory liability, and operational risk:

- **P0 (Critical) — Direct Compliance Breach & Data Spillage:** Systemic failure of a core statutory control resulting in clear legal exposure, data spillage across user boundaries, or regulatory penalties (e.g., "Delete Account" retains un-anonymized PII/PHI, un-hashed credentials, or missing non-repudiation logs for critical administrative actions).
- **P1 (High) — Deficient Statutory Right or Architectural Vulnerability:** A regulatory control exists but is incomplete or bypassable under standard conditions, or violates security-adjacent compliance mandates (e.g., data export omits core user history tables, session tokens lack absolute timeouts, or cross-tenant role validation is missing at the route handler level).
- **P2 (Medium) — Control Deficit & Weakened Auditability:** Structural or architectural gaps that diminish defensibility during an external regulatory audit but do not actively leak data (e.g., weak log retention enforcement, missing append-only configurations, or lack of structured schema validation on cached session stores).
- **P3 (Low) — Operational Hygiene & Best-Practice Deviations:** Minor accessibility discrepancies with technical workarounds, missing localized cookie-banner strings, or minor best-practice drift.

## Universal Compliance Checklist

### 1. Data Subject Rights & Cryptographic Erasure (GDPR / CCPA / CPRA)
- **Verified Right to Erasure (Soft-Delete Avoidance):** Audit deletion code paths. Ensure account removal executes an absolute purge or cryptographic erasure across all persistent layers. Pure soft-deletes (e.g., toggling an `is_deleted` flag or appending a `deleted_at` timestamp) that leave plaintext PII/PHI recoverable in primary DBs, block storage, or logs violate GDPR Article 17.
- **Complete Portability / Right to Access:** Verify that user data export routines programmatically compile and return the complete digital footprint of the user (including access logs, telemetry records, and nested relational metadata), rather than just basic profile rows.
- **Right to Rectification Workflow:** Audit data modification pathways. Verify that users can natively correct, update, or rectify their own PII/PHI via authenticated server gates. Flag architectures that force manual admin intervention to update basic user profiles without a corresponding, transparent audit trail.

### 2. Consent Lifecycle & Boundary Gating (GDPR / ePrivacy / HIPAA)
- **Server-Side Consent Enforcement:** Audit application route middleware and API controllers. Validate that acceptance of Terms of Service (ToS) or Privacy Policies is verified on the server before processing or storing downstream data. A client-side checked state with no backend verification is non-compliant.
- **ePrivacy Tracking & Cookie Gating:** Identify any integration points with analytics, telemetry, or behavioral tracking SDKs. Verify that these external tracking scripts remain dark and completely blocked from firing until a valid, server-recorded affirmative consent state is achieved.
- **Granular Re-Consent Triggers:** Scan authentication and middleware architectures for explicit legal-version tracking blocks. If privacy policies or data-processing terms change, the code must programmatically restrict access until re-consent is recorded.
Use code with caution.

### 3. Non-Repudiation Audit Trails & Logging (SOC 2 Type II / NIS2 / NIST SP 800-53)
- **Administrative Access Non-Repudiation:** Audit all privilege-heavy API controllers and admin panel interfaces. Ensure every high-value event (viewing cross-tenant PII/PHI, exporting user collections, mutating roles, or altering global settings) generates an immutable audit trail capturing the exact Actor, Action, Target, and Timestamp.
- **Tamper-Resistant Infrastructure:** Verify that the system audit logging mechanism is structurally isolated or directed to append-only ingestion pipelines. Local application code must be incapable of modifying or purging historically written audit logs.
- **PII Leakage in Logging Systems:** Scan system exceptions, console log lines, and debug hooks. System loggers must programmatically strip, mask, or hash PII, tokens, session cookies, credit card numbers, or internal memory dumps before writing to persistent disk storage.

### 4. Session Architecture & Boundary Hardening (FedRAMP High / DoD IL6)
- **Absolute & Idle Session Timeouts:** Audit session wrappers and authentication cookies. Ensure privileged interfaces (admin dashboards, billing views, security configurations) enforce strict, short idle timeouts and maximum absolute session lifespans.
- **Role-Based Access Control (RBAC) Integrity:** Trace API endpoints and mutations. Access to data objects must be programmatically scoped using strict server-side RBAC or Attribute-Based Access Control (ABAC), ensuring that a generic administrative role cannot bypass horizontal multi-tenant partition boundaries.
- **Data Residency & Localization:** Ensure cloud-regional storage routing logic is structurally sound. Code paths must strictly prevent cross-border data transfers if handling data sets bounded by strict geographic localization laws (e.g., EU-only computing boundaries).

### 5. Minimization, Retention, & Downstream Privacy (NIS2 / HIPAA)
- **Over-Collection (Data Minimization):** Flag database schemas capturing data vectors that the application does not actively utilize for its core operational functions (violating GDPR Article 5 data minimization rules).
- **Programmatic Retention Schedules:** Verify that the application features active, automated clean-up workers, cron processes, or database time-to-live (TTL) configurations that structurally drop or anonymize data once its legal or operational retention window closes.
- **Vendor/Third-Party Data Flow Alignment:** Map all outgoing webhook vectors, API aggregators, and middleware pipelines. Cross-reference third-party data transmissions against the application's stated disclosure clauses to ensure no undocumented leakage to unvetted processors occurs.

### 6. Accessibility & Structural Interface Compliance (WCAG 2.2 AAA / Section 508)
- **Keyboard Navigation & Interactive Focus:** Audit critical layout routes (authentication screens, checkout funnels, primary workspaces). Ensure all user interactions can be completed natively using keyboard mapping alone, verifying the complete exclusion of focus traps.
- **Semantic ARIA Structuring:** Scan frontend components for interactive fields, buttons, and visual illustrations. Ensure proper usage of semantic HTML layout structures and descriptive ARIA labels to ensure full screen-reader accessibility.
- **Contrast Ratios & Visual Validation:** Ensure status indicators, error banners, and functional actions enforce standard WCAG contrast ratios to safeguard readability for visually impaired users.
- **Contrast Ratios on Critical UI:** Verify that error messages, form validation alerts, status badges, and primary action buttons enforce standard WCAG contrast boundaries to safeguard readability for visually impaired users.

## Output Formatting

**No Conversational Fluff.** Omit greetings, post-audit summaries, or introductory commentary. Move directly to the ranked regulatory compliance matrix, ordered from highest severity (P0) to lowest (P3). If no compliance gaps are verified, output: `[COMPLIANCE OK] Systems conform entirely to defined regulatory standards.`

For each finding, you must output exactly this structural layout:

*   **Finding [ID]: [Short, Statutory Defect Name]**
    *   **Severity:** [P0 / P1 / P2 / P3]
    *   **Framework Mapping:** [e.g., GDPR Art. 17, CCPA § 1798.105, SOC 2 CC6.3, HIPAA § 164.312, NIST SP 800-53 AU-2]
    *   **Location:** `[File path]:[Line number]`
    *   **Defect Statement:** One sentence isolating the exact architectural or server-side logic failure breaking compliance.
    *   **Concrete Exposure Scenario:** A specific, technical description of a realistic event (e.g., a data erasure request, an administrative account compromise, or a third-party audit) where this specific line of code creates absolute regulatory liability, data spillage, or a major compliance penalty.
