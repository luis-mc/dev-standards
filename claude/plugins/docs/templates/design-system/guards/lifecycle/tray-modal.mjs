#!/usr/bin/env node
/**
 * LC-22 and the static half of LC-30. Scans native (Rust) code of the tray and the question window.
 *  - Tray files (names with `tray`): no modal, no message box, no Yes/No dialog; a notice window of 24 hours
 *    (`NOTICE_WINDOW_SECS` equal to 86400, written 24 * 60 * 60 or 86400) so one notice per event per 24 h.
 *  - Window files (names with `window`): no fixed size, no literal width and height passed to a size call; the
 *    window is sized from its content.
 * Usage: node tray-modal.mjs <dir>
 */
import { args, walk, read, rel, finish } from '../design-guards/_lib.mjs';

const MODAL = /\b(MessageBox\w*|message_box|\.modal\s*\(|set_modal|run_dialog|DialogResult|YesNo|yes_no|MB_YESNO|NSAlert|\.confirm\s*\(|AskDialog|show_dialog|rfd::)/;
const FIXED = /\b(with_inner_size|set_inner_size|set_min_inner_size|set_max_inner_size|default_size|set_default_size|request_inner_size|with_min_inner_size|set_size_request|ClientSize|SetWindowPos)\s*\(?[^;\n]*\b\d{2,}\b|\b(width|height)\s*[:=]\s*\d{2,}\b|resizable\(\s*false\s*\)/;

export function trayProblems(text) {
  const out = [];
  const code = text.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');
  const m = code.match(MODAL);
  if (m) out.push(`modal or Yes/No dialog from the tray (${m[0].trim()}); the tray only notifies (LC-22)`);
  const w = code.match(/NOTICE_WINDOW_SECS\s*:\s*u64\s*=\s*([^;]+);/);
  if (!w) out.push('no NOTICE_WINDOW_SECS: one notice per event per 24 h (LC-22)');
  else if (!/^(24\s*\*\s*60\s*\*\s*60|86_?400|60\s*\*\s*60\s*\*\s*24)$/.test(w[1].trim())) out.push(`NOTICE_WINDOW_SECS is ${w[1].trim()}, not 24 hours (LC-22)`);
  return out;
}

export function windowProblems(text) {
  const code = text.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/#\[cfg\(test\)\][\s\S]*$/, '');
  const m = code.match(FIXED);
  return m ? [`fixed window size (${m[0].trim().slice(0, 60)}); size it from its content (LC-30)`] : [];
}

if (process.argv[1]?.endsWith('tray-modal.mjs')) {
  const { rest } = args(); const root = rest[0] || '.';
  const problems = [];
  for (const f of walk(root, /\.rs$/)) {
    const name = f.split('/').pop();
    if (/tray/i.test(name)) problems.push(...trayProblems(read(f)).map((p) => `${rel(root, f)}: ${p}`));
    if (/window/i.test(name)) problems.push(...windowProblems(read(f)).map((p) => `${rel(root, f)}: ${p}`));
  }
  finish('tray-modal', problems);
}
