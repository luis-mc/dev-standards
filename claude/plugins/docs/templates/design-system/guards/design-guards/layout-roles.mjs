#!/usr/bin/env node
/**
 * Guard C (DS234): one component per layout role. The design system names the component of each role (page sections,
 * card grid, form) in `layout-roles.json` and in `components.md`. A page whose top level uses a plain gap instead fails.
 * layout-roles.json: { "roles": { "page-sections": "PageSections", "card-grid": "CardGrid", "form": "FormStack" }, "pages": ["src/pages"] }
 * A page file fails when: a role component is not named in components.md; it sets `gap` itself (CSS, inline style or a
 * gap utility class); or it has two or more `<section>` / `<form>` and does not use the role component.
 * Usage: node layout-roles.mjs <root> [--config layout-roles.json] [--components docs/design-system/next-version/components.md]
 */
import { args, walk, read, rel, finish } from './_lib.mjs';
import { join } from 'node:path';
import { existsSync } from 'node:fs';

export function checkPage(text, roles) {
  const out = [];
  if (/(?:^|[\s{;"'`])(?:row-|column-)?gap\s*:|(?:row|column)?[gG]ap\s*:\s*['"\d]|className=["'][^"']*\bgap-\d/.test(text)) out.push('sets a plain gap at the top level; use the layout role component');
  const uses = (name) => new RegExp(`<${name}\\b|data-ds-component=["']${name}`).test(text);
  const sections = (text.match(/<section\b/g) || []).length;
  if (sections >= 2 && !uses(roles['page-sections'])) out.push(`has ${sections} sections without <${roles['page-sections']}>`);
  const forms = (text.match(/<form\b/g) || []).length;
  if (forms >= 1 && /<(input|select|textarea)\b/.test(text) && (text.match(/<(input|select|textarea)\b/g) || []).length >= 2 && !uses(roles.form)) out.push(`has a form of fields without <${roles.form}>`);
  return out;
}

if (process.argv[1]?.endsWith('layout-roles.mjs')) {
  const { flags, rest } = args();
  const root = rest[0] || '.';
  const cfgPath = join(root, flags.config || 'layout-roles.json');
  const problems = [];
  if (!existsSync(cfgPath)) { finish('layout-roles', [`${flags.config || 'layout-roles.json'} is missing: name one component per layout role`]); }
  const cfg = JSON.parse(read(cfgPath));
  const roles = cfg.roles || {};
  for (const role of ['page-sections', 'card-grid', 'form']) if (!roles[role]) problems.push(`no component named for the role ${role}`);
  const comp = join(root, flags.components || 'docs/design-system/next-version/components.md');
  const compText = existsSync(comp) ? read(comp) : '';
  for (const [role, name] of Object.entries(roles)) if (!compText.includes(name)) problems.push(`components.md does not name ${name} (role ${role})`);
  for (const dir of cfg.pages || ['src/pages']) {
    for (const f of walk(join(root, dir), /\.(tsx|jsx|html|vue|svelte)$/)) for (const p of checkPage(read(f), roles)) problems.push(`${rel(root, f)}: ${p}`);
  }
  finish('layout-roles', problems);
}
