import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * The scanner behind `raw-inputs.test.ts` (design system UX-56, Enforcement kit): no native date, time or
 * number input. Dates use the date picker, times use the time picker, and the number keypad is only for
 * counts, measures and codes. Copy of the luismc-docs template; adjust CONFIG to the project.
 */
export const CONFIG = {
  /** Folders that are scanned, repo-relative. A native date, time or number input is banned in both the apps and the shared UI. */
  paths: ['apps/', 'packages/ui/'],
  /** File names that are scanned. */
  fileGlobs: ['*.tsx', '*.jsx', '*.vue', '*.svelte', '*.html'],
};

export const TYPES = ['date', 'time', 'datetime-local', 'number'] as const;
export type InputType = (typeof TYPES)[number];
export interface Breach {
  readonly file: string;
  readonly type: InputType;
}

const SKIP_DIRS = new Set(['node_modules', 'dist', '.turbo', 'coverage', '__tests__', 'tests']);
const TEST_FILE = /\.(test|spec)\./;
// type="date", type='time', type={"number"}, type={'datetime-local'}, :type="'date'" (Vue binding of a literal).
const TYPE_ATTR = /\btype\s*=\s*\{?\s*["'`]\s*'?(date|time|datetime-local|number)'?\s*["'`]/g;

function globToRegExp(glob: string): RegExp {
  return new RegExp('^' + glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$');
}

/** True when a repo-relative path is a test file or sits in a test folder. */
export function isTestPath(file: string): boolean {
  const parts = file.split('/');
  return TEST_FILE.test(parts[parts.length - 1] as string) || parts.slice(0, -1).some((p) => p === '__tests__' || p === 'tests');
}

/** The native date, time and number inputs in one source file. */
export function scanText(file: string, text: string, config = CONFIG): Breach[] {
  if (isTestPath(file)) return [];
  if (!config.fileGlobs.some((g) => globToRegExp(g).test(file.split('/').pop() as string))) return [];
  const found: Breach[] = [];
  for (const m of text.matchAll(TYPE_ATTR)) found.push({ file, type: m[1] as InputType });
  return found;
}

function walk(dir: string, out: string[]): void {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (!SKIP_DIRS.has(name)) walk(path, out);
    } else {
      out.push(path);
    }
  }
}

/** Every native date, time or number input in the scanned folders, in file order. */
export function scanTree(root: string, config = CONFIG): Breach[] {
  const found: Breach[] = [];
  for (const base of config.paths) {
    const files: string[] = [];
    walk(join(root, base), files);
    for (const file of files.sort()) {
      const rel = relative(root, file).split('\\').join('/');
      found.push(...scanText(rel, readFileSync(file, 'utf8'), config));
    }
  }
  return found;
}

/** Breaches grouped to "file|type" -> count. */
export function countBreaches(found: readonly Breach[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const b of found) counts.set(`${b.file}|${b.type}`, (counts.get(`${b.file}|${b.type}`) ?? 0) + 1);
  return counts;
}

export interface KnownEntry {
  file: string;
  type: string;
  count: number;
}

const USE: Record<string, string> = {
  date: 'the date picker',
  'datetime-local': 'the date picker and the time picker',
  time: 'the time picker',
  number: 'the number keypad (counts, measures and codes only)',
};

/** The ratchet: a count above its listed one is new; a listed count above the real one is stale. */
export function judgeBreaches(
  actual: ReadonlyMap<string, number>,
  known: readonly KnownEntry[],
): { added: string[]; stale: string[] } {
  const listed = new Map(known.map((e) => [`${e.file}|${e.type}`, e.count]));
  const added: string[] = [];
  const stale: string[] = [];
  for (const [key, n] of actual) {
    const [file, type] = key.split('|') as [string, string];
    const was = listed.get(key) ?? 0;
    if (n > was) added.push(`${file}: ${n - was} new type="${type}" input${was ? ` (${was} known)` : ''}: use ${USE[type]}`);
  }
  for (const [key, was] of listed) {
    const n = actual.get(key) ?? 0;
    const [file, type] = key.split('|');
    if (n < was) stale.push(`${file}: type="${type}" known ${was}, now ${n}: lower or remove the entry in raw-inputs.known.json`);
  }
  return { added, stale };
}
