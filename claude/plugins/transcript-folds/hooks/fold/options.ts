// The plugin's three settings and a path shown relative to the project root.
// Pure: no engine import, no Node API.

export type FoldOptions = {
  foldAbove: number
  marker: string
  compactCounts: boolean
}

export const DEFAULT_MARKER = '»'

export const DEFAULT_OPTIONS: FoldOptions = {
  foldAbove: 5,
  marker: DEFAULT_MARKER,
  compactCounts: false,
}

/**
 * The settings as the engine hands them over (any value may be missing or of
 * the wrong type) made safe: a bad number gives the default, a fraction is
 * rounded down, a negative is 0; the marker may be empty.
 */
export function normalizeOptions(raw: Readonly<Record<string, unknown>> | undefined): FoldOptions {
  const src = raw ?? {}
  const n = src.foldAbove
  const foldAbove =
    typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.floor(n)) : DEFAULT_OPTIONS.foldAbove
  const marker = typeof src.marker === 'string' ? src.marker : DEFAULT_OPTIONS.marker
  const compactCounts = typeof src.compactCounts === 'boolean' ? src.compactCounts : DEFAULT_OPTIONS.compactCounts
  return { foldAbove, marker, compactCounts }
}

/** The marker followed by a space, or nothing when the marker is empty. */
export function markerPrefix(marker: string): string {
  const m = marker.trim()
  return m === '' ? '' : `${m} `
}

function slashes(path: string): string {
  return path.replace(/\\/g, '/')
}

function isWindowsPath(path: string): boolean {
  return /^[A-Za-z]:\//.test(path)
}

/**
 * A path relative to the project root when it lies under it, else the path
 * as it came (backslashes kept as given). Drive letters compare without case.
 * The root itself shows as ".".
 */
export function relativePath(root: string, path: string): string {
  if (root === '') return path
  const r = slashes(root).replace(/\/+$/, '')
  const p = slashes(path)
  if (r === '') return path
  const fold = isWindowsPath(r) || isWindowsPath(p)
  const a = fold ? r.toLowerCase() : r
  const b = fold ? p.toLowerCase() : p
  if (b === a) return '.'
  if (b.startsWith(a + '/')) return p.slice(r.length + 1)
  return path
}
