# DS72 report: Stop hook loop

Status: in progress (branch DS72-stop-hook-loop).

Cause: the Stop hook (DL-14, DL-18) named project scripts that never write the ledger fields it reads, and the
existing per-session ceiling resets whenever the set of findings changes, so the session was blocked every turn.

Plan: (1) `smoke` / `cleaned` ledger commands, (2) messages name the recording command, (3) `stop_repeat_limit`,
(4) tests, (5) docs and change note.
