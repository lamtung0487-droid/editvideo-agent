"""Where learnkit keeps what it learns: one folder of plain JSON (LEARNKIT_DATA, or set by the host), atomic writes."""
import hashlib
import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from filelock import FileLock

_ROOT = None
ID = re.compile(r"^(ex|cmp|bp)-[0-9a-f]{16}$")


def root():
    global _ROOT
    if _ROOT is None:
        _ROOT = Path(os.environ.get("LEARNKIT_DATA", "learnkit-data")).resolve()
    return _ROOT


def configure(path):
    """A host points learnkit at its own data folder (EditVideo: <EDITVIDEO_DATA>/learnkit)."""
    global _ROOT
    _ROOT = Path(path).resolve()
    return _ROOT


def now():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def lock(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return FileLock(str(path) + ".lock", timeout=20)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def check_id(value, prefix):
    if not isinstance(value, str) or not ID.fullmatch(value) or not value.startswith(prefix + "-"):
        raise ValueError(f"Expected a {prefix}-… id returned by learnkit")
    return value


def path_for(item_id):
    kind = item_id.split("-", 1)[0]
    folder = {"ex": "exemplars", "cmp": "comparisons", "bp": "blueprints"}[kind]
    return root() / folder / (item_id + ".json")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
