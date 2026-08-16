import { defineConfig } from 'vitest/config';

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
          exclude: ['packages/*/src/**/*.integration.test.ts'],
          environment: 'node',
          passWithNoTests: false,
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
