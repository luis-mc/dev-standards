// The state luismc-transcript-folds keeps for the session ($.state), declared
// as a contract. The two switches start folded in every session; a toggle
// lasts for that session only.

export type TranscriptFoldsTally = {
  /** Paths touched this session, each once. */
  files: string[]
  /** Files a shell call changed whose paths were not reported. */
  extra: number
  added: number
  removed: number
}

/** What a finished call changed, by tool_use_id. */
export type TranscriptFoldsChange = {
  kind: 'edit' | 'new' | 'notebook' | 'bash'
  path: string
  paths: string[]
  files: number
  added: number
  removed: number
  firstLine: number
  cell: string
}

/** What a finished shell call came to, by tool_use_id. */
export type TranscriptFoldsOutcome = {
  kind: 'output' | 'empty' | 'error'
  text: string
}

declare module 'claude-code' {
  interface PluginState {
    'luismc-transcript-folds': {
      diffsFolded: boolean
      commandsFolded: boolean
      tally: TranscriptFoldsTally
      /** The project root at session start; paths are shown relative to it. */
      root: string
      counts: StateFamily<TranscriptFoldsChange>
      outcomes: StateFamily<TranscriptFoldsOutcome>
    }
  }
}
