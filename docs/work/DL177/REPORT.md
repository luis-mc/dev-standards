# DL177 report (in progress)

## Base check
`git merge-base --is-ancestor abcda856 HEAD` succeeded (HEAD abcda85).

## What changed
- delivery_runner_pool.py: Probe.wsl_vm_parts/wsl_vm_gib (max of working set, private bytes), Probe.docker_run (Windows docker CLI first, `wsl docker` fallback) used by docker_cpus and container_gib, detect_host (VM floored at container use, host-load sample, decided-by), measured_sizing inputs, memory-per-CPU message with nearest passing sizes. detect_containers and Executor already try the plain CLI; no other `wsl docker` call needed a change.
- delivery_ci_setup.py (NOT in the owns list, but the Sizing inputs line is printed there): one added line with VM figures, host-load state and what decided.
- Host-load file holds one sample (mem %, at), not a series; it is used as that one sample, ignored when over 60 s old.
- Spec R5.22 to R5.24, feature note, change note.

## Tests
