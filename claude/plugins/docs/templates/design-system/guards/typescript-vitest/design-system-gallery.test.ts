import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { DESIGN_SYSTEM, DRAFT, enforcedVersion, repoRoot, sourcesDigest, versionNumbers } from './design-system.ts';

// Gallery freshness guard (R15.14): review-visuals/index.html carries `<!-- source-digest: X -->`, the digest of the
// version's md files. It must equal a fresh digest. On a release branch, or with DESIGN_GATE=release (the ready PR to
// the default branch), a stale gallery fails; on a task branch it only warns (the join rebuilds it).
// A project with its own generator keeps the same stamp, or sets DESIGN_GALLERY_DIGEST_CMD to a command that prints the digest.

export const staleReason = (html: string | null, want: string): string | null => {
  if (html === null) return 'no gallery';
  const m = /<!-- source-digest: (\w+) -->/.exec(html);
  if (!m) return 'the gallery carries no source-digest stamp';
  return m[1] === want ? null : "the gallery is older than the version's files";
};

export const isRelease = (branch: string, defaultBranch: string, gate: string | undefined): boolean =>
  gate?.trim().toLowerCase() === 'release' || branch === defaultBranch || branch.startsWith('release');

const branchName = (): string => {
  try {
    return execFileSync('git', ['rev-parse', '--abbrev-ref', 'HEAD'], { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
  } catch {
    return '';
  }
};

describe('the design-system gallery is fresh (R15.14)', () => {
  it('tells a stale stamp from a fresh one', () => {
    expect(staleReason('<!-- source-digest: abc -->', 'abc')).toBeNull();
    expect(staleReason('<!-- source-digest: abc -->', 'def')).toContain('older');
    expect(staleReason('<html></html>', 'abc')).toContain('no source-digest');
    expect(staleReason(null, 'abc')).toBe('no gallery');
  });

  it('tells a release branch from a task branch', () => {
    expect(isRelease('release/1.2', 'main', undefined)).toBe(true);
    expect(isRelease('main', 'main', undefined)).toBe(true);
    expect(isRelease('DS1-x', 'main', undefined)).toBe(false);
    expect(isRelease('DS1-x', 'main', 'release')).toBe(true);
  });

  it('matches the stamp of next-version and of the enforced version', () => {
    const release = isRelease(branchName(), process.env['DESIGN_DEFAULT_BRANCH'] ?? 'main', process.env['DESIGN_GATE']);
    const names = [DRAFT, ...(versionNumbers().length ? [enforcedVersion()] : [])];
    for (const name of names) {
      const folder = join(repoRoot, DESIGN_SYSTEM, name);
      if (!existsSync(join(folder, 'ux-rules.md'))) continue;
      const file = join(folder, 'review-visuals', 'index.html');
      let want = sourcesDigest(folder);
      const cmd = process.env['DESIGN_GALLERY_DIGEST_CMD'];
      if (cmd) want = execFileSync(cmd, { cwd: folder, shell: true, encoding: 'utf8' }).trim().split(/\s+/)[0] ?? '';
      const why = staleReason(existsSync(file) ? readFileSync(file, 'utf8') : null, want);
      if (!why) continue;
      const msg = `${DESIGN_SYSTEM}/${name}/review-visuals/index.html: ${why}. Fix: design_system.py visuals (or your generator, which writes the same stamp)`;
      if (release) expect.fail(msg);
      console.warn(`WARN ${msg} (task branch: the join rebuilds it)`);
    }
  });
});
