import { existsSync, readFileSync } from 'node:fs';

/**
 * The judge behind `contrast.test.ts` (design system, Enforcement kit): every text-on-fill token pair meets
 * WCAG 2.2 AA (4.5:1 for text) in every theme. Copy of the luismc-docs template; adjust CONFIG to the project.
 *
 * Pairs: each fill token `<prefix>X` that has `<prefix>on-X` (this covers `X-tint` with `on-X-tint`).
 * Themes: `:root` is `light`; a dark block (`@media (prefers-color-scheme: dark)` or `[data-theme=dark]`) is
 * `dark`; any other `[data-theme=NAME]` block is `NAME`. A theme inherits the values it does not set from `:root`.
 * Colours: `#rgb`, `#rrggbb`, `rgb()` and `rgba()`, and `var(--token)` pointing at one. An alpha below 1 is not
 * blended: the pair is reported as "cannot judge" (ratio `null`).
 */
export const CONFIG = {
  /** The token CSS file, repo-relative. */
  tokensPath: 'packages/ui/src/tokens.css',
  /** The colour token prefix. */
  prefix: '--ds-color-',
  /** The least contrast for text. */
  minRatio: 4.5,
};

export interface Gap {
  readonly theme: string;
  readonly fill: string;
  readonly text: string;
  /** The measured contrast, two decimals; null when the pair cannot be judged. */
  readonly ratio: number | null;
}

type Rgb = readonly [number, number, number];

/** A colour as sRGB 0-255, or null when it cannot be judged (unknown syntax, or an alpha below 1). */
export function parseColor(value: string): Rgb | null {
  const v = value.trim().toLowerCase();
  const hex = /^#([0-9a-f]{3,8})$/.exec(v);
  if (hex) {
    let h = hex[1] as string;
    if (h.length === 3 || h.length === 4) h = [...h].map((c) => c + c).join('');
    if (h.length !== 6 && h.length !== 8) return null;
    if (h.length === 8 && parseInt(h.slice(6), 16) < 255) return null;
    return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
  }
  const fn = /^rgba?\(([^)]*)\)$/.exec(v);
  if (!fn) return null;
  const parts = (fn[1] as string).split(/[\s,/]+/).filter(Boolean);
  if (parts.length !== 3 && parts.length !== 4) return null;
  if (parts.length === 4) {
    const a = parts[3] as string;
    const alpha = a.endsWith('%') ? parseFloat(a) / 100 : parseFloat(a);
    if (!(alpha >= 1)) return null;
  }
  const rgb = parts.slice(0, 3).map((p) => (p.endsWith('%') ? (parseFloat(p) * 255) / 100 : parseFloat(p)));
  if (rgb.some((n) => Number.isNaN(n))) return null;
  return rgb.map((n) => Math.min(255, Math.max(0, n))) as unknown as Rgb;
}

