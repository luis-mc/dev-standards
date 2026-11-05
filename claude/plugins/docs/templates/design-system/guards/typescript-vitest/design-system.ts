/**
 * The one way to find the design system (docs/design-system/README.md; DOCSPEC section 15).
 * Numbered version folders (v1, v2 ...) and one draft, `next-version`. The highest numbered folder is the version
 * every app follows and every guard reads; until v1 exists the guards read `next-version`. Every guard test goes
 * through `enforcedDesignDir()`, so approving a version changes no test.
 *
 * Copy of the luismc-docs template: adjust `repoRoot` if this file does not sit in `<root>/scripts/design/`.
 */
import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

export const DESIGN_SYSTEM = 'docs/design-system';
export const DRAFT = 'next-version';
export const NUMBERED = /^v[1-9]\d*$/;
export const VERSION_NAME = /^(?:v[1-9]\d*|next-version)$/;
/** Added once after approval, then frozen too; not part of the digest. */
export const ONE_TIME = ['audit', 'visual'] as const;
export const repoRoot = join(import.meta.dirname, '..', '..');

export const versionNumbers = (root: string = repoRoot): number[] => {
  const dir = join(root, DESIGN_SYSTEM);
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && NUMBERED.test(e.name))
    .map((e) => Number(e.name.slice(1)))
    .sort((a, b) => a - b);
};

/** True when vN was moved to docs/archive/design-system-vN/ or docs/archive/design-system/vN/ (DOCSPEC R2.7, R15.1). */
export const isArchived = (n: number, root: string = repoRoot): boolean =>
  existsSync(join(root, 'docs', 'archive', `design-system-v${n}`)) ||
  existsSync(join(root, 'docs', 'archive', 'design-system', `v${n}`));

/** The enforced folder name: the highest number, else `next-version`. */
export const enforcedVersion = (root: string = repoRoot): string => {
  const numbers = versionNumbers(root);
  return numbers.length > 0 ? `v${numbers[numbers.length - 1]}` : DRAFT;
};

export const enforcedDesignDir = (root: string = repoRoot): string =>
  join(root, DESIGN_SYSTEM, enforcedVersion(root));

export const readDesignFile = (name: string, root: string = repoRoot): string =>
  readFileSync(join(enforcedDesignDir(root), name), 'utf8');

const normalised = (data: Buffer): Buffer =>
  Buffer.from(data.toString('latin1').replace(/\r\n/g, '\n'), 'latin1');

/** Same algorithm as `design_system.py` `tree_digest`: sha256 over sorted `relpath hash` lines, one-time folders left out. */
export const treeDigest = (folder: string): string => {
  const lines = readdirSync(folder, { withFileTypes: true, recursive: true })
    .filter((e) => e.isFile())
    .map((e) => join(e.parentPath, e.name).slice(folder.length + 1).replaceAll('\\', '/'))
    .filter((rel) => !(ONE_TIME as readonly string[]).includes(rel.split('/')[0]!))
    .sort()
    .map(
      (rel) =>
        `${rel} ${createHash('sha256').update(normalised(readFileSync(join(folder, rel)))).digest('hex')}`,
    );
  return createHash('sha256').update(lines.join('\n')).digest('hex');
};

// Link-only edits (R15.5): after files move, an approved version may change link targets and nothing else.
const LINK = /(\]\()([^)\s]+)|(<a\b[^>]*?\bhref=")([^"]*)|(`)([^`\s]*\/[^`\s]*)(?=`)/g;

const maskLinks = (line: string): { masked: string; targets: { kind: string; target: string }[] } => {
  const targets: { kind: string; target: string }[] = [];
  const masked = line.replace(LINK, (_m, a, b, c, d, e, f) => {
    if (a) { targets.push({ kind: 'md', target: b }); return `${a}\0`; }
    if (c) { targets.push({ kind: 'href', target: d }); return `${c}\0`; }
    targets.push({ kind: 'tick', target: f }); return `${e}\0`;
  });
  return { masked, targets };
};

const targetExists = (root: string, fileRel: string, kind: string, target: string): boolean => {
  const t0 = target.split('#')[0]!.split('?')[0]!;
  if (t0 === '' || /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i.test(t0)) return true; // an anchor or an outside link
  const t = kind === 'tick' ? t0 : decodeURI(t0);
  return existsSync(kind === 'tick' || t.startsWith('/') ? join(root, t) : join(root, dirname(fileRel), t));
};

/** True when every changed line differs only in link targets and each new target exists. */
export const isLinkOnlyChange = (oldText: string, newText: string, fileRel: string, root: string = repoRoot): boolean => {
  const a = oldText.replaceAll('\r\n', '\n').split('\n');
  const b = newText.replaceAll('\r\n', '\n').split('\n');
  if (a.length !== b.length) return false;
  return a.every((x, i) => {
    const y = b[i]!;
    if (x === y) return true;
    const mx = maskLinks(x);
    const my = maskLinks(y);
    if (mx.masked !== my.masked || mx.targets.length !== my.targets.length) return false;
    return my.targets.every((n, j) => n.target === mx.targets[j]!.target || targetExists(root, fileRel, n.kind, n.target));
  });
};
