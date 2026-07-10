import pytest
from pathlib import Path
from scripts.config import load_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def test_v2_sources_loaded():
    config = load_config(FIXTURES / "config_v2.yml")
    assert config["sources"][0]["type"] == "obsidian"
    assert config["wings"][0]["rooms"][0]["name"] == "acquisition"
    assert config["defaults"]["wing"] == "inbox"


def test_v1_migrated_to_sources():
    config = load_config(FIXTURES / "config_v1.yml")
    assert config["sources"] == [{"type": "markdown", "path": config["sources"][0]["path"]}]
    assert "~" not in config["sources"][0]["path"]
    assert "notes_folder" not in config


def test_missing_config_raises():
    with pytest.raises(ConfigError, match="config.yml not found"):
        load_config("/nonexistent/config.yml")


def test_defaults_applied():
    config = load_config(FIXTURES / "config_v2.yml")
    assert config["llm_provider"] == "auto"
