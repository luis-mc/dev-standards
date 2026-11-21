#!/usr/bin/env node
/**
 * Guard B (DS234): no fixed px or rem in margin, padding or gap outside the token files. Same idea as the raw-colour check.
 * A value must be a token: `var(--ds-space-4)`, or `calc()` over tokens. `0`, `auto`, `inherit` and percentages are fine.
 * Token files: names matching `tokens` (config `token_file_pattern`). Scans .css, .tsx, .ts, .jsx, .html, .rs-free.
 * Usage: node spacing-tokens.mjs <dir> [--tokens <regex>]
 */
import { args, walk, read, rel, finish } from './_lib.mjs';

const PROP = /(?:^|[;{\s"'`])((?:margin|padding)(?:-(?:top|right|bottom|left|inline|block|inline-start|inline-end|block-start|block-end))?|gap|row-gap|column-gap|grid-gap|inset|marginTop|marginBottom|marginLeft|marginRight|paddingTop|paddingBottom|paddingLeft|paddingRight|rowGap|columnGap)\s*:\s*([^;}\n]*)/g;
const RAW = /(?<![\w-])-?\d*\.?\d+(px|rem|em|pt)\b/;

export function scanSpacing(text) {
  const hits = [];
  const clean = text.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
  for (const m of clean.matchAll(PROP)) {
    const value = m[2].replace(/var\([^)]*\)/g, 'VAR');
    const camel = /[A-Z]/.test(m[1]);
    // a unit literal, or (in a JS style object) a bare non-zero number such as `marginTop: 12`
    if (RAW.test(value) || (camel && /^\s*-?\d*\.?\d*[1-9]\d*\s*[,}]/.test(m[2] + '}'))) {
      hits.push({ line: clean.slice(0, m.index).split('\n').length, prop: m[1], value: m[2].trim() });
    }
  }
  return hits;
}

if (process.argv[1]?.endsWith('spacing-tokens.mjs')) {
  const { flags, rest } = args();
  const root = rest[0] || '.';
  const tokenFile = new RegExp(flags.tokens || 'tokens', 'i');
  const problems = [];
  for (const f of walk(root, /\.(css|scss|tsx|ts|jsx|js|html|vue|svelte)$/)) {
    if (tokenFile.test(f.split('/').pop())) continue;
    for (const h of scanSpacing(read(f))) problems.push(`${rel(root, f)}:${h.line}: ${h.prop}: ${h.value} (use a --ds-space token)`);
  }
  finish('spacing-tokens', problems);
}
