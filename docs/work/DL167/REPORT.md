# DL167 report

## What changed
- Dockerfile: new always-on RUN installs clang, lld, llvm (no recommends, apt lists cleaned), finds the LLVM dir at build time, links clang-cl, lld-link, llvm-lib, llvm-ar, llvm-rc, lld into /usr/local/bin when not on PATH, then a self-check RUN.
- Spec: R13.88. Change notes: docs/architecture/changes/DL167-pool-llvm.md and docs/features/delivery/changes/DL167.md.
- Tests: new test_dl167_pool_llvm.py. No existing expectation moved.
- No Docker: the image was not built. `llvm-lib /?` exit code 0 is assumed (it prints help), not checked.

## Tests
- `python3 -m unittest test_dl167_pool_llvm test_runner_pool test_dl162_pool_refresh_files test_dl165_pool_refresh_hash_result` (in the tests folder): 175 tests OK.
- `docs_check.py`: one error, G1 (decisions.md stale). It fails the same on clean main, and generated files are not mine to edit.
- `gh workflow run spec-lint.yml --ref DL167-pool-llvm -f areas=delivery`, run 42803065524, watched to the end. Overall: failure. All 9 delivery jobs and "which areas" succeeded. "docs check" failed on W1 (expected) and G1 (decisions.md stale, same on clean main; generated file, not edited). Other jobs skipped.
- Not run: Docker build, mutation passes.

Branch head SHA: see `git rev-parse origin/DL167-pool-llvm` (the report commit itself cannot hold its own SHA).
READY
