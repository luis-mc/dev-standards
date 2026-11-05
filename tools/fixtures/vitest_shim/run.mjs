// Usage: node tools/fixtures/vitest_shim/run.mjs <test file> [<test file> ...]
// Runs vitest-style test files (TypeScript with erasable types) with the shim in vitest.mjs.
import { register } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

register('./hooks.mjs', import.meta.url);
for (const file of process.argv.slice(2)) await import(pathToFileURL(resolve(file)).href);
const { runAll } = await import('./vitest.mjs');
process.exit((await runAll()) ? 0 : 1);
