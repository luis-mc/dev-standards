// Shared helpers for the design-system guards (DS234) and the lifecycle guards (LC-22 to LC-30). Node only, no dependencies
// except Playwright for the rendered checks. A guard prints one line per problem and exits 1 when there is any.
import { createRequire } from 'node:module';
import { readFileSync, readdirSync, statSync, existsSync } from 'node:fs';
import { join, relative } from 'node:path';
import { pathToFileURL } from 'node:url';

export function args(argv = process.argv.slice(2)) {
  const flags = {}; const rest = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) { const k = argv[i].slice(2); flags[k] = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true; }
    else rest.push(argv[i]);
  }
  return { flags, rest };
}

/** All files under `dir` whose name matches `re`, skipping node_modules and dot folders. */
export function walk(dir, re) {
  const out = [];
  const go = (d) => {
    for (const n of readdirSync(d)) {
      if (n === 'node_modules' || n.startsWith('.')) continue;
      const p = join(d, n); const s = statSync(p);
      if (s.isDirectory()) go(p); else if (re.test(n)) out.push(p);
    }
  };
  if (existsSync(dir)) go(dir);
  return out.sort();
}

export const read = (p) => readFileSync(p, 'utf8');
export const rel = (root, p) => relative(root, p).split('\\').join('/');

export function finish(name, problems) {
  if (problems.length) { for (const p of problems) console.log(`${name}: ${p}`); console.log(`${name}: FAIL (${problems.length})`); process.exit(1); }
  console.log(`${name}: ok`);
}

/** Today as YYYY-MM-DD; DS_TODAY overrides (tests). */
export const today = () => process.env.DS_TODAY || new Date().toISOString().slice(0, 10);
export const daysBetween = (a, b) => Math.round((Date.parse(b) - Date.parse(a)) / 86400000);

export function loadPlaywright() {
  const nm = process.env.DS_NODE_MODULES;
  const req = createRequire(nm ? join(nm, 'x.js') : import.meta.url);
  return req('playwright');
}

export const fileUrl = (p) => pathToFileURL(p).href;
