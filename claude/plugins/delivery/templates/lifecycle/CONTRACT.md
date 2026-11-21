# Updater test interface (DS235c)

A product's updater offers this interface in test builds only. A stack passes the conformance runner
(`scripts/delivery/lifecycle_conformance.py`) by offering it. The interface names no language.

The project's `lifecycle.json` `test_interface` says how to reach it:

```json
{ "test_interface": { "transport": "http", "url": "http://127.0.0.1:7391" } }
{ "test_interface": { "transport": "cli", "command": ["./product-updater", "test"] } }
```

The runner also takes `--url` or `--cmd`, which win over the file.

## Transports

- `http`: each verb is `POST <url>/test/<verb>` with a JSON body (or `{}`) and returns a JSON object.
- `cli`: each verb is `<command...> <verb> '<json body>'` and prints one JSON object on stdout. The product keeps its state between calls (a file or a daemon).

An error returns `{"error": "<text>"}`. The interface must not exist in a release build.

## Verbs

| Verb | Body | Returns |
|---|---|---|
| `reset` | `version`, `paired`, `policy`, `window`, `channel`, `idle`, `now`, `server_url`, `public_key`, `seed` | state |
| `clock.set` | `now` (epoch seconds) | state |
| `clock.advance` | `seconds` | state |
| `server.set` | `url`, `public_key` (hex Ed25519) | state |
| `state` | none | state |
| `check` | none | `{ran: bool, state}`. `ran` is false when unpaired |
| `install` | `actor`, `remote` (bool), `click` (bool) | state |
| `policy.set` | `policy`, `window` (`{"start":"HH:MM","end":"HH:MM"}` UTC or null) | state |
| `idle.set` | `idle` (bool) | state |
| `selftest.set` | `pass` (bool) | state |
| `pair` | `paired` (bool) | state |
| `audit` | none | `{rows: [...]}` |
| `settings` | none | `{policy, window, channel, last_check, last_result}` |

The fake clock is the only clock the updater reads in a test build. `clock.advance` runs every timer
that falls due, in order, each at its own due time, and returns when the updater is stable. Timers are the next check, a retry, and the opening of the install window while the state is `waiting`. `idle.set`, `policy.set` and `pair` re-evaluate the state at once. A remote `install` needs no click: the signed-in owner's request is the consent.

## State object

`state`, `version`, `paired`, `policy`, `window`, `channel`, `idle`, `now`, `next_check_at` (epoch or null),
`retry_at` (epoch or null), `failures` (count for the offered version), `offered` (version or null),
`history` (list of `{from, to, at}` since `reset`).

States: `unpaired`, `up_to_date`, `available`, `review`, `waiting`, `downloading`, `verifying`, `refused`,
`installing`, `testing`, `updated`, `rolling_back`, `rolled_back`, `skipped`.

## Fake server

`GET <server_url>/<channel>/manifest.json` returns `{"manifest": {...}, "signature": "<hex>"}`.
The signature is Ed25519 over the canonical manifest: JSON with sorted keys and separators `,` and `:`.
Manifest keys: `product`, `channel`, `version`, `required` (bool), `expires_at` (epoch), `url`, `sha256`.
`GET <url>` returns the package bytes. A non-200 manifest reply is a failed check.

## Behaviour the runner checks

- LC-3: every state is reached; every move in `history` is in the allowed table below.
- LC-4: a bad signature, a bad hash, an expired manifest and an older version each end in `refused`. The installed version stays. One audit row has `kind` `refused` and `detail` `bad_signature`, `bad_hash`, `expired` or `older_version`.
- LC-5: the first check is 60 to 600 s after `reset`. Then the gap is 6 h +/- 20%. After a failed check the gap is 60 s, 300 s, 1800 s, 7200 s, then 7200 s. A good check resets it.
- LC-6: `automatic_when_idle` installs only when idle, and inside `window` when set. `ask_first` never installs without `install` with `click: true`. A `required` manifest installs under either policy.
- LC-7: after a failed install (self-test fails, rollback) the retry is 3600 s, then 14400 s. The third failure ends in `skipped`; nothing installs again until a newer version is offered.
- LC-25: a remote install writes an audit row with `kind` `install`, `actor`, `remote` true and `result` (`ok` or `rolled_back`).
- LC-26: `settings` has `policy`, `window`, `channel`, `last_check` (epoch) and `last_result` (string).
- LC-28: while unpaired no check runs: no request goes to the server, from a timer or from `check`.

Audit row: `{at, kind, actor, result, detail, remote}`. Kinds: `check`, `install`, `refused`, `rollback`, `skip`.

## Allowed moves

| From | To |
|---|---|
| any | `unpaired` (on unpair) |
| `unpaired` | `up_to_date` |
| `up_to_date` | `up_to_date`, `available`, `refused`, `waiting`, `review`, `downloading` |
| `available` | `review`, `waiting`, `downloading` |
| `review` | `downloading`, `review`, `up_to_date` |
| `waiting` | `downloading`, `waiting` |
| `downloading` | `verifying`, `refused` |
| `verifying` | `installing`, `refused` |
| `installing` | `testing` |
| `testing` | `updated`, `rolling_back` |
| `updated` | `up_to_date`, `available`, `refused`, `waiting`, `review`, `downloading` |
| `rolling_back` | `rolled_back` |
| `rolled_back` | `waiting`, `downloading`, `skipped`, `available`, `rolled_back`, `up_to_date` |
| `refused` | `refused`, `up_to_date`, `available`, `waiting`, `review`, `downloading` |
| `skipped` | `skipped`, `up_to_date`, `available`, `waiting`, `review`, `downloading` |

A move to the same state is allowed where listed. `available` is a pass-through: a state is recorded for it
before the policy decides `review`, `waiting` or `downloading`.
