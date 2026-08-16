/**
 * Enforces STACKSPEC §3.2's layer rules.
 *
 * §3.2 requires these be enforced by "a lint rule or dependency-graph check
 * that fails the build, not by review", because "a documented convention
 * without enforcement decays". dependency-cruiser rather than an ESLint rule:
 * two of the six rules are about the *workspace graph* (circular dependencies,
 * client apps reaching server packages transitively), which an import-scoped
 * lint rule cannot see.
 *
 * Every rule below cites the clause it enforces. If you relax one, §20 wants
 * the deviation recorded in docs/specs/stack-profile.md with a named approver —
 * an unrecorded divergence is a violation, a recorded one is not.
 *
 * Run: pnpm depcruise --config .dependency-cruiser.cjs apps packages
 */
module.exports = {
  forbidden: [
    {
      name: 'core-is-pure',
      severity: 'error',
      comment:
        '§3.2: core MUST NOT import any framework, any I/O, any environment ' +
        'variable, any clock, or any package outside core. It is pure ' +
        'functions and types — that is what makes it testable, reusable by ' +
        'the worker and seeds, and safe to reason about.',
      from: { path: '^packages/core' },
      to: {
        pathNot: '^packages/core',
        // node: builtins are I/O and clocks; anything outside core is by
        // definition outside core.
        dependencyTypesNot: ['type-only'],
      },
    },
    {
      name: 'only-db-touches-the-driver',
      severity: 'error',
      comment:
        '§3.2: db MUST be the only package that imports the database driver ' + 'or ORM.',
      from: { pathNot: '^packages/db' },
      to: { path: 'node_modules/(drizzle-orm|pg|postgres|@neondatabase)' },
    },
    {
      name: 'no-next-outside-apps',
      severity: 'error',
      comment:
        '§3.2: no package below apps/ may import next/*. A next/headers ' +
        'import inside a shared package is the first step of the erosion this ' +
        'rule exists to prevent.',
      from: { path: '^packages/' },
      to: { path: 'node_modules/next' },
    },
    {
      name: 'clients-use-the-generated-api-client-only',
      severity: 'error',
      comment:
        '§3.2: client apps MUST NOT import db, auth, core, or any service ' +
        'package. They reach the system exclusively through the generated API ' +
        'client. (core is tempting and forbidden — see §1.)',
      from: { path: '^apps/(web|admin|ios|android)' },
      to: { path: '^packages/(db|auth|core|jobs)' },
    },
    {
      name: 'platform-sdks-stay-in-adapters',
      severity: 'error',
      comment:
        '§3.2: platform SDKs (@vercel/blob, mail provider SDK, push SDKs) ' +
        'MUST be imported only inside their adapter package.',
      from: { pathNot: '^packages/(storage|mail|notify|observability)' },
      to: { path: 'node_modules/(@vercel/blob|resend|@sendgrid|expo-server-sdk)' },
    },
    {
      name: 'no-unresolvable',
      severity: 'error',
      comment:
        'An import dependency-cruiser cannot resolve is reported with ' +
        'valid: true, so every rule below silently skips it and the run ends ' +
        '"no dependency violations found". A resolution problem therefore ' +
        'empties this entire gate instead of failing it — which is exactly ' +
        'what happened with workspace packages using an "exports" field ' +
        'before enhancedResolveOptions was set below. This rule is the ' +
        'backstop: an unresolvable import fails rather than disappearing.',
      from: {},
      to: { couldNotResolve: true },
    },
    {
      name: 'no-circular-workspace-deps',
      severity: 'error',
      comment: '§3.2: circular workspace dependencies MUST NOT exist.',
      from: {},
      to: { circular: true },
    },
  ],
  options: {
    doNotFollow: { path: 'node_modules' },
    tsConfig: { fileName: 'tsconfig.json' },
    tsPreCompilationDeps: true,
    // Workspace packages are pnpm symlinks under node_modules and are
    // published with either "main" or "exports". Without these, an "exports"
    // package does not resolve, every cross-package edge is dropped, and the
    // layer rules above match nothing while still reporting success.
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'types'],
      mainFields: ['module', 'main', 'types'],
      extensions: ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'],
    },
    exclude: { path: '(\\.test\\.|\\.spec\\.|__tests__|__fixtures__)' },
    reporterOptions: {
      text: { highlightFocused: true },
    },
  },
};
