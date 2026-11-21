#!/usr/bin/env node
/**
 * LC-24 and LC-30: every update state and every question window renders without clipping or overlap at 100%, 150% and 200%
 * text scale and at 360 px. Each page of a fixture app lists its states (one section per state). The guard loads each page at
 * 360 px for each scale and fails on: horizontal overflow, a box cut off by its container (overflow hidden or clip), a box
 * outside the viewport width, a button whose label is cut off, and any overlap (the same check as the rendered-layout guard,
 * with each focusable focused). Usage: node states-render.mjs <page.html>... [--scales 1,1.5,2] [--width 360]
 */
import { args, finish, loadPlaywright, fileUrl } from '../design-guards/_lib.mjs';
import { PAGE_SOURCE } from '../design-guards/rendered-layout.mjs';
import { resolve } from 'node:path';

const CLIP = `(() => {
  const out = []; const vw = document.documentElement.clientWidth;
  const label = (e) => e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\\s+/)[0] : '');
  if (document.documentElement.scrollWidth > vw + 1) out.push('horizontal overflow (' + document.documentElement.scrollWidth + ' > ' + vw + ')');
  for (const e of document.body.querySelectorAll('*')) {
    const s = getComputedStyle(e); const r = e.getBoundingClientRect();
    if (r.width === 0 || r.height === 0 || s.display === 'none') continue;
    if (r.right > vw + 1 || r.left < -1) out.push(label(e) + ' is outside the ' + vw + ' px width');
    const clips = /hidden|clip|auto|scroll/.test(s.overflowX + s.overflowY);
    if ((clips || e.tagName === 'BUTTON') && (e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)) out.push(label(e) + ' is clipped or scrolls');
  }
  return out;
})()`;

export async function checkStates(browser, file, { scales = [1, 1.5, 2], width = 360 } = {}) {
  const out = [];
  for (const scale of scales) {
    const page = await browser.newPage({ viewport: { width, height: 800 } });
    await page.goto(fileUrl(resolve(file)));
    await page.addStyleTag({ content: `html { font-size: ${scale * 100}% !important; }` });
    for (const p of await page.evaluate(CLIP)) out.push(`${file} @${scale * 100}%: ${p}`);
    const n = (await page.evaluate(`${PAGE_SOURCE}(${JSON.stringify({ count: true, sectionToken: '--ds-space-6' })})`)).count;
    const seen = new Set();
    for (const focus of [-1, ...Array.from({ length: n }, (_, i) => i)]) {
      const res = await page.evaluate(`${PAGE_SOURCE}(${JSON.stringify({ focus, sectionToken: '--ds-space-6' })})`);
      for (const p of res.problems) if (!seen.has(p.text)) { seen.add(p.text); out.push(`${file} @${scale * 100}%: ${p.rule}: ${p.text}`); }
    }
    await page.close();
  }
  return out;
}

if (process.argv[1]?.endsWith('states-render.mjs')) {
  const { flags, rest } = args();
  if (!rest.length) { console.error('usage: states-render.mjs <page.html>...'); process.exit(2); }
  const scales = flags.scales ? String(flags.scales).split(',').map(Number) : [1, 1.5, 2];
  const pw = loadPlaywright(); const browser = await pw.chromium.launch();
  const problems = [];
  for (const f of rest) problems.push(...await checkStates(browser, f, { scales, width: Number(flags.width || 360) }));
  await browser.close();
  finish('states-render', problems);
}
