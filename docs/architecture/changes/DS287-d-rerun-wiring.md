---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
task: DS287-d
---
The ts, go and rust CI templates run `rerun_tests.py` in each test job on pull requests (failed tests first, then affected packages) and upload a test report. `changed_areas.py unmapped --check` and `area_select.py --unmapped --check` fail a pull request that holds a file no area maps; the doctor reports the count.
