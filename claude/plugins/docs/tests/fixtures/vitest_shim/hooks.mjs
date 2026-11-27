// Module hook: the bare specifier `vitest` resolves to the shim next to this file.
export async function resolve(specifier, context, nextResolve) {
  if (specifier === 'vitest') return { url: new URL('./vitest.mjs', import.meta.url).href, shortCircuit: true };
  return nextResolve(specifier, context);
}
