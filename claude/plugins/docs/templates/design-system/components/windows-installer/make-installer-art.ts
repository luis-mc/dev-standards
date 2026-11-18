// Build-time installer artwork. Reads the design-system token file and writes the
// two WixUI bitmaps: banner 493x58 and dialog side 493x312 (24-bit BMP).
// Every colour comes from the tokens. Nothing is hand-picked here.
//
// Usage: node --experimental-strip-types make-installer-art.ts <tokens-file> <out-dir> [variant]
// The variant is a token-name prefix for a second product, for example "bw"
// reads --ds-bw-color-primary instead of --ds-color-primary.
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

type Rgb = [number, number, number];

// Reads `--name: value` pairs; the first (light) value of a name wins.
export function readTokens(text: string): Map<string, Rgb> {
  const out = new Map<string, Rgb>();
  const re = /(--[a-z0-9-]+)\s*[:|`\s]+\s*`?#([0-9a-fA-F]{6})\b/g;
  for (const m of text.matchAll(re)) {
    const name = m[1] as string;
    const hex = m[2] as string;
    if (out.has(name)) continue;
    const n = parseInt(hex, 16);
    out.set(name, [(n >> 16) & 255, (n >> 8) & 255, n & 255]);
  }
  return out;
}

export function pick(tokens: Map<string, Rgb>, variant: string, role: string): Rgb {
  const name = variant ? `--ds-${variant}-color-${role}` : `--ds-color-${role}`;
  const v = tokens.get(name);
  if (!v) throw new Error(`token ${name} not found`);
  return v;
}

// A 24-bit bottom-up BMP. Rows are padded to four bytes.
export function bmp(w: number, h: number, paint: (x: number, y: number) => Rgb): Buffer {
  const row = Math.ceil((w * 3) / 4) * 4;
  const size = 54 + row * h;
  const b = Buffer.alloc(size);
  b.write("BM", 0, "latin1");
  b.writeUInt32LE(size, 2);
  b.writeUInt32LE(54, 10);
  b.writeUInt32LE(40, 14);
  b.writeInt32LE(w, 18);
  b.writeInt32LE(h, 22);
  b.writeUInt16LE(1, 26);
  b.writeUInt16LE(24, 28);
  b.writeUInt32LE(row * h, 34);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const [r, g, bl] = paint(x, y);
      const o = 54 + (h - 1 - y) * row + x * 3;
      b[o] = bl;
      b[o + 1] = g;
      b[o + 2] = r;
    }
  }
  return b;
}

export function build(tokensText: string, variant = ""): { banner: Buffer; dialog: Buffer } {
  const t = readTokens(tokensText);
  const surface = pick(t, variant, "surface");
  const primary = pick(t, variant, "primary");
  const divider = pick(t, variant, "divider");
  // Banner: surface with a primary band on the left edge and a divider line below.
  const banner = bmp(493, 58, (x, y) => (y === 57 ? divider : x < 8 ? primary : surface));
  // Dialog side: primary panel at the left (the WixUI text sits on the right part), surface elsewhere.
  const dialog = bmp(493, 312, (x) => (x < 164 ? primary : surface));
  return { banner, dialog };
}

const [, , tokensFile, outDir, variant] = process.argv;
if (tokensFile && outDir) {
  const { banner, dialog } = build(readFileSync(tokensFile, "utf8"), variant ?? "");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(join(outDir, "banner.bmp"), banner);
  writeFileSync(join(outDir, "dialog.bmp"), dialog);
}
