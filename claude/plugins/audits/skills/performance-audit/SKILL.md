---
description: Advanced, production-grade systems and runtime performance audit of the current repo. Universally applicable across multi-paradigm database architectures, caching models, and full-stack execution environments. Grounded in Core Web Vitals (LCP, INP, CLS), execution planning, memory leaks, and edge/serverless boundaries. Detects database round-trip waste, connection pool exhaustion, retry-amplified load storms, and cross-service network/IO overhead. Produces severity-ranked findings. Does not auto-fix. Use when the user requests a performance audit, latency review, reports slow APIs or an overloaded database, or invokes /luismc-audits:performance-audit.
---

# Expert-Level Systems & Runtime Performance Audit

Execute a deep architectural and empirical performance sweep across the codebase. This skill **identifies, quantifies, and reports—it does not remediate**. Remediation is a deliberate follow-up step so bottlenecks can be triaged, measured, and benchmarked before code changes land.

## Process

1. **Architectural & Runtime Mapping:** Identify the host deployment topography (Serverless/Edge Functions vs. long-lived Node.js/Docker/Containerized instances). Map the rendering architecture (Server-Side Rendering, Static/Incremental Hydration, or Client-Side SPAs). Serverless environments must be evaluated for cold starts and resource connection hoarding; long-lived processes must be audited for event-loop blocks and memory leaks.
2. **Empirical Evidence First:** Every finding must be anchored in mechanical reality. If an execution plan or bundle analyzer trace cannot be directly run, evaluate the code mathematically (e.g., algorithmic complexity $O(N^2)$), compute precise database row processing scales, or calculate frontend payload bytes. Differentiate strictly between *proven regressions* and *theoretical bottlenecks*.
3. **Token-Optimized Diagnostics:** Use Claude Code's native file-viewing tools to preserve your **Prompt Cache** and avoid duplicative, heavy file reading. Keep terminal outputs highly condensed.

## Severity & Algorithmic Rubric

Classify findings strictly based on runtime impact, traffic scale, and compute complexity:

- **P0 (Critical) — Cascading Failures & Unbounded Demise:** Bottlenecks causing request timeouts, server memory exhaustion (OOM), database deadlocks, connection pool exhaustion, or retry-amplified load storms. High-traffic loops exhibiting superlinear execution scaling ($O(N^2)$ or worse), unindexed scans on high-growth tables/collections, or N+1 queries on core list views.
- **P1 (High) — User-Facing Latency Sinks:** Blockages that visibly compromise Core Web Vitals (LCP, INP). Adds >500ms of avoidable Time to First Byte (TTFB), stacks avoidable database or network round-trips on hot request paths, or generates heavy, uncompressed, un-paginated payloads on standard customer pathways.
- **P2 (Medium) — Compound Inefficiencies:** Real systemic waste on secondary, low-traffic routes or small datasets that will linearly expand into a high-severity block as traffic or the database grows.
- **P3 (Low) — Micro-Optimizations:** Superficial style or best-practice deviations with no current measurable latency or CPU impact.

## Universal Performance Checklist

### 1. Persistence & Data Layer Hardening (Relational & NoSQL)
- **Relational & Document N+1 Queries:** Audit ORM, query builders, or raw data access layouts. Flag loops or map iterations issuing one query per item instead of a batch, join, or native multi-key inclusion logic.
- **Query Plan Degradation (Missing Indexes):** Scan fields inside filtering clauses (`where`), sorting rules (`orderBy`), and join operations (`JOIN`) that lack matching indexes (such as B-Tree, GIN, or Compound indexes) in the data schema.
- **Unbounded Cursor Sinks:** Verify that all data listings implement explicit pagination controls (limit/offset, token-based, or cursor-based pagination). List endpoints must never run without limits, preventing a table from dumping raw records into server RAM.
- **Over-Fetching Rows:** Identify queries pulling down full records, wildcard columns (`SELECT *`), or massive object graphs when only a few specific column strings or primitive properties are utilized downstream.
- **Transaction Lifespan Leakage:** Ensure database transactions or atomic blocks do not remain open while waiting on non-database asynchronous I/O operations (e.g., third-party API calls, slow external system reads, or long-running computational loops).

