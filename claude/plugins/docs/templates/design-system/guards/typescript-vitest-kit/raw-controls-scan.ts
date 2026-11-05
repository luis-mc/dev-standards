import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * The scanner behind `raw-controls.test.ts` (design system, Enforcement kit): no raw `<button>`, `<input>`,
 * `<select>` or `<textarea>` in app code. Apps use the shared UI components. Copy of the luismc-docs template;
 * adjust CONFIG to the project.
 */
export const CONFIG = {
  /** App folders, repo-relative. Everything inside is scanned. */
  appPaths: ['apps/'],
  /** Shared UI folders, repo-relative. Never judged: this is where the raw controls belong. */
  sharedPaths: ['packages/ui/'],
  /** File names that are scanned. */
  fileGlobs: ['*.tsx', '*.jsx', '*.vue', '*.svelte', '*.html'],
};

export const TAGS = ['button', 'input', 'select', 'textarea'] as const;
export type Tag = (typeof TAGS)[number];
export interface Breach {
  readonly file: string;
  readonly tag: Tag;
}

const SKIP_DIRS = new Set(['node_modules', 'dist', '.turbo', 'coverage', '__tests__', 'tests']);
const TEST_FILE = /\.(test|spec)\./;

function globToRegExp(glob: string): RegExp {
  return new RegExp('^' + glob.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$');
}

/** True when a repo-relative path is a test file or sits in a test folder. */
export function isTestPath(file: string): boolean {
  const parts = file.split('/');
  return TEST_FILE.test(parts[parts.length - 1] as string) || parts.slice(0, -1).some((p) => p === '__tests__' || p === 'tests');
}

/** True when a repo-relative path is inside one of the folders. */
export function isUnder(file: string, folders: readonly string[]): boolean {
  return folders.some((f) => file.startsWith(f.endsWith('/') ? f : f + '/'));
}

/** The raw controls in one source file. Lower-case tags only: `<Button>` is a component. */
export function scanText(file: string, text: string, config = CONFIG): Breach[] {
  if (isTestPath(file) || isUnder(file, config.sharedPaths)) return [];
  if (!config.fileGlobs.some((g) => globToRegExp(g).test(file.split('/').pop() as string))) return [];
  const found: Breach[] = [];
  for (const m of text.matchAll(/<(button|input|select|textarea)(?=[\s/>])/g)) found.push({ file, tag: m[1] as Tag });
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

/** Every raw control in the app folders, in file order. */
export function scanApps(root: string, config = CONFIG): Breach[] {
  const found: Breach[] = [];
  for (const app of config.appPaths) {
    const files: string[] = [];
    walk(join(root, app), files);
    for (const file of files.sort()) {
      const rel = relative(root, file).split('\\').join('/');
      found.push(...scanText(rel, readFileSync(file, 'utf8'), config));
    }
  }
  return found;
}

/** Breaches grouped to "file|tag" -> count. */
export function countBreaches(found: readonly Breach[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const b of found) counts.set(`${b.file}|${b.tag}`, (counts.get(`${b.file}|${b.tag}`) ?? 0) + 1);
  return counts;
}

export interface KnownEntry {
  file: string;
  tag: string;
  count: number;
}

/** The ratchet: a count above its listed one is new; a listed count above the real one is stale. */
export function judgeBreaches(
  actual: ReadonlyMap<string, number>,
  known: readonly KnownEntry[],
): { added: string[]; stale: string[] } {
  const listed = new Map(known.map((e) => [`${e.file}|${e.tag}`, e.count]));
  const added: string[] = [];
  const stale: string[] = [];
  for (const [key, n] of actual) {
    const [file, tag] = key.split('|');
    const was = listed.get(key) ?? 0;
    if (n > was) added.push(`${file}: ${n - was} new raw <${tag}>${was ? ` (${was} known)` : ''}`);
  }
  for (const [key, was] of listed) {
    const n = actual.get(key) ?? 0;
    const [file, tag] = key.split('|');
    if (n < was) stale.push(`${file}: <${tag}> known ${was}, now ${n}: lower or remove the entry in raw-controls.known.json`);
  }
  return { added, stale };
}
