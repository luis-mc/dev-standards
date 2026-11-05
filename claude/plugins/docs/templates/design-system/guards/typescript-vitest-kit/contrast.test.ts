import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { contrastRatio, judgeContrast, judgeGaps, parseColor, readGaps, type KnownEntry } from './contrast.ts';

// Contrast (design system, Enforcement kit). Every text-on-fill token pair meets WCAG 2.2 AA (4.5:1) in every
// theme. Today's gaps are the known list `contrast.known.json` (theme, fill, text, ratio). It is a ratchet: a new
// gap fails, and a listed gap that now passes but is still listed fails too. Adjust CONFIG in contrast.ts.
const root = join(import.meta.dirname, '..', '..');
const known = (JSON.parse(readFileSync(join(import.meta.dirname, 'contrast.known.json'), 'utf8')) as { entries: KnownEntry[] }).entries;

describe('contrast', () => {
  it('no new gap, and no listed gap that already passes (the list only shrinks)', () => {
    const { added, stale } = judgeGaps(readGaps(root), known);
    expect(added, 'new contrast gap: fix the token').toEqual([]);
    expect(stale, 'fixed gap still listed: shrink the known list').toEqual([]);
  });

  describe('the judge itself', () => {
    const p = '--ds-color-';
    const css = (extra = '') => `:root{${p}brand:#0b5fff;${p}on-brand:#ffffff;${p}brand-tint:#e6efff;${p}on-brand-tint:#0a2a6b;}${extra}`;
    it('computes WCAG ratios', () => {
      expect(Math.round(contrastRatio([0, 0, 0], [255, 255, 255]))).toBe(21);
      expect(parseColor('#fff')).toEqual([255, 255, 255]);
      expect(parseColor('rgb(10 20 30)')).toEqual([10, 20, 30]);
      expect(parseColor('rgba(10, 20, 30, 0.5)')).toEqual(null);
    });
    it('passes a passing pair, tint pairs included', () => {
      expect(judgeContrast(css())).toEqual([]);
    });
    it('finds a failing pair', () => {
      const gaps = judgeContrast(css().replace('#ffffff', '#9ab8ff'));
      expect(gaps).toHaveLength(1);
      expect(gaps[0]?.theme).toBe('light');
      expect(gaps[0]?.fill).toBe(p + 'brand');
    });
    it('a listed gap passes, a new one fails', () => {
      const gaps = judgeContrast(css().replace('#ffffff', '#9ab8ff'));
      const entry = { theme: 'light', fill: p + 'brand', text: p + 'on-brand', ratio: gaps[0]?.ratio ?? null };
      expect(judgeGaps(gaps, [entry])).toEqual({ added: [], stale: [] });
      expect(judgeGaps(gaps, []).added).toHaveLength(1);
      expect(judgeGaps(gaps, [{ ...entry, ratio: 9 }]).added).toHaveLength(1);
    });
    it('a fixed but listed gap fails', () => {
      const entry = { theme: 'light', fill: p + 'brand', text: p + 'on-brand', ratio: 2.1 };
      expect(judgeGaps(judgeContrast(css()), [entry]).stale).toHaveLength(1);
    });
    it('a theme inherits a value it does not set', () => {
      // dark sets only the fill; the text colour (white) comes from :root and now fails on a light fill
      const gaps = judgeContrast(css(`@media (prefers-color-scheme: dark){:root{${p}brand:#f0f0ff;}}`));
      expect(gaps).toHaveLength(1);
      expect(gaps[0]?.theme).toBe('dark');
      expect(gaps[0]?.text).toBe(p + 'on-brand');
    });
    it('reads [data-theme=NAME] blocks and var() references', () => {
      const gaps = judgeContrast(css(`[data-theme="calm"]{${p}on-brand:var(${p}brand-tint);${p}brand:#e6efff;}`));
      expect(gaps.map((g) => g.theme)).toEqual(['calm']);
    });
    it('reports a translucent colour as cannot judge', () => {
      const gaps = judgeContrast(css().replace('#ffffff', 'rgba(255,255,255,0.8)'));
      expect(gaps).toEqual([{ theme: 'light', fill: p + 'brand', text: p + 'on-brand', ratio: null }]);
    });
  });
});
