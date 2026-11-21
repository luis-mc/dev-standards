#!/usr/bin/env node
/**
 * Guard E (DS234): a feature spec that cites a UX rule must name the test that proves it. A line that holds the rule ID
 * (UX-n or CORE-n) must also hold a backticked path to a test or spec file that exists, or the spec must hold a
 * `Proof: UX-n ... \`path\`` line. Usage: node citation-test.mjs <repo-root> [--specs docs/features]
 */
import { args, walk, read, rel, finish } from './_lib.mjs';
import { join, dirname } from 'node:path';
import { existsSync } from 'node:fs';

const ID = /\b(?:UX|CORE)-\d+[a-z]?\b/g;
const PATH = /`([^`\s]+\.(?:py|ts|tsx|mjs|js|rs|go|sh))`/g;
const isTest = (p) => /test|spec/i.test(p.split('/').pop());

export function citationProblems(text, exists) {
  const named = new Map(); // id -> true when a line with the id names an existing test
  const cited = new Set();
  const lines = text.split('\n');
  const proofs = lines.filter((l) => /^\s*[-*]?\s*(Proof|Test|Tests):/i.test(l));
  lines.forEach((l) => {
    const ids = l.match(ID) || [];
    const paths = [...l.matchAll(PATH)].map((m) => m[1]).filter(isTest);
    const ok = paths.some(exists);
    for (const id of ids) { cited.add(id); if (ok) named.set(id, true); }
  });
  for (const l of proofs) { const paths = [...l.matchAll(PATH)].map((m) => m[1]).filter(isTest); if (paths.some(exists)) for (const id of l.match(ID) || []) named.set(id, true); }
  return [...cited].filter((id) => !named.get(id)).map((id) => `cites ${id} but names no test that proves it (a backticked test path that exists)`);
}

if (process.argv[1]?.endsWith('citation-test.mjs')) {
  const { flags, rest } = args();
  const root = rest[0] || '.';
  const problems = [];
  for (const f of walk(join(root, flags.specs || 'docs/features'), /^spec\.md$/)) {
    for (const p of citationProblems(read(f), (p) => existsSync(join(root, p)) || existsSync(join(dirname(f), p)))) problems.push(`${rel(root, f)}: ${p}`);
  }
  finish('citation-test', problems);
}
