import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DESIGN_SYSTEM, NUMBERED, approvalProblems, type Approval, ONE_TIME, isArchived, isLinkOnlyChange, repoRoot, treeDigest, versionNumbers } from './design-system.ts';

// Freeze guard (R15.4, R15.5): an approved version is read-only, and design changes touch only next-version.
// Two checks: the digest recorded at approval (approvals.json) still matches the folder, and the branch's diff
// against its base (DESIGN_BASE, default origin/main) changes no numbered folder except the one-time audit/ and visual/,
// and link-only edits (every changed line differs only in link targets, each new target exists) after files move.

export interface Change {
  status: string; // git status letter: A, M, D, R, C, T
  path: string; // repo-relative
}

/** What breaks the freeze. `known` lists the numbered versions that approvals.json records. */
export const freezeProblems = (
  changes: readonly Change[],
  known: readonly string[] = [],
  archived: readonly string[] = [],
  linkOnly: (path: string) => boolean = () => false,
): string[] => {
  const problems: string[] = [];
  const pattern = new RegExp(`^${DESIGN_SYSTEM}/(v[1-9]\\d*)/(.*)$`);
  for (const { status, path } of changes) {
    const m = pattern.exec(path);
    if (!m) continue;
    const version = m[1]!;
    const rest = m[2]!;
    const oneTime = (ONE_TIME as readonly string[]).includes(rest.split('/')[0]!);
    if (status === 'D' && archived.includes(version)) continue; // moved to docs/archive/: an archive, not an edit
    if (status === 'M' && linkOnly(path)) continue; // a link-only edit after files moved
    const promotion = status === 'A' && known.includes(version); // a new version folder, approved in approvals.json
    if (!(status === 'A' && oneTime) && !promotion)
      problems.push(`${path} (${status}): ${version} is approved and read-only; put the change into next-version`);
  }
  return problems;
};

const git = (...args: string[]): string | null => {
  try {
    return execFileSync('git', args, { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
  } catch {
    return null;
  }
};

const approvalsFile = join(repoRoot, DESIGN_SYSTEM, 'approvals.json');
const recorded = (): Record<string, Approval> =>
  existsSync(approvalsFile)
    ? (JSON.parse(readFileSync(approvalsFile, 'utf8')) as { versions: Record<string, Approval> }).versions
    : {};

describe('an approved design-system version is read-only', () => {
  it('tells a frozen edit from an allowed addition', () => {
    const p = (s: string, rest: string): Change => ({ status: s, path: `${DESIGN_SYSTEM}/v1/${rest}` });
    expect(freezeProblems([p('A', 'audit/index.html'), p('A', 'visual/a.png')])).toEqual([]);
    expect(freezeProblems([p('M', 'ux-rules.md')])).toHaveLength(1);
    expect(freezeProblems([p('D', 'tokens.md')])).toHaveLength(1);
    expect(freezeProblems([p('A', 'notes.md')])).toHaveLength(1);
    expect(freezeProblems([p('A', 'README.md')], ['v1'])).toEqual([]); // the promotion itself
    expect(freezeProblems([p('D', 'tokens.md')], ['v1'], ['v1'])).toEqual([]); // v1 moved to docs/archive/
    expect(freezeProblems([p('M', 'README.md')], [], [], () => true)).toEqual([]); // a link-only edit
    expect(freezeProblems([p('A', 'README.md')], [], [], () => true)).toHaveLength(1);
    expect(freezeProblems([{ status: 'M', path: `${DESIGN_SYSTEM}/next-version/tokens.md` }])).toEqual([]);
  });

  it('tells a missing approval record from a complete one (R15.14)', () => {
    const ok: Approval = { digest: 'd', approved: { by: 'owner', date: '2026-01-01', evidence: 'chat' }, implementation: { date: '2026-01-02', evidence: 'chat' } };
    expect(approvalProblems(['v1'], { v1: ok })).toEqual([]);
    expect(approvalProblems(['v1'], {})).toHaveLength(2); // no entry: no approval, no implementation
    expect(approvalProblems(['v1'], { v1: { ...ok, approved: { by: 'owner', date: '2026-01-01' } } })[0]).toContain('approved.evidence');
    expect(approvalProblems(['v1'], { v1: { ...ok, digest: '' } })[0]).toContain('digest');
    expect(approvalProblems(['v1', 'v2'], { v1: ok, v2: { ...ok, implementation: null } })).toHaveLength(1); // only the highest needs it
    expect(approvalProblems(['v1'], { v1: { ...ok, implementation: { date: '2026-01-02', evidence: 'live as-is' } } })).toEqual([]);
  });

  it('has a complete owner approval for every numbered version, and an implementation approval for the enforced one (R15.14)', () => {
    const names = versionNumbers().map((n) => `v${n}`);
    expect(approvalProblems(names, recorded())).toEqual([]);
  });

  it('keeps each numbered version equal to its digest at approval', () => {
    const all = recorded();
    for (const n of versionNumbers()) {
      const name = `v${n}`;
      if (all[name] === undefined) continue; // reported with its fix command by the approval check above
      expect(treeDigest(join(repoRoot, DESIGN_SYSTEM, name)), `${name} was edited after its approval`).toBe(all[name]!.digest);
    }
  });

  it('changes no numbered version on this branch', () => {
    const base = process.env['DESIGN_BASE'] ?? 'origin/main';
    const mb = git('merge-base', base, 'HEAD')?.trim();
    if (!mb) return; // no base to compare with (shallow clone): the digest check above still holds
    const out = git('diff', '--no-renames', '--name-status', mb, '--', `${DESIGN_SYSTEM}/`) ?? '';
    const changes = out
      .split('\n')
      .filter(Boolean)
      .map((l) => {
        const [status, path] = l.split('\t') as [string, string];
        return { status: status[0]!, path };
      })
      .filter((c) => NUMBERED.test(c.path.split('/')[2] ?? ''));
    expect(freezeProblems(
        changes,
        Object.keys(recorded()),
        Object.keys(recorded()).filter((v) => isArchived(Number(v.slice(1)))),
        (path) => {
          const old = git('show', `${mb}:${path}`);
          return old !== null && existsSync(join(repoRoot, path)) && isLinkOnlyChange(old, readFileSync(join(repoRoot, path), 'utf8'), path);
        },
      )).toEqual([]);
  });
});