### 2. Database Round-Trip Economics & Load Amplification
- **Sequential Query Waterfalls:** Flag request handlers issuing multiple independent database queries as sequential awaits. Independent reads must execute concurrently (`Promise.all` with throttling) or be consolidated into a single joined/batched query. Compute the round-trip tax: N sequential queries × per-query network latency = avoidable TTFB with zero N+1 pattern present.
- **Per-Request Round-Trip Budget:** Count total database round-trips issued per request handler on core pathways. Flag any hot-path endpoint exceeding ~3 round-trips per request; each excess trip multiplies under concurrency into raw connection, network, and CPU pressure against the database.
- **Connection Pool Exhaustion & Connection Storms:** Audit pool configuration against deployment topology. Serverless/edge functions must route through an external pooling layer (e.g., PgBouncer, RDS Proxy, or driver-level HTTP pooling) — never open direct database connections per invocation. Long-lived processes must bound pool size below the database's max connections divided by instance count, and pools must define acquisition timeouts.
- **Missing Query & Statement Timeouts:** Every database client and query path must enforce explicit query/statement timeouts. Absent timeouts allow a single slow query to pin connections, drain the pool, and stall every unrelated request queued behind it.
- **Retry Storms & Load Amplification:** Flag retry logic lacking exponential backoff, jitter, and hard retry caps. Uncapped retries against a degraded database multiply load precisely when the system can least absorb it, converting a slowdown into a full outage.
- **Database-as-Queue Polling:** Identify cron jobs, background workers, or client loops polling database tables on tight intervals. Polling hot tables generates constant baseline query load and lock churn; flag for event-driven alternatives (LISTEN/NOTIFY, change streams, or a dedicated queue system).
- **Lock Contention & Hot Rows:** Identify `SELECT ... FOR UPDATE`, serializable isolation transactions, or frequent concurrent writes targeting shared counter/status/singleton rows. Flag transactions holding row or table locks across multiple statements on high-write tables — these manifest as latency explosions while database CPU appears healthy.
- **Computation in the Wrong Tier:** Flag application code fetching full row sets solely to count, sum, filter, sort, or deduplicate in application memory. Aggregation, filtering, and ordering must be pushed down into the database engine, which returns computed bytes instead of raw row graphs — saving network transfer, server RAM, and CPU simultaneously.

### 3. Advanced Caching Architecture & Tiering
- **Stale-While-Revalidate (SWR) & Cache-Control:** Audit all network responses and API outputs. Static or slow-changing data must leverage strict HTTP cache headers (`Cache-Control: public, max-age=X, s-maxage=Y, stale-while-revalidate=Z`) to offload traffic from your servers straight to the global CDN edge.
- **Request Cascades & Deduplication:** Audit server-side data fetching. Ensure identical database queries or API lookups triggered multiple times within a single user request lifecycle are cached or memoized (e.g., using React `cache()` or global request contexts) to prevent redundant inner-network traffic.
- **Cache-Busting & Invalidation Strategy:** Ensure that when mutated data is written to the persistence layer, the application triggers explicit, targeted cache invalidation paths rather than relying on arbitrary, long TTL timers or dropping the entire cache registry wholesale.
- **Framework Caching Architecture:** Identify opportunities where dynamic Server-Side Rendering (SSR) could be converted into Incremental Static Regeneration (ISR) or Static Site Generation (SSG). Ensure caching rules are applied to mostly static marketing or informational assets.
- **Volatile Store Overheads:** Trace connection pools to key-value or caching microservices. Check if multiple sequential cache commands are being awaited line-by-line rather than using batched pipelines, multi-gets, or concurrent execution arrays.

### 4. API Performance Requirements & SLA Hardening
- **Time to First Byte (TTFB) & Latency Budgets:** Audit route handlers to ensure P95 latency targets are met. Core read APIs must return within <100ms; write operations must return within <250ms. Any endpoint exceeding these limits must be flagged for background worker offloading or aggressive caching.
- **Over-Fetching & Payload Budgeting:** Restrict maximum raw JSON or data payloads to <50KB per request. Ensure API contracts omit unnecessary object graphs, metadata fields, or deeply nested relational data arrays that the client-side consumer does not immediately render.
- **Network Chattiness Constraints:** Flag client-side interaction loops that trigger repetitive, sequential API requests where a single consolidated or batched query payload would cut down on network round-trip overhead.
- **Compression and Serialization:** Ensure text responses exceeding 1KB enforce server-side compression (`gzip`/`brotli`). Identify loops blocking the main thread with massive data serialization operations that could be offloaded.
- **Idempotency & Concurrent Safety:** Verify that high-concurrency API paths utilize proper conditional requests (`If-Match`, `ETag`) or idempotency keys to prevent race conditions from triggering redundant, expensive server re-calculations.

