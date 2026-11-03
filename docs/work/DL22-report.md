# DL22: CIR10 step S6 (guided /delivery-ci-setup for Options 1 to 3)

Status: in progress.

Base: `origin/main`. `origin/DL17-ci-option-names` holds only a start report so far (no rename yet), so this branch uses the Option 1 to 3 names from CIR10 section 3 and does not depend on it. Rebase on it when it lands.

## Plan
1. Engine `delivery_ci_setup.py`: answers in, config out, install, doctor, numbered by-hand list.
2. One list of by-hand items (`by_hand_items`) that the printer and the doctor both read.
3. Doctor: checks each item (ok / confirmed / open / cannot check).
4. Command `commands/delivery-ci-setup.md`: asks, no default anywhere.
5. Tests with fakes for each option; docs, change notes.

## Steps done
(none yet)
