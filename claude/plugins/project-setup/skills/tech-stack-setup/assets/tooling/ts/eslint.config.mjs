// @ts-check
import js from '@eslint/js';
import ts from 'typescript-eslint';

/**
 * STACKSPEC does not name a linter — §13.1 requires that `lint` run and fail
 * the build, not which tool does it. ESLint is this generator's choice, and the
 * choice belongs in docs/specs/stack-profile.md, not in the spec: treating it
 * as a spec requirement would be a new MUST, which §20 makes a major version.
 *
 * §3.2's layer rules are NOT enforced here. They are graph properties —
 * circular workspace dependencies, client apps reaching server packages — and
 * live in .dependency-cruiser.cjs, which CI runs as its own gate.
 */
export default ts.config(
  js.configs.recommended,
  ...ts.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: { projectService: true },
    },
    rules: {
      // §5.6 forbids sequential awaits on independent queries and N+1 access.
      // Neither is decidable by a linter, but an un-awaited promise is the
      // adjacent bug that is, and it silently drops errors.
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/no-misused-promises': 'error',

      // §2.2 pins exact versions and forbids degrading to a generic type when a
      // precise one exists. `any` is how that erodes in practice.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unsafe-assignment': 'error',
      '@typescript-eslint/no-unsafe-return': 'error',

      // An unused variable after a refactor is usually the tail of a change
      // that was half-applied.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  {
    // Config and script files are not part of the typed program.
    files: ['**/*.config.{js,ts,cjs,mjs}', 'scripts/**'],
    ...ts.configs.disableTypeChecked,
  },
  {
    ignores: [
      '**/dist/**',
      '**/build/**',
      '**/.next/**',
      '**/node_modules/**',
      // Generated clients are regenerated and diff-checked by CI (§4.1);
      // linting them would fail on style the generator owns.
      '**/generated/**',
    ],
  },
);
