import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * STACKSPEC §13.5 guard test (starter): no source file may contain a
 * merge-conflict marker line.
 *
 * Markers left in a committed file break the build in some languages and
 * silently change behaviour in config and data files. The branch gate and the
 * pre-push hook run this project on every push, whatever changed.
 *
 * It scans the tracked and not-ignored files under the repository root. Markdown
 * and plain text are excluded: `=======` alone on a line is a setext heading
 * underline there, not a conflict.
 */

const SCANNED = new Set([
  '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.json', '.jsonc',
  '.yml', '.yaml', '.toml', '.css', '.scss', '.html', '.sql', '.sh',
  '.go', '.rs', '.cs', '.csproj', '.props', '.targets', '.sln',
]);

const SKIP_DIRS = new Set(['.git', 'node_modules', '.delivery']);

// Paths are matched and reported with '/' on every OS: the listing prints them
// that way, but a path that went through Windows tooling may carry '\'.
const toSlash = (path: string): string => path.replaceAll('\\', '/');

// Built from pieces so this file does not contain a marker line itself.
const START = new RegExp('^' + '<'.repeat(7) + '( |$)');
const SEPARATOR = new RegExp('^' + '='.repeat(7) + '$');
const END = new RegExp('^' + '>'.repeat(7) + '( |$)');

// Listed once per run: both tests below use it, and `git` is the slow part to start.
// Another checkout nested in this one (an agent worktree) shows up in the listing as
// one `dir/` entry, which has no scanned extension, so its files are never read.
let listed: { root: string; files: string[] } | undefined;

/** The scanned files as repository-relative paths with '/' separators. */
function repositoryFiles(): { root: string; files: string[] } {
  if (listed) return listed;
  const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
  const out = execFileSync(
    'git',
    ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
  );
  const files = out
    .split('\0')
    .map(toSlash)
    .filter(
      (f) =>
        f !== '' &&
        SCANNED.has(extname(f).toLowerCase()) &&
        !f.split('/').some((segment) => SKIP_DIRS.has(segment)),
    );
  listed = { root, files };
  return listed;
}

describe('guard: no merge-conflict markers', () => {
  it('finds files to scan (an empty scan would pass for the wrong reason)', () => {
    expect(repositoryFiles().files.length).toBeGreaterThan(0);
  });

  it('has no conflict marker line in any source file', () => {
    const hits: string[] = [];
    const { root, files } = repositoryFiles();
    for (const file of files) {
      let text: string;
      try {
        text = readFileSync(join(root, file), 'utf8');
      } catch {
        continue; // deleted in the working tree but still listed
      }
      text.split(/\r?\n/).forEach((line, index) => {
        if (START.test(line) || SEPARATOR.test(line) || END.test(line)) {
          hits.push(`${file}:${index + 1}: ${line}`);
        }
      });
    }
    expect(hits, `merge-conflict markers found:\n${hits.join('\n')}`).toEqual([]);
  });
});
