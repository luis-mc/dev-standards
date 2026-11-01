import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';
import { enforcedDesignDir, readDesignFile, repoRoot } from './design-system.ts';

// Follow guard (R15.6): the apps follow the enforced (highest numbered) version.
//   1. retired words (content.md) are not drawn as UI text;
//   2. the rule table (ux-rules.md) is well formed, its guards exist, and every `design system UX-n` citation resolves;
//   3. screens use tokens, not raw colours.
// Adjust CONFIG to the project. The functions below are pure and tested on examples.
const CONFIG = {
  sourceRoots: ['src'], // folders scanned, repo-relative
  extensions: ['.ts', '.tsx', '.js', '.jsx', '.css'],
  skip: /(\.test\.|\.spec\.|\/testing\/|node_modules|\/dist\/)/,
  tokenFiles: [/tokens?\.css$/, /theme\.css$/], // the only files allowed to hold a raw colour
};

export const section = (text: string, name: string): string => {
  const m = new RegExp(`<!-- ${name}:start -->\\r?\n([\\s\\S]*?)\\r?\n<!-- ${name}:end -->`).exec(text);
  if (!m) throw new Error(`${name} table not found`);
  return m[1]!;
};
const rows = (table: string): string[][] =>
  table
    .split('\n')
    .filter((l) => l.startsWith('|'))
    .slice(2)
    .map((l) => l.split('|').slice(1, -1).map((c) => c.trim()));

/** The retired words of content.md. */
export const retiredWords = (contentMd: string): string[] =>
  rows(section(contentMd, 'retired-words'))
    .map((r) => r[0]!)
    .filter((w) => /^[\w' -]+$/.test(w));

/** Retired words drawn as a whole string literal or JSX text, e.g. 'Submit' or >Submit<. */
export const findRetired = (source: string, words: readonly string[]): string[] =>
  words.filter((w) => {
    const e = w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return new RegExp(`(['"\`]\\s*${e}\\s*['"\`]|>\\s*${e}\\s*<)`).test(source);
  });

/** The rule IDs and their guard column, from the rule table. */
export const ruleTable = (uxRules: string): { id: string; guard: string }[] =>
  rows(section(uxRules, 'rule-table')).map((r) => ({ id: r[0]!, guard: r[2] ?? '' }));

/** `design system UX-4` citations in a source text. */
export const citations = (text: string): string[] =>
  [...text.matchAll(/design system\s+(UX-\d+(?:[ ,]+(?:and\s+)?UX-\d+)*)/gi)].flatMap((m) => m[1]!.match(/UX-\d+/g) ?? []);

/** Raw colours (#hex, rgb(), hsl()) in a text. */
export const rawColours = (text: string): string[] =>
  text.match(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|\b(?:rgb|hsl)a?\([^)]*\)/g) ?? [];

const walk = (dir: string): string[] =>
  !existsSync(dir)
    ? []
    : readdirSync(dir, { withFileTypes: true, recursive: true })
        .filter((e) => e.isFile())
        .map((e) => join(e.parentPath, e.name));
const sources = CONFIG.sourceRoots
  .flatMap((r) => walk(join(repoRoot, r)))
  .map((p) => p.replaceAll('\\', '/'))
  .filter((p) => CONFIG.extensions.some((x) => p.endsWith(x)) && !CONFIG.skip.test(p));
const text = new Map(sources.map((p) => [p, readFileSync(p, 'utf8')]));

describe('the pure checks', () => {
  it('finds retired words as UI text only', () => {
    expect(findRetired("<button>Submit</button> label('Click here')", ['Submit', 'Click here'])).toEqual(['Submit', 'Click here']);
    expect(findRetired('const submitForm = () => {}', ['Submit'])).toEqual([]);
  });
  it('reads citations and raw colours', () => {
    expect(citations('see design system UX-1, UX-4 and design system UX-2')).toEqual(['UX-1', 'UX-4', 'UX-2']);
    expect(rawColours('color: #fff; background: rgb(1, 2, 3); id="#top"')).toEqual(['#fff', 'rgb(1, 2, 3)']);
  });
});

describe('the apps follow the enforced design-system version', () => {
  it('uses no retired word as UI text', () => {
    const words = retiredWords(readDesignFile('content.md'));
    const found = [...text].flatMap(([p, t]) => findRetired(t, words).map((w) => `${relative(repoRoot, p)}: "${w}"`));
    expect(found).toEqual([]);
  });

  it('has a well formed rule table whose guards exist', () => {
    const rules = ruleTable(readDesignFile('ux-rules.md'));
    expect(rules.length).toBeGreaterThan(0);
    expect(new Set(rules.map((r) => r.id)).size).toBe(rules.length);
    for (const r of rules) {
      expect(r.id, 'rule ID').toMatch(/^UX-\d+$/);
      const guard = r.guard.replaceAll('`', '');
      if (guard && guard !== 'none yet') expect(existsSync(join(repoRoot, guard)), `${r.id}: guard ${guard}`).toBe(true);
    }
  });

  it('cites only rule IDs that exist', () => {
    const ids = new Set(ruleTable(readDesignFile('ux-rules.md')).map((r) => r.id));
    const bad = [...text].flatMap(([p, t]) => citations(t).filter((c) => !ids.has(c)).map((c) => `${relative(repoRoot, p)}: ${c}`));
    expect(bad).toEqual([]);
  });

  it('uses tokens, not raw colours, outside the token files', () => {
    const bad = [...text]
      .filter(([p]) => !CONFIG.tokenFiles.some((re) => re.test(p)))
      .flatMap(([p, t]) => rawColours(t).map((c) => `${relative(repoRoot, p)}: ${c}`));
    expect(bad).toEqual([]);
  });

  it('enforces a folder that exists', () => {
    expect(existsSync(enforcedDesignDir())).toBe(true);
  });
});
