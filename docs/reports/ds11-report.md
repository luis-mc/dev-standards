
## Results
- Delivery plugin tests (`python3 -m unittest discover` in `claude/plugins/delivery/tests`): 135 passed after adjusting `test_question_asked_then_answered` (a prompt now always records `owner_prompt`).
- `tools/test_delivery_hooks.py`: 46 passed. `change_notes.py check`: ok.
- `tools/test_rule_tags.py` not run locally (session guard: heavy suite, left to CI); the Q-5 bullet keeps its single `<!-- check: Q-5 -->` tag and the new plugin rule file is identical to the asset.
