from pathlib import Path
import yaml

from scripts.paths import config_path


class ConfigError(Exception):
    pass


def load_config(path=None) -> dict:
    config_path_ = Path(path) if path is not None else config_path()
    if not config_path_.exists():
        raise ConfigError(
            f"config.yml not found at {config_path_}. Run /mindgraph-setup."
        )

    with open(config_path_) as f:
        config = yaml.safe_load(f) or {}

    # v1 → v2 migration: notes_folder becomes a single markdown source.
    if "notes_folder" in config and "sources" not in config:
        expanded = str(Path(config.pop("notes_folder")).expanduser())
        config["sources"] = [{"type": "markdown", "path": expanded}]

    config.setdefault("sources", [])
    for src in config["sources"]:
        if "path" in src:
            src["path"] = str(Path(src["path"]).expanduser())

    config.setdefault("llm_provider", "auto")
    config.setdefault("wings", [])
    config.setdefault("defaults", {"wing": "inbox", "room": "general"})
    return config
