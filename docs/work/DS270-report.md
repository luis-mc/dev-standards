# DS270 report: what is enforced and what is advice

Read in `hook_pre_tool.py` (`check_launch`) on branch `DS269-affected-targets`.

## Before this branch

| Rule | State | How |
|---|---|---|
| D4 cloud first | Enforced | A local `Agent` launch is denied unless its prompt has a `PC-bound:` line (any text) or the cloud cap is full. |
| DL-39 PC-bound only | Half enforced | The line must exist. Its text was never read. |
| DL-38 caps | Enforced | Total, cloud and local caps and free memory deny the launch. |
| DL-40 one agent per area | Advice only | The spec said the hook injects the open tasks as context. No code did that (no `additionalContext` in the hook). |
| DL-41 file ownership | Enforced | A launch whose `owns` overlaps a running agent's `owns` is denied. |

## Built here

- DL-126: a launch that names a task (a `task:` line in the delivery block, else the task ID read from the prompt as in DL-123) is denied once when another To do or Waiting task of the same `app` (or `area`) is in the project record. The denial lists those tasks. A second identical launch passes. The memory is `.delivery/state/dl40-denied.json`. `checks_off` `DL-40` turns it off.
- DL-127: a `PC-bound:` reason with no PC-bound step word (build, test, install, runner, browser, hardware and similar) prints a warning and lets the launch through. `checks_off` `DL-127` turns it off.

## Still advice

- "Large, truly parallel parts" is judgment. The hook cannot tell it, so the second launch always passes.
- A task with no `app` or `area` in the record is never checked.
- The hook injects no context. The spec text that said so is fixed (DELIVERYSPEC section 3).
- DL-39 reads the reason by words only. A reason that names a step can still be false.
