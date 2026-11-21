#!/usr/bin/env node
/**
 * Build the fixture apps: one HTML page per part, rendering all its states with the shared CSS and the fixture tokens.
 * Usage: node build-fixtures.mjs <out-dir>
 * Needs `react`, `react-dom` and `esbuild`; set DS_NODE_MODULES to the node_modules folder that has them.
 * The words are read from ../../lifecycle/words.json when it exists (DS235a); the defaults in words.ts apply otherwise.
 */
import { createRequire } from 'node:module';
import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = process.argv[2];
if (!out) { console.error('usage: build-fixtures.mjs <out-dir>'); process.exit(2); }
const nm = process.env.DS_NODE_MODULES;
const req = createRequire(join(nm || here, 'x.js'));
const esbuild = req('esbuild');
mkdirSync(out, { recursive: true });
const css = readFileSync(join(here, 'tokens.fixture.css'), 'utf8') + readFileSync(join(here, 'lifecycle-parts.css'), 'utf8');
const wordsPath = join(here, '..', '..', 'lifecycle', 'words.json');
const words = existsSync(wordsPath) ? readFileSync(wordsPath, 'utf8') : 'null';
const names = readdirSync(join(here, 'fixtures')).filter((f) => f.endsWith('.fixture.tsx')).map((f) => f.replace('.fixture.tsx', ''));
for (const name of names) {
  const entry = `import { loadWords } from ${JSON.stringify(join(here, 'words.ts'))};\nloadWords(${words});\nimport ${JSON.stringify(join(here, 'fixtures', name + '.fixture.tsx'))};`;
  const r = await esbuild.build({
    stdin: { contents: entry, resolveDir: here, loader: 'tsx' },
    bundle: true, write: false, format: 'iife', jsx: 'automatic', minify: false,
    nodePaths: nm ? [nm] : [], define: { 'process.env.NODE_ENV': '"production"' },
  });
  const js = r.outputFiles[0].text.replace(/<\/script/g, '<\\/script');
  writeFileSync(join(out, name + '.html'),
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${name}</title><style>${css}</style></head><body><div id="root"></div><script>${js}</script></body></html>`);
}
console.log(names.join('\n'));
