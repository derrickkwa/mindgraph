import importlib
import json
import subprocess
import sys
from pathlib import Path

import scripts.paths as paths

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_env.py"


def test_check_reports_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path))
    importlib.reload(paths)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=abc\n")
    import scripts.check_env as ce
    ce = importlib.reload(ce)
    result = ce.check()
    assert result["keys"]["gemini"] is True
    assert isinstance(result["python_ok"], bool)
    assert "python_version" in result


def test_cli_runs_as_a_direct_subprocess(tmp_path):
    """Regression test: the skill invokes this file directly (python3 .../check_env.py),
    not as a package import. Must not raise ModuleNotFoundError for 'scripts'."""
    env = {**__import__("os").environ, "MINDGRAPH_HOME": str(tmp_path)}
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True, text=True, cwd=str(tmp_path), env=env,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "python_ok" in data
    assert "ready" in data
