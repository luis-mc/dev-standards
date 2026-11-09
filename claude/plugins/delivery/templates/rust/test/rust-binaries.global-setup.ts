// DS208: vitest globalSetup. Builds the Rust crates a TypeScript test spawns, once per run.
//
// Use: set RUST_TEST_CRATES=crate-a,crate-b and add this file to vitest:
//   globalSetup: ['test/rust-binaries.global-setup.ts']
// Each test reads the exe path from process.env.<CRATE>_BIN (upper case, '-' becomes '_').
// Example: crate `my-tool` gives MY_TOOL_BIN. CARGO_TARGET_DIR is honoured.
import { spawnSync } from 'node:child_process';
import { join, resolve } from 'node:path';

export default function setup(): void {
  const crates = (process.env.RUST_TEST_CRATES ?? '')
    .split(',')
    .map((c) => c.trim())
    .filter((c) => c.length > 0);
  if (crates.length === 0) return;

  const targetDir = resolve(process.env.CARGO_TARGET_DIR ?? 'target');
  const ext = process.platform === 'win32' ? '.exe' : '';

  for (const crate of crates) {
    const res = spawnSync('cargo', ['build', '--locked', '-p', crate], {
      stdio: 'inherit',
      shell: process.platform === 'win32',
    });
    if (res.error) {
      throw new Error(
        `rust-binaries: cannot run cargo (${res.error.message}). ` +
          'Install the Rust toolchain and put cargo on PATH, or unset RUST_TEST_CRATES.',
      );
    }
    if (res.status !== 0) {
      throw new Error(`rust-binaries: cargo build --locked -p ${crate} failed (exit ${res.status}).`);
    }
    process.env[`${crate.toUpperCase().replace(/-/g, '_')}_BIN`] = join(targetDir, 'debug', crate + ext);
  }
}
