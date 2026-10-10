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

// Built from pieces so this file does not contain a marker line itself.
const START = new RegExp('^' + '<'.repeat(7) + '( |$)');
const SEPARATOR = new RegExp('^' + '='.repeat(7) + '$');
const END = new RegExp('^' + '>'.repeat(7) + '( |$)');

function repositoryFiles(): string[] {
  const root = execFileSync('git', ['rev-parse', '--show-toplevel'], { encoding: 'utf8' }).trim();
  const listed = execFileSync(
    'git',
    ['ls-files', '-z', '--cached', '--others', '--exclude-standard'],
    { cwd: root, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
  );
  return listed
    .split('\0')
    .filter((f) => f !== '' && SCANNED.has(extname(f).toLowerCase()))
    .map((f) => join(root, f));
}

describe('guard: no merge-conflict markers', () => {
  it('finds files to scan (an empty scan would pass for the wrong reason)', () => {
    expect(repositoryFiles().length).toBeGreaterThan(0);
  });

  it('has no conflict marker line in any source file', () => {
    const hits: string[] = [];
    for (const file of repositoryFiles()) {
      let text: string;
      try {
        text = readFileSync(file, 'utf8');
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
