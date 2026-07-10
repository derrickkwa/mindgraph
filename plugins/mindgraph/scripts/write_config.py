import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json

import yaml
from scripts.paths import config_path

_SKELETON = {"sources": [], "llm_provider": "auto", "wings": [],
             "defaults": {"wing": "inbox", "room": "general"}}


def read() -> dict:
    p = config_path()
    if not p.exists():
        return dict(_SKELETON)
    data = yaml.safe_load(p.read_text()) or {}
    for k, v in _SKELETON.items():
        data.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return data


def _write(cfg: dict) -> None:
    config_path().write_text(yaml.safe_dump(cfg, sort_keys=False))


def set_sources(sources: list) -> None:
    cfg = read()
    cfg["sources"] = sources
    _write(cfg)


def set_wings(wings: list) -> None:
    cfg = read()
    cfg["wings"] = wings
    _write(cfg)


def _main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("set-sources", "set-wings"):
        print("usage: write_config.py <set-sources|set-wings> (JSON list on stdin)",
              file=sys.stderr)
        sys.exit(1)
    subcommand = sys.argv[1]
    data = json.loads(sys.stdin.read())
    if subcommand == "set-sources":
        set_sources(data)
        print(f"wrote {len(data)} sources")
    else:
        set_wings(data)
        print(f"wrote {len(data)} wings")


if __name__ == "__main__":
    _main()
