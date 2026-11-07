import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { countBreaches, judgeBreaches, scanText, scanTree, TYPES, type KnownEntry } from './raw-inputs-scan.ts';

// No native date, time or number input (design system UX-56, Enforcement kit). Dates use the date picker, times
// use the time picker, and the number keypad is only for counts, measures and codes. Today's breaches are the
// known list `raw-inputs.known.json` (file, type, count). It is a ratchet: a new breach fails, and a listed breach
// that is gone but still listed fails too. Adjust CONFIG in raw-inputs-scan.ts to your folders.
const root = join(import.meta.dirname, '..', '..');
const known = (JSON.parse(readFileSync(join(import.meta.dirname, 'raw-inputs.known.json'), 'utf8')) as { entries: KnownEntry[] }).entries;

describe('no native date, time or number input (UX-56)', () => {
  it('every known breach names a banned type and a count', () => {
    for (const e of known) {
      expect(TYPES, `${e.file}: type`).toContain(e.type);
      expect(e.count).toBeGreaterThan(0);
    }
  });

  it('no new native input, and no listed one that is already gone (the list only shrinks)', () => {
    const { added, stale } = judgeBreaches(countBreaches(scanTree(root)), known);
    expect(added, 'native date, time or number input: use the picker or the keypad').toEqual([]);
    expect(stale, 'fixed breach still listed: shrink the known list').toEqual([]);
  });

  describe('the scan itself', () => {
    const count = (file: string, text: string) => countBreaches(scanText(file, text));
    it('finds each banned type', () => {
      const text = '<input type="date"/><input type="time" /><input type=\'datetime-local\'/><input type={"number"} />';
      expect(scanText('apps/web/a.tsx', text).map((b) => b.type)).toEqual(['date', 'time', 'datetime-local', 'number']);
    });
    it('a planted native input fails', () => {
      for (const t of TYPES) {
        expect(judgeBreaches(count('apps/web/src/a.tsx', `<input type="${t}" />`), []).added, t).toHaveLength(1);
      }
    });
    it('other input types pass', () => {
      expect(scanText('apps/web/a.tsx', '<input type="text" inputMode="numeric"/><input type="email"/><button type="button"/>')).toEqual([]);
      expect(scanText('apps/web/a.tsx', '<input type="datetime"/><input type="numbers"/>')).toEqual([]);
    });
    it('a listed breach passes', () => {
      const entry = { file: 'apps/web/src/a.tsx', type: 'date', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<input type="date"/>'), [entry])).toEqual({ added: [], stale: [] });
    });
    it('a fixed but listed breach fails', () => {
      const entry = { file: 'apps/web/src/a.tsx', type: 'date', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<DatePicker />'), [entry]).stale).toHaveLength(1);
    });
    it('a raised count fails', () => {
      const entry = { file: 'apps/web/src/a.tsx', type: 'number', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<input type="number"/><input type="number"/>'), [entry]).added).toHaveLength(1);
    });
    it('the shared UI is judged too', () => {
      expect(scanText('packages/ui/src/field.tsx', '<input type="time"/>')).toHaveLength(1);
    });
    it('a test file is ignored', () => {
      expect(scanText('apps/web/src/a.test.tsx', '<input type="date"/>')).toEqual([]);
      expect(scanText('apps/web/src/__tests__/a.tsx', '<input type="date"/>')).toEqual([]);
    });
    it('other file types are ignored', () => {
      expect(scanText('apps/web/a.ts', 'const s = \'type="date"\'')).toEqual([]);
      expect(scanText('apps/web/a.vue', '<input type="date">')).toHaveLength(1);
    });
  });
});
