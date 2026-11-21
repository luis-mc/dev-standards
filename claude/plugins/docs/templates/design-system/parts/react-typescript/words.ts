/**
 * Words for the lifecycle parts. The words table is `templates/design-system/lifecycle/words.json`
 * (written by DS235a; a project adds its own in `lifecycle.json`). A part never holds a word of its own:
 * it calls `t(key)`. The defaults below are the words of the lifecycle contract, used only until a table is loaded.
 */
export type Words = Record<string, string>;

const DEFAULTS: Words = {
  'banner.ready': 'Update ready',
  'banner.running': 'Updating',
  'banner.done': 'Updated',
  'banner.failed': 'Update failed',
  'action.update_now': 'Update now',
  'action.later': 'Later',
  'action.retry': 'Try again',
  'action.close': 'Close',
  'action.cancel': 'Cancel',
  'policy.automatic_when_idle': 'Automatic when idle',
  'policy.ask_first': 'Ask first',
  'updates.title': 'Updates',
  'updates.policy': 'When to update',
  'updates.window': 'Only between',
  'updates.channel': 'Channel',
  'updates.wait_running': 'Wait for running work',
  'updates.last_check': 'Last check',
  'updates.locked_by': 'Set by',
  'history.title': 'Update history',
  'history.empty': 'No updates yet',
  'remote.title': 'Update this machine',
  'remote.start': 'Start update',
  'remove.title': 'Remove',
  'remove.keep': 'Keep my data',
  'remove.purge': 'Delete my data too',
  'remove.confirm': 'Remove',
  'remove.cancel': 'Cancel',
  'remove.choose': 'Choose what happens to your data',
  'fleet.up_to_date': 'Up to date',
  'fleet.waiting': 'Waiting',
  'fleet.needs_you': 'Needs you',
};

let table: Words = { ...DEFAULTS };

/** Load a words table (the parsed `words.json`: flat `{key: text}` or `{ words: {...} }`). Missing keys keep the default. */
export function loadWords(json: unknown): void {
  const src = (json && typeof json === 'object' && 'words' in (json as object)
    ? (json as { words: unknown }).words
    : json) as Record<string, unknown> | undefined;
  table = { ...DEFAULTS };
  for (const [k, v] of Object.entries(src ?? {})) if (typeof v === 'string') table[k] = v;
}

export function t(key: string): string {
  return table[key] ?? key;
}
