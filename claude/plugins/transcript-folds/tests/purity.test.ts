import test from 'node:test'
import assert from 'node:assert/strict'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'

// hooks/fold/*.ts is the decision logic; the engine's environment has no Node,
// so these files must stand on their own: no engine import, no JSX, no Node API.
const dir = join(import.meta.dirname, '..', 'hooks', 'fold')
const files = readdirSync(dir).filter(name => name.endsWith('.ts'))

test('there are fold modules to check', () => {
  assert.ok(files.length >= 6)
})

for (const name of files) {
  const source = readFileSync(join(dir, name), 'utf8')
  // Comments say what the file is; only code is judged.
  const code = source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '')

  test(`${name}: imports only sibling .ts files`, () => {
    const imports = [...code.matchAll(/^\s*import\s[^'"]*['"]([^'"]+)['"]/gm)].map(m => m[1] as string)
    for (const spec of imports) {
      assert.match(spec, /^\.\/[a-z_]+\.ts$/, `${name} imports ${spec}`)
    }
    assert.ok(!/\bimport\s*\(/.test(code), `${name} holds an import()`)
    assert.ok(!/\brequire\s*\(/.test(code), `${name} holds a require()`)
  })

  test(`${name}: no JSX, no Node API`, () => {
    assert.ok(!/<\/[A-Z][A-Za-z]*>|(?<![A-Za-z0-9_])<[A-Z][A-Za-z]*[\s/>]/.test(code), `${name} looks like JSX`)
    assert.ok(!/\bprocess\.|\bBuffer\b|node:/.test(code), `${name} uses a Node API`)
  })
}
