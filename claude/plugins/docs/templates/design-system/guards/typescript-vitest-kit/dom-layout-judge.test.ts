import { describe, expect, it } from 'vitest';
import { domLayoutSource, judgeLayout, measureDomLayout, LAYOUT_WIDTHS, type KnownLayoutBreach } from './dom-layout.ts';

// Self-test of the DOM layout checker's pure parts (the ratchet judge, the widths, the injected source).
// The measurement itself runs in a browser: see dom-layout-example.spec.ts.
const known: KnownLayoutBreach[] = [{ screen: 'home', width: 360, rule: 'gap', task: 'T1' }];

describe('dom layout judge', () => {
  it('measures at 360, 393 and 1300 px', () => {
    expect(LAYOUT_WIDTHS.map((s) => s.width)).toEqual([360, 393, 1300]);
  });
  it('fails an unknown breach', () => {
    const r = judgeLayout('home', [{ width: 393, rule: 'overflow', text: 'x' }], known);
    expect(r.unknown).toHaveLength(1);
  });
  it('accepts a listed breach and fails a listed breach that is gone', () => {
    expect(judgeLayout('home', [{ width: 360, rule: 'gap', text: 'x' }], known)).toEqual({ unknown: [], stale: [] });
    expect(judgeLayout('home', [], known).stale).toHaveLength(1);
  });
  it('a star width covers every width; other screens are not touched', () => {
    const star: KnownLayoutBreach[] = [{ screen: 'home', width: '*', rule: 'gap', task: 'T1' }];
    expect(judgeLayout('home', [{ width: 1300, rule: 'gap', text: 'x' }], star).unknown).toEqual([]);
    expect(judgeLayout('other', [], star).stale).toEqual([]);
  });
  it('builds a source that carries the options', () => {
    const src = domLayoutSource({ primary: '#go', spaceVar: '--s-' });
    expect(src).toContain('"#go"');
    expect(src).toContain('"--s-"');
  });
  it('measures every width and tags the problems with it', async () => {
    const sizes: number[] = [];
    const page = {
      setViewportSize: (s: { width: number; height: number }) => {
        sizes.push(s.width);
        return Promise.resolve();
      },
      evaluate: <T>() => Promise.resolve([{ rule: 'overflow', text: 't' }] as unknown as T),
    };
    const found = await measureDomLayout(page);
    expect(sizes).toEqual([360, 393, 1300]);
    expect(found.map((f) => f.width)).toEqual([360, 393, 1300]);
  });
});
