import importlib
import scripts.paths as paths


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
