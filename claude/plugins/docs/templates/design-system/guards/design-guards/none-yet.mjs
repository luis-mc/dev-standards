#!/usr/bin/env node
/**
 * Guard D (DS234): a rule whose guard is `none yet` gets a date and fails after a set number of days.
 * Write `none yet (2026-11-21)` in the Guard column. A bare `none yet` fails. The limit is `none_yet_days` in the config
 * (default 30). Usage: node none-yet.mjs <ux-rules.md> [--config tools/design-guards.json]
 */
import { args, read, finish, today, daysBetween } from './_lib.mjs';
import { existsSync } from 'node:fs';

export function checkNoneYet(text, now, days) {
  const out = [];
  for (const line of text.split('\n')) {
    const cells = line.split('|').map((c) => c.trim());
    if (cells.length < 4 || !/^[A-Z]+-\d+[a-z]?$/.test(cells[1])) continue;
    const guard = cells[cells.length - 2];
    if (!/none yet/i.test(guard)) continue;
    const d = guard.match(/(\d{4}-\d{2}-\d{2})/);
    if (!d) { out.push(`${cells[1]}: "none yet" has no date; write none yet (YYYY-MM-DD)`); continue; }
    const age = daysBetween(d[1], now);
    if (age > days) out.push(`${cells[1]}: "none yet" is ${age} days old, the limit is ${days}; add the guard`);
  }
  return out;
}

if (process.argv[1]?.endsWith('none-yet.mjs')) {
  const { flags, rest } = args();
  let days = 30;
  const cfg = flags.config || 'tools/design-guards.json';
  if (existsSync(cfg)) days = JSON.parse(read(cfg)).none_yet_days ?? 30;
  finish('none-yet', checkNoneYet(read(rest[0]), today(), days).map((p) => `${rest[0]}: ${p}`));
}
