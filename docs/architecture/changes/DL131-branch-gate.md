---
plugin: claude/plugins/delivery/.claude-plugin/plugin.json
change: minor
---
`branch_gate.py` restores `docs/work` after the run (tracked files restored, new files removed, that folder only), so `--e2e-only` screenshots no longer leave the tree dirty (DL131). It sets `PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1` and `FORCE_COLOR=0` for its children and rewrites each step log as UTF-8 without colour codes, decoding non-UTF-8 output as cp1252 with replacement (DL134). When a branch changes `.cs` or `.csproj` files, it builds them with `dotnet build` where it can; where it cannot (no dotnet, or a Windows-only project off Windows) it adds `C# changed, not compiled on <os>` to the result's `warnings` list and prints it in the summary (DL141).
