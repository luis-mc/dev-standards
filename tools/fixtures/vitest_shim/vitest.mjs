// A tiny stand-in for `vitest` so the shipped guard-test templates can be self-tested here with plain Node
// (no install, no network). It supports only what the templates use: describe, it, expect and a few matchers.
import assert from 'node:assert/strict';

const queue = [];
let prefix = [];

export function describe(name, fn) {
  prefix.push(name);
  try {
    fn();
  } finally {
    prefix.pop();
  }
}
export function it(name, fn) {
  queue.push({ name: [...prefix, name].join(' > '), fn });
}
export const test = it;

export function expect(actual, message) {
  const m = (cond, text) => assert.ok(cond, (message ? message + ': ' : '') + text);
  const show = (v) => JSON.stringify(v);
  return {
    toEqual: (e) => {
      try {
        assert.deepEqual(actual, e);
      } catch {
        m(false, `expected ${show(e)} but got ${show(actual)}`);
      }
    },
    toBe: (e) => m(Object.is(actual, e), `expected ${show(e)} but got ${show(actual)}`),
    toContain: (e) => m(actual.includes(e), `expected ${show(actual)} to contain ${show(e)}`),
    toHaveLength: (n) => m(actual.length === n, `expected length ${n} but got ${actual.length}`),
    toMatch: (re) => m(re.test(actual), `expected ${show(actual)} to match ${re}`),
    toBeGreaterThan: (n) => m(actual > n, `expected ${actual} > ${n}`),
  };
}

export async function runAll() {
  let passed = 0;
  let failed = 0;
  for (const t of queue) {
    try {
      await t.fn();
      passed++;
    } catch (e) {
      failed++;
      console.log('FAIL ' + t.name + ': ' + (e && e.message ? e.message : e));
    }
  }
  console.log(`${passed} passed, ${failed} failed`);
  return failed === 0;
}
