#!/usr/bin/env node
/**
 * LC-23: lifecycle parts use the shared template and tokens only. In a project's parts folder:
 *  - every part (*.tsx with `data-ds-part`) uses the shared stylesheet classes (`ds-part`) and holds no `style=` colour,
 *    size or font and no raw colour;
 *  - the shared stylesheet holds no raw colour, no px, rem or em literal and no font name outside `var(--ds-*)`.
 * Usage: node parts-tokens.mjs <parts-dir> [--css lifecycle-parts.css]
 */
import { args, walk, read, rel, finish } from '../design-guards/_lib.mjs';

const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(/;
const LENGTH = /(?<![\w-])-?\d*\.?\d+(?:px|rem|em|pt|vh|vw)\b/;
const FONT = /font-family\s*:\s*(?!var\()/;

export function cssProblems(text) {
  const out = [];
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
  clean.split('\n').forEach((l, i) => {
    if (/^\s*@media/.test(l)) return;
    const decl = l.replace(/var\([^)]*\)/g, 'VAR');
    if (COLOUR.test(decl)) out.push(`line ${i + 1}: raw colour`);
    if (LENGTH.test(decl)) out.push(`line ${i + 1}: raw size (${decl.match(LENGTH)[0]})`);
    if (FONT.test(l)) out.push(`line ${i + 1}: font family not from a token`);
  });
  return out;
}

export function partProblems(text) {
  const out = [];
  if (!/data-ds-part=/.test(text)) return out;
  if (!/(?<![\w-])ds-part(?![\w-])/.test(text)) out.push('does not use the shared part class ds-part');
  if (/style=\{\{/.test(text) || /\bstyle="/.test(text)) out.push('inline style; use the shared stylesheet');
  if (COLOUR.test(text)) out.push('raw colour');
  if (/\bfont-family\b|fontFamily/.test(text)) out.push('font set in the part');
  return out;
}

if (process.argv[1]?.endsWith('parts-tokens.mjs')) {
  const { flags, rest } = args(); const root = rest[0] || '.';
  const problems = [];
  for (const f of walk(root, /\.tsx$/)) problems.push(...partProblems(read(f)).map((p) => `${rel(root, f)}: ${p}`));
  for (const f of walk(root, new RegExp(String(flags.css || 'lifecycle-parts.css').replace(/\./g, '\\.') + '$'))) problems.push(...cssProblems(read(f)).map((p) => `${rel(root, f)}: ${p}`));
  finish('parts-tokens', problems);
}
