import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { countBreaches, judgeBreaches, scanApps, scanText, TAGS, type KnownEntry } from './raw-controls-scan.ts';

// No raw controls (design system, Enforcement kit). App code has no raw <button>, <input>, <select> or <textarea>;
// it uses the shared UI components. Today's breaches are the known list `raw-controls.known.json` (file, tag, count).
// It is a ratchet: a new breach fails, and a listed breach that is gone but still listed fails too.
// Adjust CONFIG in raw-controls-scan.ts to your folders.
const root = join(import.meta.dirname, '..', '..');
const known = (JSON.parse(readFileSync(join(import.meta.dirname, 'raw-controls.known.json'), 'utf8')) as { entries: KnownEntry[] }).entries;

describe('no raw controls', () => {
  it('every known breach names a real tag and a count', () => {
    for (const e of known) {
      expect(TAGS, `${e.file}: tag`).toContain(e.tag);
      expect(e.count).toBeGreaterThan(0);
    }
  });

  it('no new raw control, and no listed one that is already gone (the list only shrinks)', () => {
    const { added, stale } = judgeBreaches(countBreaches(scanApps(root)), known);
    expect(added, 'new raw control: use the shared UI component').toEqual([]);
    expect(stale, 'fixed breach still listed: shrink the known list').toEqual([]);
  });

  describe('the scan itself', () => {
    const count = (file: string, text: string) => countBreaches(scanText(file, text));
    it('a planted raw button fails', () => {
      const actual = count('apps/web/src/a.tsx', '<div><button onClick={f}>Go</button></div>');
      expect(judgeBreaches(actual, []).added).toHaveLength(1);
    });
    it('finds all four tags and ignores components', () => {
      const found = scanText('apps/web/a.tsx', '<button/><input type="x"/><select></select><textarea />').map((b) => b.tag);
      expect(found).toEqual(['button', 'input', 'select', 'textarea']);
      expect(scanText('apps/web/a.tsx', '<Button /><InputField /><buttonGroup>')).toEqual([]);
    });
    it('a listed breach passes', () => {
      const entry = { file: 'apps/web/src/a.tsx', tag: 'button', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<button>x</button>'), [entry])).toEqual({ added: [], stale: [] });
    });
    it('a fixed but listed breach fails', () => {
      const entry = { file: 'apps/web/src/a.tsx', tag: 'button', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<Button>x</Button>'), [entry]).stale).toHaveLength(1);
    });
    it('a raised count fails', () => {
      const entry = { file: 'apps/web/src/a.tsx', tag: 'button', count: 1 };
      expect(judgeBreaches(count('apps/web/src/a.tsx', '<button/><button/>'), [entry]).added).toHaveLength(1);
    });
    it('a shared-path file is ignored', () => {
      expect(scanText('packages/ui/src/button.tsx', '<button>x</button>')).toEqual([]);
    });
    it('a test file is ignored', () => {
      expect(scanText('apps/web/src/a.test.tsx', '<button>x</button>')).toEqual([]);
      expect(scanText('apps/web/src/__tests__/a.tsx', '<button>x</button>')).toEqual([]);
      expect(scanText('apps/web/tests/a.tsx', '<button>x</button>')).toEqual([]);
    });
    it('other file types are ignored', () => {
      expect(scanText('apps/web/a.ts', 'const s = "<button>"')).toEqual([]);
      expect(scanText('apps/web/a.vue', '<button>x</button>')).toHaveLength(1);
    });
  });
});
