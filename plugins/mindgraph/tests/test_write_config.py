import importlib
import subprocess
import sys
import yaml
from pathlib import Path

import scripts.paths as paths

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_config.py"


def _mod(monkeypatch, tmp_path):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path))
    importlib.reload(paths)
    import scripts.write_config as wc
    return importlib.reload(wc)


def test_set_sources_then_wings_roundtrip(tmp_path, monkeypatch):
    wc = _mod(monkeypatch, tmp_path)
    wc.set_sources([{"type": "notion"}])
    wc.set_wings([{"name": "growth", "rooms": [{"name": "acq", "concepts": ["funnel-design"]}]}])
    cfg = wc.read()
    assert cfg["sources"] == [{"type": "notion"}]
    assert cfg["wings"][0]["rooms"][0]["concepts"] == ["funnel-design"]
    assert cfg["defaults"] == {"wing": "inbox", "room": "general"}


def test_cli_set_sources_runs_as_a_direct_subprocess(tmp_path, monkeypatch):
    """Regression test: the skill invokes this file directly (python3 .../write_config.py),
    not as a package import. Must not raise ModuleNotFoundError for 'scripts'."""
    env = {**__import__("os").environ, "MINDGRAPH_HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "set-sources"],
        input='[{"type": "obsidian", "path": "/tmp/x"}]',
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "wrote 1 sources" in result.stdout
    cfg = yaml.safe_load((tmp_path / "config.yml").read_text())
    assert cfg["sources"] == [{"type": "obsidian", "path": "/tmp/x"}]


def test_cli_set_wings_runs_as_a_direct_subprocess(tmp_path, monkeypatch):
    env = {**__import__("os").environ, "MINDGRAPH_HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "set-wings"],
        input='[{"name": "growth", "rooms": [{"name": "acq", "concepts": ["funnel-design"]}]}]',
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "wrote 1 wings" in result.stdout
    cfg = yaml.safe_load((tmp_path / "config.yml").read_text())
    assert cfg["wings"][0]["name"] == "growth"
