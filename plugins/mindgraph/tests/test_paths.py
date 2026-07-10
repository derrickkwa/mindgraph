import importlib
from pathlib import Path


def _fresh(monkeypatch, home):
    monkeypatch.setenv("MINDGRAPH_HOME", str(home))
    import scripts.paths as paths
    return importlib.reload(paths)


def test_data_home_honors_env(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.data_home() == (tmp_path / "brain")
    assert paths.data_home().is_dir()


def test_default_is_dot_mempalace(monkeypatch):
    monkeypatch.delenv("MINDGRAPH_HOME", raising=False)
    import importlib, scripts.paths as paths
    paths = importlib.reload(paths)
    assert paths.data_home() == Path.home() / ".mempalace"


def test_derived_paths(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.config_path() == tmp_path / "brain" / "config.yml"
    assert paths.env_path() == tmp_path / "brain" / ".env"
    assert paths.checkpoints_dir().is_dir()
    assert paths.adapters_dir().is_dir()
    assert paths.wiki_dir().is_dir()
