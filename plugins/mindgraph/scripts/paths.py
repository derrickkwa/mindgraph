"""Resolve MindGraph's writable data home. Never write inside the plugin dir."""
import os
from pathlib import Path


def data_home() -> Path:
    raw = os.environ.get("MINDGRAPH_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".mempalace"
    home.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return data_home() / "config.yml"


def env_path() -> Path:
    return data_home() / ".env"


def _subdir(name: str) -> Path:
    d = data_home() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def wiki_dir() -> Path:
    return _subdir("_wiki")


def adapters_dir() -> Path:
    return _subdir("adapters")


def checkpoints_dir() -> Path:
    return _subdir("checkpoints")
