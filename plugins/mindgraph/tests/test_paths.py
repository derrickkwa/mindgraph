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


def test_palace_dir_honors_env(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.palace_dir() == tmp_path / "brain" / "palace"
    assert paths.palace_dir().is_dir()


def test_palace_dir_default_is_dot_mempalace(monkeypatch):
    monkeypatch.delenv("MINDGRAPH_HOME", raising=False)
    import importlib, scripts.paths as paths
    paths = importlib.reload(paths)
    assert paths.palace_dir() == Path.home() / ".mempalace" / "palace"


def test_kg_db_path_honors_env(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.kg_db_path() == tmp_path / "brain" / "knowledge_graph.sqlite3"


def test_batch_ingest_resolves_paths_under_home(tmp_path, monkeypatch):
    """get_chromadb_collection / get_kg must resolve under MINDGRAPH_HOME,
    without touching a live DB — chromadb.PersistentClient and
    KnowledgeGraph are faked to just record the path/db_path passed in."""
    import sys
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path / "brain"))

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "scripts"))
    sys.path.insert(0, str(root / "skills" / "brain-ingest" / "scripts"))

    import scripts.paths as paths_mod
    importlib.reload(paths_mod)

    import batch_ingest
    importlib.reload(batch_ingest)

    recorded = {}

    class FakeCollection:
        pass

    class FakePersistentClient:
        def __init__(self, path):
            recorded["chroma_path"] = path

        def get_or_create_collection(self, name):
            return FakeCollection()

    class FakeChromaModule:
        PersistentClient = FakePersistentClient

    class FakeKnowledgeGraph:
        def __init__(self, db_path=None):
            recorded["kg_db_path"] = db_path

    monkeypatch.setitem(sys.modules, "chromadb", FakeChromaModule())

    import types
    fake_mempalace_kg_module = types.ModuleType("mempalace.knowledge_graph")
    fake_mempalace_kg_module.KnowledgeGraph = FakeKnowledgeGraph
    fake_mempalace_module = types.ModuleType("mempalace")
    fake_mempalace_module.knowledge_graph = fake_mempalace_kg_module
    monkeypatch.setitem(sys.modules, "mempalace", fake_mempalace_module)
    monkeypatch.setitem(sys.modules, "mempalace.knowledge_graph", fake_mempalace_kg_module)

    batch_ingest.get_chromadb_collection()
    batch_ingest.get_kg()

    home = tmp_path / "brain"
    assert Path(recorded["chroma_path"]) == home / "palace"
    assert Path(recorded["kg_db_path"]) == home / "knowledge_graph.sqlite3"
