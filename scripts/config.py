from pathlib import Path
import yaml


class ConfigError(Exception):
    pass


def load_config(path: str | Path = "config.yml") -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"config.yml not found at {config_path.resolve()}. "
            "Run: python scripts/setup.py"
        )

    with open(config_path) as f:
        config = yaml.safe_load(f) or {}

    if "notes_folder" not in config:
        raise ConfigError("config.yml must include 'notes_folder'")

    config["notes_folder"] = str(Path(config["notes_folder"]).expanduser())
    config.setdefault("llm_provider", "auto")
    config.setdefault("wings", [])
    config.setdefault("defaults", {"wing": "misc", "room": "general"})

    return config
