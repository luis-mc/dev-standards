import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { countBreaches, judgeBreaches, KINDS, scanApps, scanText, type KnownEntry } from './no-app-css-scan.ts';

// No app CSS (design system, Enforcement kit). An app folder carries no stylesheet, no CSS-in-JS block, no `style=`
// with layout or colour values and no class the shared UI package does not define. Every look lives in the shared
// package. Today's breaches are the known list `no-app-css.known.json` (file, kind, count, the task that removes
// it). It is a ratchet: a new breach fails, and a listed breach that is gone but still listed fails too.
// Adjust CONFIG in no-app-css-scan.ts, and TASK_ID below to your task-ID prefixes.
const root = join(import.meta.dirname, '..', '..');
const TASK_ID = /^[A-Z]+\d+/;
const known = (JSON.parse(readFileSync(join(import.meta.dirname, 'no-app-css.known.json'), 'utf8')) as { entries: KnownEntry[] }).entries;

describe('no app CSS', () => {
  it('every known breach names its removing task and a real kind', () => {
    for (const e of known) {
      expect(KINDS, `${e.file}: kind`).toContain(e.kind);
      expect(e.task, `${e.file}: task`).toMatch(TASK_ID);
      expect(e.count).toBeGreaterThan(0);
    }
  });

  it('no new breach, and no listed breach that is already gone (the list only shrinks)', () => {
    const { added, stale } = judgeBreaches(countBreaches(scanApps(root)), known);
    expect(added, 'new app CSS: use shared UI parts').toEqual([]);
    expect(stale, 'fixed breach still listed: shrink the known list').toEqual([]);
  });

  describe('the scan itself', () => {
    const kit = new Set(['k-btn', 'k-card']);
    const kinds = (file: string, text: string): string[] => scanText(file, text, kit).map((b) => b.kind);
    it('finds a stylesheet', () => {
      expect(kinds('apps/x/src/x.css', '.a{}')).toEqual(['stylesheet']);
      expect(kinds('apps/x/src/x.scss', '.a{}')).toEqual(['stylesheet']);
    });
    it('finds CSS in code', () => {
      expect(kinds('apps/x/a.tsx', 'const A = styled.div`color:red`;')).toEqual(['css-in-js']);
      expect(kinds('apps/x/a.tsx', 'el.style.cssText = "a:b"')).toEqual(['css-in-js']);
      expect(kinds('apps/x/a.tsx', '<style>{x}</style>')).toEqual(['css-in-js']);
    });
    it('allows style= only for custom properties', () => {
      expect(kinds('apps/x/a.tsx', '<i style={{ "--w": w }} />')).toEqual([]);
      expect(kinds('apps/x/a.tsx', '<i style={{ width: 4 }} />')).toEqual(['style-attr']);
      expect(kinds('apps/x/a.html', '<i style="color:red">')).toEqual(['style-attr']);
    });
    it('allows shared classes and flags others', () => {
      expect(kinds('apps/x/a.tsx', '<b className="k-btn k-card" />')).toEqual([]);
      expect(kinds('apps/x/a.tsx', '<b className="k-btn mine" />')).toEqual(['class-name']);
      expect(kinds('apps/x/a.tsx', '<b className={cond ? "mine" : "k-btn"} />')).toEqual(['class-name']);
      expect(kinds('apps/x/a.tsx', '<b className={props.className} />')).toEqual([]);
    });
    it('judges a ratchet both ways', () => {
      const entry = { file: 'a.tsx', kind: 'style-attr', count: 2, task: 'T1' };
      expect(judgeBreaches(new Map([['a.tsx|style-attr', 3]]), [entry]).added).toHaveLength(1);
      expect(judgeBreaches(new Map([['a.tsx|style-attr', 1]]), [entry]).stale).toHaveLength(1);
      expect(judgeBreaches(new Map([['a.tsx|style-attr', 2]]), [entry])).toEqual({ added: [], stale: [] });
      expect(judgeBreaches(new Map([['b.tsx|class-name', 1]]), []).added).toHaveLength(1);
    });
  });
});
