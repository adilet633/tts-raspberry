import json
from pathlib import Path


def load_config(path: str = "config.json") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError("Config not found: {}".format(path))
    return json.loads(p.read_text(encoding="utf-8"))