import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import delivery_ledger as L  # noqa: E402


def make_root(cfg=None):
    d = tempfile.mkdtemp(prefix="dl-")
    (Path(d) / ".delivery").mkdir()
    if cfg is not None:
        import json
        (Path(d) / ".delivery" / "config.json").write_text(json.dumps(cfg))
    return Path(d)
