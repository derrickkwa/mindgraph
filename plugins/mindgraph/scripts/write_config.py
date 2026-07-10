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
