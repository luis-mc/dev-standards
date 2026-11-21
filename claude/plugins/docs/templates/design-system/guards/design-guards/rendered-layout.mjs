#!/usr/bin/env node
/**
 * Guard A (DS234): the rendered-layout guard. Playwright loads each page at 360, 393, 1300 and 1800 px and checks:
 *  1. no element box overlaps a neighbour. The box counts the focus outline, the glow and the box-shadow, and the
 *     check runs once with each focusable field focused;
 *  2. the gap between page sections (`[data-ds-section]`) equals the section token (default `--ds-space-6`).
 * Usage: node rendered-layout.mjs <page.html>... [--widths 360,393,1300,1800] [--section-token --ds-space-6]
 * Set DS_NODE_MODULES to the node_modules folder that has `playwright` when it is not on the module path.
 */
import { args, finish, loadPlaywright, fileUrl } from './_lib.mjs';
import { resolve } from 'node:path';

export const WIDTHS = [360, 393, 1300, 1800];

/** Runs in the page. Returns problems. `cfg.focus` is the index of the focusable to focus (-1 none). */
export const PAGE_SOURCE = `((cfg) => {
  const px = (v) => parseFloat(v) || 0;
  const visible = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\\s+/)[0] : '');
  const shadowReach = (s) => { // largest reach of any box-shadow, per side
    if (!s || s === 'none') return { t: 0, r: 0, b: 0, l: 0 };
    const parts = s.split(/,(?![^(]*\\))/); let t = 0, r = 0, b = 0, l = 0;
    for (const p of parts) {
      if (/inset/.test(p)) continue;
      const nums = (p.replace(/rgba?\\([^)]*\\)|hsla?\\([^)]*\\)|#[0-9a-f]+/gi, '').match(/-?[\\d.]+px|(?<![\\w.])-?0(?![\\w.])/g) || []).map(px);
      const [x = 0, y = 0, blur = 0, spread = 0] = nums; const g = blur + spread;
      t = Math.max(t, g - y); b = Math.max(b, g + y); l = Math.max(l, g - x); r = Math.max(r, g + x);
    }
    return { t, r, b, l };
  };
  const extBox = (e) => { // border box grown by outline and shadow
    const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    const o = s.outlineStyle !== 'none' ? px(s.outlineWidth) + px(s.outlineOffset) : 0;
    const sh = shadowReach(s.boxShadow);
    const g = (a) => Math.max(o, a, 0);
    return { l: r.left - g(sh.l), t: r.top - g(sh.t), r: r.right + g(sh.r), b: r.bottom + g(sh.b) };
  };
  const focusables = [...document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter(visible);
  if (cfg.count) return { count: focusables.length };
  const problems = [];
  const focused = cfg.focus >= 0 ? focusables[cfg.focus] : null;
  if (focused) focused.focus({ focusVisible: true });
  const all = [...document.body.querySelectorAll('*')].filter((e) => visible(e) && !/^(script|style|svg|path|br|option)$/i.test(e.tagName) &&
    (getComputedStyle(e).display !== 'inline' || focusables.includes(e)));
  const related = (a, b) => a.contains(b) || b.contains(a);
  const check = (a) => {
    const A = extBox(a);
    for (const b of all) {
      if (b === a || related(a, b)) continue;
      const B = extBox(b);
      if (A.l < B.r - 0.5 && B.l < A.r - 0.5 && A.t < B.b - 0.5 && B.t < A.b - 0.5) problems.push({ rule: 'overlap', text: label(a) + ' overlaps ' + label(b) + (focused ? ' with ' + label(focused) + ' focused' : '') });
    }
  };
  if (focused) check(focused); else for (const a of all) check(a);
  if (!focused) {
    const probe = document.createElement('i'); probe.style.cssText = 'position:absolute;visibility:hidden;margin-top:var(' + cfg.sectionToken + ')'; document.body.appendChild(probe);
    const want = px(getComputedStyle(probe).marginTop); probe.remove();
    const secs = [...document.querySelectorAll('[data-ds-section]')].filter(visible);
    for (let i = 1; i < secs.length; i++) {
      if (secs[i].parentElement !== secs[i - 1].parentElement) continue;
      const gap = secs[i].getBoundingClientRect().top - secs[i - 1].getBoundingClientRect().bottom;
      if (Math.abs(gap - want) > 0.5) problems.push({ rule: 'section-gap', text: 'gap before section ' + (i + 1) + ' is ' + gap + 'px, the token ' + cfg.sectionToken + ' is ' + want + 'px' });
    }
  }
  return { problems };
})`;

export async function checkRenderedLayout(browser, file, { widths = WIDTHS, sectionToken = '--ds-space-6' } = {}) {
  const out = [];
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.goto(fileUrl(resolve(file)));
    const n = (await page.evaluate(`${PAGE_SOURCE}(${JSON.stringify({ count: true, sectionToken })})`)).count;
    const runs = [-1, ...Array.from({ length: n }, (_, i) => i)];
    const seen = new Set();
    for (const focus of runs) {
      const res = await page.evaluate(`${PAGE_SOURCE}(${JSON.stringify({ focus, sectionToken })})`);
      for (const p of res.problems) { const k = `${width}|${p.text}`; if (!seen.has(k)) { seen.add(k); out.push(`${file} @${width}px: ${p.rule}: ${p.text}`); } }
    }
    await page.close();
  }
  return out;
}

if (import.meta.url === `file://${process.argv[1]}` || process.argv[1]?.endsWith('rendered-layout.mjs')) {
  const { flags, rest } = args();
  if (!rest.length) { console.error('usage: rendered-layout.mjs <page.html>...'); process.exit(2); }
  const widths = flags.widths ? String(flags.widths).split(',').map(Number) : WIDTHS;
  const pw = loadPlaywright(); const browser = await pw.chromium.launch();
  const problems = [];
  for (const f of rest) problems.push(...await checkRenderedLayout(browser, f, { widths, sectionToken: flags['section-token'] || '--ds-space-6' }));
  await browser.close();
  finish('rendered-layout', problems);
}
