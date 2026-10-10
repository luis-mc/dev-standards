import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { defineConfig } from '@playwright/test';

// STACKSPEC §11.2: a spec that fails intermittently is moved to a committed
// quarantine list with an owner, a date and a reason, and is fixed. A
// quarantined spec still runs and reports but cannot fail the build.
//
// e2e/quarantine.json is that list:
//   [{ "spec": "tests/checkout.spec.ts", "owner": "name",
//      "since": "YYYY-MM-DD", "reason": "why it is flaky" }]
// `spec` is a path from the repository root. Run Playwright from the root
// (`pnpm exec playwright test`), which is how CI and `pnpm e2e` run it.
//
//   default                 every spec EXCEPT the quarantined ones (the gate)
//   E2E_QUARANTINE=only     ONLY the quarantined ones (CI's non-blocking step)

interface Quarantined {
  spec: string;
  owner: string;
  since: string;
  reason: string;
}

function loadQuarantine(): Quarantined[] {
  const file = resolve('e2e/quarantine.json');
  if (!existsSync(file)) return [];
  const list: unknown = JSON.parse(readFileSync(file, 'utf8'));
  if (!Array.isArray(list)) throw new Error(`${file} must be a JSON list`);
  for (const entry of list as Partial<Quarantined>[]) {
    // An entry with no owner, date or reason is a spec hidden from the gate.
    if (!entry.spec || !entry.owner || !entry.since || !entry.reason) {
      throw new Error(
        `${file}: every entry needs spec, owner, since and reason (§11.2): ${JSON.stringify(entry)}`,
      );
    }
  }
  return list as Quarantined[];
}

// Absolute, forward-slashed: Playwright globs match on absolute file paths.
const quarantined = loadQuarantine().map((q) => resolve(q.spec).split('\\').join('/'));
const only = process.env.E2E_QUARANTINE === 'only';

export default defineConfig({
  testDir: './tests',
  reporter: 'line',
  // §11.3: a flaky spec is quarantined and fixed, never retried until green.
  // Retries stay 0 for the gating specs; do not raise this to make CI pass.
  retries: 0,
  forbidOnly: !!process.env.CI,
  ...(only
    ? // Nothing quarantined means nothing to run, not "run everything".
      { testMatch: quarantined.length > 0 ? quarantined : ['**/__no-quarantined-spec__'] }
    : { testIgnore: quarantined }),
});
