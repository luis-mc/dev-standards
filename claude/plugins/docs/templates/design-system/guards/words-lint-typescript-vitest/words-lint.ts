/**
 * Words lint (DS235a, LC-2 and LC-31). Copy to scripts/design/ with words-lint.test.ts. Edit CONFIG.
 * LC-2: every lifecycle UI string is a value of the words table in docs/design-system/vN/lifecycle.json, and no
 * banned word is in it. LC-31: notices are plain: no error code, no HTTP status, no doubled punctuation.
 */
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

export const CONFIG = {
  /** Files that hold lifecycle UI strings (relative to the repo root, folders are walked). */
  lifecycleFiles: ['src/lifecycle'],
  extensions: ['.ts', '.tsx'],
};

export const DEFAULT_BANNED = ['OK', 'Yes', 'No', 'Install now', 'Later', 'daemon', 'binary', 'payload'];
const CASE_SENSITIVE = new Set(['OK', 'Yes', 'No', 'Later']);

export type Finding = { rule: 'LC-2' | 'LC-31'; text: string; why: string };
export type Words = { banned?: string[]; states?: Record<string, Record<string, string>> };

const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export function bannedHits(text: string, banned: string[] = DEFAULT_BANNED): string[] {
  return banned.filter((w) =>
    new RegExp(`(?<![A-Za-z0-9])${esc(w)}(?![A-Za-z0-9])`, CASE_SENSITIVE.has(w) ? '' : 'i').test(text));
}

const PLAIN: [string, RegExp][] = [
  ['error code', /0x[0-9a-fA-F]|(?<![A-Za-z0-9])[A-Z]{1,5}[-_]?[0-9]{3,}(?![A-Za-z0-9])|\b(?:[Ee]rror|[Cc]ode)\s+[0-9]/],
  ['HTTP status', /HTTP\s*[1-5][0-9]{2}\b|\bstatus(?:\s+code)?\s+[1-5][0-9]{2}\b/i],
  ['doubled punctuation', /([.,;:!?])\1/],
];

export function plainHits(text: string): string[] {
  return PLAIN.filter(([, rx]) => rx.test(text)).map(([name]) => name);
}

export function tableValues(words: Words): Set<string> {
  const out = new Set<string>();
  for (const state of Object.values(words.states ?? {})) for (const v of Object.values(state)) out.add(v);
  return out;
}

/** The string literals of TypeScript source: '...', "..." and `...` without `${`. */
export function literals(source: string): string[] {
  const out: string[] = [];
  const rx = /'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\$]|\\.)*)`/g;
  for (const m of source.matchAll(rx)) out.push((m[1] ?? m[2] ?? m[3] ?? '').replace(/\\(.)/g, '$1'));
  return out;
}

export function checkStrings(strings: string[], words: Words): Finding[] {
  const allowed = tableValues(words);
  const banned = [...new Set([...DEFAULT_BANNED, ...(words.banned ?? [])])];
  const found: Finding[] = [];
  for (const text of strings) {
    if (!/[A-Za-z]/.test(text)) continue;
    for (const w of bannedHits(text, banned)) found.push({ rule: 'LC-2', text, why: `banned word '${w}'` });
    if (!allowed.has(text)) found.push({ rule: 'LC-2', text, why: 'not in the words table' });
    for (const why of plainHits(text)) found.push({ rule: 'LC-31', text, why });
  }
  return found;
}

export function findLifecycle(root: string): string | null {
  const dir = join(root, 'docs', 'design-system');
  if (!existsSync(dir)) return null;
  const nums = readdirSync(dir).filter((n) => /^v[1-9]\d*$/.test(n)).map((n) => Number(n.slice(1))).sort((a, b) => b - a);
  for (const name of [...nums.map((n) => `v${n}`), 'next-version']) {
    const f = join(dir, name, 'lifecycle.json');
    if (existsSync(f)) return f;
  }
  return null;
}

function walk(path: string): string[] {
  if (!existsSync(path)) return [];
  const out: string[] = [];
  for (const e of readdirSync(path, { withFileTypes: true })) {
    const p = join(path, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (CONFIG.extensions.some((x) => p.endsWith(x)) && !/\.(test|spec)\./.test(p)) out.push(p);
  }
  return out;
}

export function scanRoot(root: string): Finding[] {
  const lc = findLifecycle(root);
  if (!lc) throw new Error('no lifecycle.json under docs/design-system');
  const words = (JSON.parse(readFileSync(lc, 'utf8')) as { words: Words }).words;
  return CONFIG.lifecycleFiles.flatMap((f) => walk(join(root, f))).flatMap((p) => checkStrings(literals(readFileSync(p, 'utf8')), words));
}
