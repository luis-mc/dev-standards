import os
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import delivery_ledger as L  # noqa: E402

# DL32: no test touches the real machine folder or the real local-heavy folder of the person running the tests.
_ISO = tempfile.mkdtemp(prefix="dl-iso-")
# DL165: always override. A CI job in the shared runner pool has DELIVERY_MACHINE_DIR set to the real
# machine folder, and setdefault kept it, so a fixture (64 'a' as RUNNER_SHA256) reached the real pool .env.
os.environ["DELIVERY_MACHINE_DIR"] = os.path.join(_ISO, "machine")
os.environ["DELIVERY_LOCAL_HEAVY_DIR"] = os.path.join(_ISO, "heavy")


def make_root(cfg=None):
    d = tempfile.mkdtemp(prefix="dl-")
    (Path(d) / ".delivery").mkdir()
    if cfg is not None:
        import json
        (Path(d) / ".delivery" / "config.json").write_text(json.dumps(cfg))
    return Path(d)
