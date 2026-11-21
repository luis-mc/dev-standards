import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { bannedHits, checkStrings, literals, plainHits, scanRoot, type Words } from './words-lint.ts';

// LC-2 and LC-31 (DS235a). The self-tests prove the rules; the last test scans the project.
const words: Words = { states: { available: { title: 'Version {version} is ready.', no: 'Not now' } } };
const root = join(import.meta.dirname, '..', '..');

describe('words lint', () => {
  it('passes a clean string from the table', () => {
    expect(checkStrings(['Version {version} is ready.'], words)).toEqual([]);
  });
  it('flags each banned word', () => {
    for (const w of ['OK', 'Yes', 'No', 'Install now', 'Later', 'daemon', 'binary', 'payload']) {
      expect(bannedHits(`Press ${w} to go`)).toContain(w);
    }
  });
  it('does not flag a word that only contains a banned one', () => {
    expect(bannedHits('Nothing changed. Notes.')).toEqual([]);
  });
  it('flags error codes, HTTP statuses and doubled punctuation', () => {
    expect(plainHits('Failed with 0x80070005')).toContain('error code');
    expect(plainHits('Error 1603')).toContain('error code');
    expect(plainHits('The server said HTTP 503')).toContain('HTTP status');
    expect(plainHits('Done..')).toContain('doubled punctuation');
  });
  it('flags a string that is not in the table', () => {
    expect(checkStrings(['Click here'], words).map((f) => f.why)).toContain('not in the words table');
  });
  it('reads string literals', () => {
    expect(literals(`const a = 'x y'; const b = "z w"; const c = \`q r\`;`)).toEqual(['x y', 'z w', 'q r']);
  });
  it('the project has no finding', () => {
    expect(scanRoot(root)).toEqual([]);
  });
});