/** WCAG 2.2 relative luminance. */
export function luminance([r, g, b]: Rgb): number {
  const lin = (c: number): number => {
    const s = c / 255;
    return s <= 0.04045 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** WCAG 2.2 contrast ratio, 1 to 21. */
export function contrastRatio(a: Rgb, b: Rgb): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

type Tokens = Map<string, string>;

/** The token declarations of each theme, as written (no inheritance yet). */
export function readThemes(css: string): Map<string, Tokens> {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const themes = new Map<string, Tokens>();
  const stack: string[] = [];
  let buf = '';
  const themeOf = (): string | null => {
    const inDark = stack.some((s) => s.startsWith('@media') && /prefers-color-scheme\s*:\s*dark/.test(s));
    const sel = stack.filter((s) => !s.startsWith('@')).join(' ');
    const attr = /\[data-theme\s*=\s*["']?([\w-]+)["']?\]/.exec(sel);
    if (attr) return attr[1] as string;
    if (inDark) return 'dark';
    return /(^|[\s,])(:root|html)\b/.test(sel) ? 'light' : null;
  };
  const declare = (body: string): void => {
    const theme = themeOf();
    if (theme === null) return;
    const map = themes.get(theme) ?? new Map<string, string>();
    themes.set(theme, map);
    for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+)/g)) map.set(m[1] as string, (m[2] as string).trim());
  };
  for (const ch of text) {
    if (ch === '{') {
      stack.push(buf.trim());
      buf = '';
    } else if (ch === '}') {
      declare(buf);
      buf = '';
      stack.pop();
    } else {
      buf += ch;
    }
  }
  return themes;
}

/** A theme's token values: its own over `:root`. */
function resolved(themes: Map<string, Tokens>, theme: string): Tokens {
  return new Map([...(themes.get('light') ?? []), ...(themes.get(theme) ?? [])]);
}

function colorOf(tokens: Tokens, name: string, depth = 0): Rgb | null {
  const raw = tokens.get(name);
  if (raw === undefined || depth > 8) return null;
  const ref = /^var\(\s*(--[\w-]+)\s*(?:,[^)]*)?\)$/.exec(raw);
  return ref ? colorOf(tokens, ref[1] as string, depth + 1) : parseColor(raw);
}

/** Every pair below the minimum (or not judgeable), in every theme. Pure: CSS text in, gaps out. */
export function judgeContrast(css: string, config = CONFIG): Gap[] {
  const themes = readThemes(css);
  if (!themes.has('light')) themes.set('light', new Map());
  const gaps: Gap[] = [];
  for (const theme of themes.keys()) {
    const tokens = resolved(themes, theme);
    for (const name of tokens.keys()) {
      if (!name.startsWith(config.prefix)) continue;
      const x = name.slice(config.prefix.length);
      if (x.startsWith('on-')) continue;
      const text = `${config.prefix}on-${x}`;
      if (!tokens.has(text)) continue;
      const fill = colorOf(tokens, name);
      const ink = colorOf(tokens, text);
      if (!fill || !ink) {
        gaps.push({ theme, fill: name, text, ratio: null });
        continue;
      }
      const ratio = Math.round(contrastRatio(fill, ink) * 100) / 100;
      if (contrastRatio(fill, ink) < config.minRatio) gaps.push({ theme, fill: name, text, ratio });
    }
  }
  return gaps;
}

/** The gaps of the project's token file. A missing file has none (like an absent app folder): set CONFIG.tokensPath. */
export function readGaps(root: string, config = CONFIG): Gap[] {
  const path = `${root}/${config.tokensPath}`;
  return existsSync(path) ? judgeContrast(readFileSync(path, 'utf8'), config) : [];
}

export interface KnownEntry {
  theme: string;
  fill: string;
  text: string;
  ratio: number | null;
}

/** The ratchet: a gap not listed (or worse than listed) is new; a listed gap that is gone is stale. */
export function judgeGaps(actual: readonly Gap[], known: readonly KnownEntry[]): { added: string[]; stale: string[] } {
  const key = (e: { theme: string; fill: string; text: string }): string => `${e.theme}|${e.fill}|${e.text}`;
  const listed = new Map(known.map((e) => [key(e), e]));
  const seen = new Set<string>();
  const added: string[] = [];
  const stale: string[] = [];
  const show = (r: number | null): string => (r === null ? 'cannot judge' : String(r));
  for (const g of actual) {
    seen.add(key(g));
    const was = listed.get(key(g));
    const label = `${g.theme}: ${g.text} on ${g.fill} is ${show(g.ratio)}`;
    if (!was) added.push(`${label} (needs 4.5)`);
    else if (g.ratio !== null && (was.ratio === null || g.ratio < was.ratio)) added.push(`${label}, worse than the listed ${show(was.ratio)}`);
  }
  for (const e of known)
    if (!seen.has(key(e))) stale.push(`${e.theme}: ${e.text} on ${e.fill} now passes: remove the entry in contrast.known.json`);
  return { added, stale };
}
