## Context-efficiency behavior

After a `/compact` or any context reset, trust the compact summary — don't
re-read files, configs, or SKILL.md content just to confirm understanding
before answering a question. Re-read a specific file only right before
*acting* on it (editing it, quoting exact current content, or checking
whether a specific claim is stale). Verifying the whole state eagerly after
a reset burns tens of thousands of tokens for no functional gain.
