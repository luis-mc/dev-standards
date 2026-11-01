import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DESIGN_SYSTEM, DRAFT, NUMBERED, VERSION_NAME, enforcedVersion, repoRoot } from './design-system.ts';

// Layout guard (R15.1, R15.2): only version folders, README.md and approvals.json sit in docs/design-system/;
// versions are numbered without a gap; every version holds its files.
const FILES = ['README.md', 'CHANGES.md', 'ux-rules.md', 'components.md', 'tokens.md', 'content.md', 'review-visuals/index.html'];
const BESIDE = ['README.md', 'approvals.json'];

export const layoutProblems = (entries: readonly [string, boolean][]): string[] => {
  const problems: string[] = [];
  for (const [name, folder] of entries) {
    if (!folder && !BESIDE.includes(name) && name !== '.gitkeep')
      problems.push(`${name}: only ${BESIDE.join(' and ')} sit beside the versions`);
    if (folder && !VERSION_NAME.test(name))
      problems.push(`${name}/: a version folder is v1, v2 ... or ${DRAFT}`);
  }
  const numbers = entries
    .filter(([n, f]) => f && NUMBERED.test(n))
    .map(([n]) => Number(n.slice(1)))
    .sort((a, b) => a - b);
  numbers.forEach((n, i) => {
    if (n !== i + 1) problems.push(`v${n}/: versions are numbered v1, v2 ... without a gap`);
  });
  return problems;
};

const dir = join(repoRoot, DESIGN_SYSTEM);

describe('the design system folder', () => {
  it('tells a good layout from a bad one', () => {
    expect(layoutProblems([['README.md', false], [DRAFT, true], ['v1', true]])).toEqual([]);
    expect(layoutProblems([['tokens.md', false]])).toHaveLength(1);
    expect(layoutProblems([['v2', true]])).toHaveLength(1);
    expect(layoutProblems([['1', true]])).toHaveLength(1);
  });

  it('holds only version folders, README.md and approvals.json', () => {
    const entries = readdirSync(dir, { withFileTypes: true }).map((e): [string, boolean] => [e.name, e.isDirectory()]);
    expect(layoutProblems(entries)).toEqual([]);
  });

  it('gives every version folder its files', () => {
    const versions = readdirSync(dir, { withFileTypes: true }).filter((e) => e.isDirectory() && VERSION_NAME.test(e.name));
    for (const v of versions)
      for (const f of FILES) expect(existsSync(join(dir, v.name, f)), `${v.name}/${f}`).toBe(true);
  });

  it('has a version to enforce', () => {
    expect(existsSync(join(dir, enforcedVersion(), 'ux-rules.md'))).toBe(true);
  });
});
