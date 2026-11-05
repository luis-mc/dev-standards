import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

/**
 * The scanner behind `no-app-css.test.ts` (design system, Enforcement kit): what an app folder may not carry,
 * found by reading its sources. Copy of the luismc-docs template; adjust CONFIG to the project.
 *
 * Four kinds of breach, counted per file:
 *  - `stylesheet`: a `.css` / `.scss` file inside an app folder;
 *  - `css-in-js`: a style block written in code (`<style`, `createElement('style')`, `styled.x`, a `css` tagged
 *    template, `insertRule`, `adoptedStyleSheets`, `style.cssText`);
 *  - `style-attr`: a `style=` prop or attribute that sets anything but a CSS custom property (layout and colour
 *    belong to the shared UI package);
 *  - `class-name`: a `className` (or `class=`) with a class the shared UI package does not define.
 */
export const CONFIG = {
  /** App folders, repo-relative. Everything inside is scanned. */
  appRoots: ['apps/web', 'apps/admin'],
  /** The shared UI package, repo-relative. Its stylesheets and class maps define the classes apps may use. */
  uiRoot: 'packages/ui/src',
  /** File names of class maps inside the shared UI package; their string values count as shared classes. */
  classMapFile: /classes?\.ts$|class-?names?\.ts$|css\.ts$/,
};

export type Kind = 'stylesheet' | 'css-in-js' | 'style-attr' | 'class-name';
export const KINDS: readonly Kind[] = ['stylesheet', 'css-in-js', 'style-attr', 'class-name'];
export interface Breach {
  readonly file: string;
  readonly kind: Kind;
}

const SKIP_DIRS = new Set(['node_modules', 'dist', '.turbo', 'coverage', 'e2e', 'test', 'testing', 'fixtures']);
const TEST_FILE = /\.(test|spec|integration\.test)\.[cm]?[jt]sx?$/;

function walk(dir: string, out: string[]): void {
  if (!existsSync(dir)) return;
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (!SKIP_DIRS.has(name)) walk(path, out);
    } else if (!TEST_FILE.test(name)) {
      out.push(path);
    }
  }
}

/** Every class the shared UI package defines: its sheets, and the string values of its class maps. */
export function kitClasses(root: string, config = CONFIG): Set<string> {
  const set = new Set<string>();
  const files: string[] = [];
  walk(join(root, config.uiRoot), files);
  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    if (file.endsWith('.css')) {
      for (const m of text.matchAll(/\.(-?[_a-zA-Z][\w-]*)/g)) set.add(m[1] as string);
    } else if (config.classMapFile.test(file)) {
      for (const m of text.matchAll(/['"`]([_a-zA-Z][\w -]*)['"`]/g))
        for (const token of (m[1] as string).split(/\s+/)) set.add(token);
    }
  }
  return set;
}

/** The text of the braces or quotes that start at `from` (an attribute value), or '' when it is neither. */
function attributeValue(text: string, from: number): string {
  const open = text[from];
  if (open === '"' || open === "'") {
    const end = text.indexOf(open, from + 1);
    return end < 0 ? '' : text.slice(from + 1, end);
  }
  if (open !== '{') return '';
  let depth = 0;
  for (let i = from; i < text.length; i++) {
    if (text[i] === '{') depth++;
    else if (text[i] === '}' && --depth === 0) return text.slice(from + 1, i);
  }
  return '';
}

/** The breaches of one source file. */
export function scanText(file: string, text: string, kit: ReadonlySet<string>): Breach[] {
  const found: Breach[] = [];
  const add = (kind: Kind, n = 1): void => {
    for (let i = 0; i < n; i++) found.push({ file, kind });
  };
  if (/\.s?css$/.test(file)) {
    add('stylesheet');
    return found;
  }
  if (!/\.(tsx?|jsx?|html|mjs|cjs)$/.test(file)) return found;
  add(
    'css-in-js',
    (
      text.match(
        /<style[\s>]|createElement\(\s*['"]style['"]|\bstyled\s*[.(]|\bcss\s*`|\.insertRule\(|adoptedStyleSheets|\.style\.cssText/g,
      ) ?? []
    ).length,
  );
  for (const m of text.matchAll(/\bstyle=/g)) {
    const value = attributeValue(text, (m.index ?? 0) + m[0].length);
    const keys = [...value.matchAll(/(?:^|[{,;\s])['"]?([a-zA-Z-][\w-]*)['"]?\s*:/g)].map((k) => k[1] as string);
    if (keys.some((k) => !k.startsWith('--'))) add('style-attr');
  }
  for (const m of text.matchAll(/\b(?:className|class)=/g)) {
    const value = attributeValue(text, (m.index ?? 0) + m[0].length);
    if (value === '') continue;
    const tokens: string[] = [];
    if (text[(m.index ?? 0) + m[0].length] === '{') {
      // An expression: only its literal class words can be judged; names the code passes in are the caller's.
      for (const lit of value.replace(/\$\{[^}]*\}/g, ' ').matchAll(/(['"`])((?:(?!\1)[^\\]|\\.)*?)\1/g))
        tokens.push(...(lit[2] as string).split(/\s+/));
    } else {
      tokens.push(...value.split(/\s+/));
    }
    if (tokens.some((t) => /^[_a-zA-Z][\w-]*$/.test(t) && !kit.has(t))) add('class-name');
  }
  return found;
}

/** Every breach in the app folders, in file order. */
export function scanApps(root: string, config = CONFIG): Breach[] {
  const kit = kitClasses(root, config);
  const found: Breach[] = [];
  for (const app of config.appRoots) {
    const files: string[] = [];
    walk(join(root, app), files);
    for (const file of files.sort()) {
      const rel = relative(root, file).split('\\').join('/');
      found.push(...scanText(rel, readFileSync(file, 'utf8'), kit));
    }
  }
  return found;
}

/** Breaches grouped to "file|kind" -> count. */
export function countBreaches(found: readonly Breach[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const b of found) counts.set(`${b.file}|${b.kind}`, (counts.get(`${b.file}|${b.kind}`) ?? 0) + 1);
  return counts;
}

export interface KnownEntry {
  file: string;
  kind: string;
  count: number;
  task: string;
}

/** The ratchet: a breach above its listed count is new; a listed count above the real one is stale. */
export function judgeBreaches(
  actual: ReadonlyMap<string, number>,
  known: readonly KnownEntry[],
): { added: string[]; stale: string[] } {
  const listed = new Map(known.map((e) => [`${e.file}|${e.kind}`, e.count]));
  const added: string[] = [];
  const stale: string[] = [];
  for (const [key, n] of actual) {
    const [file, kind] = key.split('|');
    const was = listed.get(key) ?? 0;
    if (n > was) added.push(`${file}: ${n - was} new ${kind} breach${n - was > 1 ? 'es' : ''}${was ? ` (${was} known)` : ''}`);
  }
  for (const [key, was] of listed) {
    const n = actual.get(key) ?? 0;
    const [file, kind] = key.split('|');
    if (n < was) stale.push(`${file}: ${kind} known ${was}, now ${n}: lower or remove the entry in no-app-css.known.json`);
  }
  return { added, stale };
}
