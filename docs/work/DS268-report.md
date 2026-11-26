# DS268 report: fold hook messages

Branch: DS268-fold-hook-messages.

## Open question: which component draws a hook message

The types name none. `RenderComponent` has no hook entry. `UserMessage` props are `text`, `origin`, `isExpanded`, `task`, `from`; `origin.kind` has no hook value. `InfoNotice` has `text` and `command`. No render input carries a hook marker. The `MessageDisplay` event is for assistant text only.

Decision: hook `ui.render` on `UserMessage` and `InfoNotice`, skip a composer prompt and an expanded (`ctrl+o`) row, and match the text shape.

## Chord

The engine's ThemePicker context has two actions, both taken (checked in the installed binary). No third `theme:` action exists. The third chord, `ctrl+x h`, uses `settings:sortByTokens`, handled only in the usage settings dialog.

## Unverified

- That hook output arrives as a `UserMessage` or `InfoNotice` row at all. Use `/fold-hooks diag`.
- That `settings:sortByTokens` is accepted as a Button `action` and that the chord reaches the plugin.
- Real look of the line, the band width and the toast, in a live terminal.
- `claude plugin test` cannot load the node:test suites (it refuses `node:test`; true before this task too). The suites ran with `node --test --experimental-strip-types`.
