import { configDefaults, defineConfig } from 'vitest/config';

/**
 * STACKSPEC §11.1 makes four test kinds mandatory, and CI runs them in two
 * different jobs — the ones needing no I/O in the static job, the ones needing
 * an ephemeral Postgres in its own. Projects are what let `ci.yml` select them
 * individually (`vitest run --project unit`) instead of relying on file-name
 * conventions that silently stop matching.
 *
 * A project whose glob matches nothing passes. That makes an empty or
 * mis-globbed suite indistinguishable from a passing one, so `passWithNoTests`
 * is false everywhere below: an absent suite fails loudly.
 */

/**
 * Other checkouts nested under this one (agent worktrees under
 * `.claude/worktrees`, a second clone in `.worktrees`) hold their own copy of
 * every test file. A `**` glob from the root would run all of them, once per
 * checkout, against whatever state those checkouts are in at that moment. A
 * project whose include starts with `**` excludes them; `exclude` replaces
 * Vitest's defaults, so those are spread in.
 */
const nestedCheckouts = ['**/.claude/worktrees/**', '**/.worktrees/**'];

export default defineConfig({
  test: {
    passWithNoTests: false,
    projects: [
      {
        // §11.1 server unit tests: all of core, plus service-package logic.
        // Pure, fast, no I/O.
        test: {
          name: 'unit',
          include: ['packages/*/src/**/*.test.ts'],
          exclude: [
            'packages/*/src/**/*.integration.test.ts',
            // Guard tests belong to the `guard` project below, never to a
            // package-scoped run.
            'packages/*/src/**/*.guard.test.ts',
          ],
          environment: 'node',
          passWithNoTests: false,
        },
      },
      {
        // §13.5 guard tests: each scans the source or the specs as a whole
        // (conflict markers, retired vocabulary, design rules, duplication
        // ratchets). The branch gate and the pre-push hook run this project
        // whatever changed, because scoping a guard by package lets a change
        // elsewhere break it unseen. Add a guard by adding a `*.guard.test.ts`
        // file anywhere; `guards/no-conflict-markers.guard.test.ts` is the
        // starter, and keeps this project from ever finding zero tests.
        test: {
          name: 'guard',
          include: ['**/*.guard.test.ts'],
          exclude: [...configDefaults.exclude, ...nestedCheckouts],
          environment: 'node',
          passWithNoTests: false,
          // A guard reads the whole repository. Vitest's 5 s default test
          // timeout is a race on a big tree or a busy machine (parallel agents,
          // a cold file cache); a guard that is really stuck is caught by the
          // gate's own limit on the step, not by this.
          testTimeout: 60_000,
          hookTimeout: 60_000,
        },
      },
      {
        // §11.1 contract tests: every client and the server verified against
        // the same fixtures derived from the OpenAPI document. Required
        // coverage is every endpoint's success shape, every documented error
        // code, pagination envelopes, unknown-field tolerance, unknown-enum
        // tolerance, and the "upgrade required" response.
        test: {
          name: 'contract',
          include: ['packages/contract/test/**/*.test.ts'],
          environment: 'node',
          passWithNoTests: false,
        },
      },
      {
        // §11.1 + §5.5 integration tests: API routes end to end against an
        // ephemeral real Postgres seeded through the migration chain. Not mocks.
        test: {
          name: 'integration',
          include: ['**/*.integration.test.ts'],
          exclude: [...configDefaults.exclude, ...nestedCheckouts],
          environment: 'node',
          passWithNoTests: false,
          // Migrations and fixtures share one database per run; parallel files
          // would race on the schema.
          fileParallelism: false,
          hookTimeout: 60_000,
        },
      },
      {
        // §11.1 security tests: MUST fail the build when any route ships
        // without an explicit authorization declaration. Kept separate so the
        // failure names the control rather than appearing as one red test in a
        // large integration run.
        test: {
          name: 'authz',
          include: ['apps/api/test/authorization/**/*.test.ts'],
          environment: 'node',
          passWithNoTests: false,
        },
      },
    ],
  },
});