### 5. Cross-Service Network & Host I/O Efficiency
- **Connection Reuse for Internal & Third-Party Calls:** Verify HTTP clients calling internal microservices or external APIs reuse agents/keep-alive connections. Per-request TCP+TLS handshakes add 50–300ms of avoidable latency per call and exhaust ephemeral ports under sustained load.
- **Synchronous Filesystem & Blocking I/O:** Flag `readFileSync`/`writeFileSync` or equivalent blocking file, DNS, or socket operations inside request handlers; these freeze the event loop for every concurrent request sharing the process.
- **Logging & Serialization Overhead:** Identify hot paths performing synchronous structured logging, deep object cloning, or full JSON serialization/parsing of large object graphs per request; quantify per-request CPU cost at realistic traffic volumes.
- **Downstream Circuit Breaking & Fail-Fast:** Verify calls to slow or unreliable dependencies enforce request timeouts and fail-fast behavior (circuit breakers, bulkheads) so one degraded dependency cannot queue inbound requests indefinitely and exhaust server memory and sockets.

### 6. Compute Architecture & Full-Stack Rendering
- **Execution Thread Starvation:** Scan request handlers for synchronous, blocking algorithms (e.g., heavy crypto, massive file system reads, deep array mutations) that freeze the main application runtime thread.
- **Streaming & Deferred Hydration:** Audit server-side route components. Ensure data-heavy or slower third-party APIs utilize asynchronous streaming, loading states, or deferred rendering hooks to prevent blocking the initial TTFB page paint.
- **Algorithmic Complexity Escalation:** Isolate nested loops, deep lookups, or matrix operations. Ensure data processing paths scale linearly ($O(N)$) or logarithmically, completely blocking superlinear configurations ($O(N^2)$) on high-growth data objects.
- **Unbounded Concurrency Pools:** Audit concurrent arrays (`Promise.all`). Ensure calls traversing an unknown data scale throttle their execution through active batching or queue wrappers to prevent hitting external service connection ceilings.

### 7. Memory Allocation & Retention Hardening (Scale Safety)
- **Unevicted Global Collections:** Scan the global application scope for long-lived caches, maps, arrays, or object registries. Every manual cache container **MUST** enforce an aggressive Least Recently Used (LRU) eviction strategy or Max-Age policy to prevent memory exhaustion over time.
- **Buffered Storage Exhaustion:** Audit binary data, file-upload handlers, and data export endpoints. Large files or collections must be processed via streaming chunks (`stream`) rather than loading and buffering whole assets natively into server RAM.
- **Event-Listener Lifecycle Leaks:** Identify any web sockets, long-lived server event hooks, or background cron-job routines. Ensure every process implements clean cleanup hooks (`removeListener`, connection closers) to stop abandoned requests from holding onto active memory contexts.

### 8. Frontend Bundling, Hydration, & Core Web Vitals
- **Hydration Blocking & Dynamic Imports:** Scan the initial page load bundle for non-critical visual components (e.g., heavy modal windows, dark-mode switches, chart engines, or third-party feedback widgets). Force these elements into asynchronous dynamic chunks that lazy-load only after the page hits interactivity to secure a fast Largest Contentful Paint (LCP) score.
- **CSS & Style Delivery Bloat:** Identify runtime CSS-in-JS solutions or unpurged utility styles that block the main parsing engine. Ensure styling is delivered via atomic, pre-compiled static stylesheets to minimize initial styling blocks.
- **Polyfill & Legacy Payload Tax:** Ensure your build compiler splits code using modern browser targets (`esnext`). Flag legacy scripts or polyfills being served to modern browsers that artificially inflate your JavaScript payload sizes.
- **Third-Party Script Sandboxing:** Verify that tracking pixels, analytical tag managers, and customer support scripts are deferred, loaded lazily, or offloaded onto separate worker threads so they do not hijack the main thread and tank your Interaction to Next Paint (INP) score.
- **Visual Asset Optimization:** Audit frontend markup image tags. Images must enforce modern web standards (compressed formats, dynamic source sizing layouts, structural dimension attributes) to prevent Cumulative Layout Shift (CLS).

## Output Formatting

**No Conversational Fluff.** Omit greetings, post-audit summaries, or introductory commentary. Move directly to the ranked performance matrix, ordered from highest severity (P0) to lowest (P3). If no bottlenecks are verified, output: `[PERF OK] Systems running at optimal efficiency.`

For each finding, you must output exactly this structural layout:

*   **Finding [ID]: [Short, Quantitative Performance Bug Name]**
    *   **Severity:** [P0 / P1 / P2 / P3]
    *   **Performance Metrics Impacted:** [e.g., API SLA, TTFB, LCP, INP, Payload Size, DB CPU, DB Connections, RAM Memory Leak, Network I/O]
    *   **Location:** `[File path]:[Line number]`
    *   **Defect Statement:** One sentence isolating the exact algorithmic or structural architectural failure.
    *   **Concrete Scalability Scenario:** A specific, technical description of how a realistic metric (e.g., 50 concurrent users or 10,000 DB records) turns this structural line of code into a major latency block or infrastructure collapse.