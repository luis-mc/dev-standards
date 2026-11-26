---
title: Fix a citation of a removed delivery rule
type: how-to
---
# Fix a citation of a removed delivery rule

The delivery plugin no longer owns machine limits. Seven of its rules are removed: DL-50, DL-51, DL-77, DL-78, DL-79, DL-90 and DL-91. They covered the load guard, the heavy-job and runner rules, the runner hooks and the CI slots. These IDs are not reused.

## What failed

`docs_check.py` reports error `R1` for each line of your project that cites one of them. A project is checked when it has a `.delivery/` folder. The message looks like this:

```
ERROR R1 src/build.py:12: cites DL-77: removed, delete the citation. See docs/guides/removed-delivery-ids.md
```

## Find the citations

Run this from the project root:

```
grep -rnE "DL-(77|78|79|90|91)\b" . --exclude-dir=.git --exclude-dir=node_modules
```

It lists every file and line. Task IDs such as `DL77` have no hyphen and are not matched.

## What to change

Each hit is a comment, a test name, a doc sentence or a config note that points at a rule that is gone. For each one:

1. Delete the ID from the text. Keep the rest of the sentence if it is still true.
2. If the whole sentence or test only existed for the removed rule, delete it.
3. If a config file turns the rule off, for example `checks_off: ["DL-77"]`, delete that entry. The key is no longer read.
4. Do not replace the ID with another delivery ID.

Records of the past are not checked: `docs/archive/`, `docs/work/`, `docs/project/`, change notes and version table rows. Leave them as they are.

## Check again

Run `python3 <luismc-docs>/scripts/docs_check.py`. The `R1` errors are gone when no line cites a removed ID.
