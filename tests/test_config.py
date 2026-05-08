import pytest
from pathlib import Path
from scripts.config import load_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_valid_config():
    config = load_config(FIXTURES / "config_valid.yml")
    assert config["llm_provider"] == "auto"
    assert len(config["wings"]) == 2
    assert config["defaults"]["wing"] == "misc"


def test_notes_folder_expanded():
    config = load_config(FIXTURES / "config_valid.yml")
    assert "~" not in config["notes_folder"]


def test_missing_config_raises():
    with pytest.raises(ConfigError, match="config.yml not found"):
        load_config("/nonexistent/config.yml")


def test_missing_notes_folder_raises():
    with pytest.raises(ConfigError, match="notes_folder"):
        load_config(FIXTURES / "config_no_notes.yml")


def test_default_llm_provider():
    config = load_config(FIXTURES / "config_minimal.yml")
    assert config["llm_provider"] == "auto"
