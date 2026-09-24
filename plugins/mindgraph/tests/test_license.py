"""LICENSE must be byte-identical at the repo root and inside the plugin
directory, since pyproject.toml's `license = {file = "LICENSE"}` resolves
relative to the plugin directory but the canonical fetched text lives at the
repo root.
"""
from pathlib import Path

REQUIRED_NOTICE = "Required Notice: Copyright (c) 2026 Derrick Kwa"


def _root_license() -> Path:
    return Path(__file__).resolve().parents[3] / "LICENSE"


def _plugin_license() -> Path:
    return Path(__file__).resolve().parents[1] / "LICENSE"


def test_root_license_exists():
    assert _root_license().is_file()


def test_plugin_license_exists():
    assert _plugin_license().is_file()


def test_license_files_are_byte_identical():
    root_bytes = _root_license().read_bytes()
    plugin_bytes = _plugin_license().read_bytes()
    assert root_bytes == plugin_bytes


def test_both_contain_required_notice():
    assert REQUIRED_NOTICE in _root_license().read_text()
    assert REQUIRED_NOTICE in _plugin_license().read_text()
