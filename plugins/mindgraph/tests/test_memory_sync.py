import io
import json
import os
import sys

import chromadb
import pytest
from chromadb import Documents, EmbeddingFunction, Embeddings

from scripts import memory_sync as ms


class FakeEF(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t) % 7), 1.0, 0.5] for t in input]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    return tmp_path


def mem(home, project, name, body, type_="project"):
    d = home / "projects" / project / "memory"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(f"---\nname: {name[:-3]}\ndescription: d\nmetadata:\n  type: {type_}\n---\n\n{body}\n")
    return str(d / name)


@pytest.fixture
def col(home):
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(home / "home" / "palace"), settings=settings)
    return client.get_or_create_collection(ms.COLLECTION, embedding_function=FakeEF())


def memory_rows(col, source_file):
    res = col.get(where={"$and": [{"wing": {"$eq": "memory"}},
                                  {"source_file": {"$eq": source_file}}]},
                  include=["documents", "metadatas"])
    return res["documents"], res["metadatas"]


def test_eligibility():
    assert ms.is_eligible("project_x.md")
    assert not ms.is_eligible("MEMORY.md")
    assert not ms.is_eligible("archive.md")
    assert not ms.is_eligible("hub_clients.md")
    assert not ms.is_eligible("notes.txt")


def test_parse_memory_reads_nested_type():
    meta, body = ms.parse_memory("---\nname: a\ndescription: \"d\"\nmetadata:\n  type: feedback\n---\n\nBody here\n")
    assert meta == {"name": "a", "description": "d", "type": "feedback"}
    assert body == "Body here"


def test_chunk_body_splits_long_text_on_paragraphs():
    body = "\n\n".join(["x" * 1500] * 4)
    chunks = ms.chunk_body(body, max_chars=4000)
    assert len(chunks) == 2
    assert all(len(c) <= 4000 for c in chunks)


def test_sync_adds_with_metadata(col, home):
    path = mem(home, "proj-a", "a.md", "verdict one", "feedback")
    ms.sync_file(col, path)
    docs, metas = memory_rows(col, "memory/proj-a/a.md")
    assert docs == ["verdict one"]
    assert metas[0]["room"] == "feedback"
    assert metas[0]["memory_name"] == "a"
    assert metas[0]["project"] == "proj-a"


def test_edit_replaces_rather_than_duplicates(col, home):
    path = mem(home, "proj-a", "a.md", "old verdict")
    ms.sync_file(col, path)
    mem(home, "proj-a", "a.md", "new verdict")
    r = ms.sync_file(col, path)
    docs, _ = memory_rows(col, "memory/proj-a/a.md")
    assert docs == ["new verdict"]
    assert r["action"] == "synced" and r["deleted"] == 1 and r["added"] == 1


def test_unchanged_file_is_noop(col, home):
    path = mem(home, "proj-a", "a.md", "same")
    ms.sync_file(col, path)
    assert ms.sync_file(col, path)["action"] == "unchanged"


def test_frontmatter_only_edit_resyncs(col, home):
    path = mem(home, "proj-a", "a.md", "same", type_="project")
    ms.sync_file(col, path)
    mem(home, "proj-a", "a.md", "same", type_="feedback")
    r = ms.sync_file(col, path)
    assert r["action"] == "synced"
    docs, metas = memory_rows(col, "memory/proj-a/a.md")
    assert metas[0]["room"] == "feedback"


def test_deleted_file_removes_chunks(col, home):
    path = mem(home, "proj-a", "a.md", "gone soon")
    ms.sync_file(col, path)
    os.remove(path)
    assert ms.sync_file(col, path)["action"] == "deleted"
    assert memory_rows(col, "memory/proj-a/a.md")[0] == []


def test_other_wings_never_touched(col, home):
    col.add(ids=["notes1"], documents=["a raw note"],
            metadatas=[{"wing": "clients", "room": "x", "source_file": "memory/proj-a/a.md"}])
    path = mem(home, "proj-a", "a.md", "v1")
    ms.sync_file(col, path)
    mem(home, "proj-a", "a.md", "v2")
    ms.sync_file(col, path)
    os.remove(path)
    ms.sync_file(col, path)
    assert col.get(ids=["notes1"])["documents"] == ["a raw note"]


def test_delete_without_wing_clause_refused(col):
    with pytest.raises(ValueError):
        ms.safe_delete(col, {"source_file": {"$eq": "memory/proj-a/a.md"}})
    with pytest.raises(ValueError):
        ms.safe_delete(col, {"$and": [{"source_file": {"$eq": "x"}}, {"room": {"$eq": "y"}}]})


def test_dry_run_writes_nothing(col, home):
    path = mem(home, "proj-a", "a.md", "v1")
    ms.sync_file(col, path, dry_run=True)
    assert memory_rows(col, "memory/proj-a/a.md")[0] == []


def test_sync_all_reconciles_and_skips_hubs(col, home):
    mem(home, "proj-a", "a.md", "keep")
    mem(home, "proj-a", "hub_clients.md", "- [x](a.md)")
    orphan = mem(home, "proj-a", "b.md", "orphan")
    ms.sync_all(col)
    os.remove(orphan)
    summary = ms.sync_all(col)
    assert summary["unchanged"] == 1
    assert summary["deleted"] == 1
    assert memory_rows(col, "memory/proj-a/b.md")[0] == []
    assert memory_rows(col, "memory/proj-a/hub_clients.md")[0] == []


def test_run_hook_only_acts_inside_memory_dir(col, home):
    path = mem(home, "proj-a", "a.md", "hooked")
    factory = lambda: col
    outside = json.dumps({"tool_input": {"file_path": "/tmp/elsewhere.md"}})
    assert ms.run_hook(outside, collection_factory=factory, enabled=True) is None
    inside = json.dumps({"tool_input": {"file_path": path}})
    assert ms.run_hook(inside, collection_factory=factory, enabled=True)["action"] == "synced"
    assert ms.run_hook("not json", collection_factory=factory, enabled=True) is None


# --- F1: palace write lock ----------------------------------------------------

def test_palace_write_lock_creates_lock_file(home):
    assert not ms.lock_path().exists()
    with ms.palace_write_lock():
        assert ms.lock_path().exists()


class _FakeLock:
    def __init__(self, calls):
        self._calls = calls

    def __enter__(self):
        self._calls.append("locked")

    def __exit__(self, *exc):
        return False


def test_run_hook_ineligible_file_never_calls_factory(home):
    def boom():
        raise AssertionError("collection factory should not be called")
    path = mem(home, "proj-a", "hub_clients.md", "text")  # hub_ prefix is ineligible
    payload = json.dumps({"tool_input": {"file_path": path}})
    assert ms.run_hook(payload, collection_factory=boom, enabled=True) is None


# --- F5: quieter, cheaper hook -------------------------------------------------

def test_get_collection_fails_loudly_when_palace_missing(home, tmp_path):
    with pytest.raises(Exception):
        ms.get_collection(palace_path=str(tmp_path / "no-palace"))


def test_get_collection_with_embedding_function_creates(home, tmp_path):
    col = ms.get_collection(palace_path=str(tmp_path / "palace2"), embedding_function=FakeEF())
    assert col is not None


def test_hook_main_prints_nothing_on_success(monkeypatch, home, tmp_path, capsys):
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(tmp_path / "palace3"), settings=settings)
    col = client.get_or_create_collection(ms.COLLECTION, embedding_function=FakeEF())
    path = mem(home, "proj-a", "a.md", "hooked")
    monkeypatch.setattr(ms, "hook_enabled", lambda: True)
    monkeypatch.setattr(ms, "get_collection", lambda palace_path=None: col)
    monkeypatch.setattr(sys, "argv", ["memory_sync.py", "--hook"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": path}})))
    with pytest.raises(SystemExit) as exc:
        ms.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""


def test_hook_main_logs_error_and_exits_zero(monkeypatch, home, tmp_path, capsys):
    path = mem(home, "proj-a", "a.md", "hooked")
    monkeypatch.setattr(ms, "hook_enabled", lambda: True)

    def boom(palace_path=None):
        raise RuntimeError("palace unreachable")

    monkeypatch.setattr(ms, "get_collection", boom)
    monkeypatch.setattr(sys, "argv", ["memory_sync.py", "--hook"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": path}})))
    with pytest.raises(SystemExit) as exc:
        ms.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "palace unreachable" in ms.hook_log_path().read_text()


def test_all_exits_1_when_sync_all_has_errors(monkeypatch, home, tmp_path):
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(tmp_path / "palace4"), settings=settings)
    col = client.get_or_create_collection(ms.COLLECTION, embedding_function=FakeEF())
    mem(home, "proj-a", "a.md", "fine")
    monkeypatch.setattr(ms, "get_collection", lambda palace_path=None: col)
    monkeypatch.setattr(ms, "sync_all", lambda *a, **k: {"synced": 0, "unchanged": 0, "skipped": 0,
                                                          "deleted": 0, "added": 0,
                                                          "errors": [{"file": "a.md", "error": "boom"}],
                                                          "files": []})
    monkeypatch.setattr(sys, "argv", ["memory_sync.py", "--all"])
    with pytest.raises(SystemExit) as exc:
        ms.main()
    assert exc.value.code == 1


# --- Task 3 additions: per-project isolation, opt-in hook, actionable errors --

def test_same_filename_in_two_projects_is_independent(col, home):
    a = mem(home, "proj-a", "feedback_x.md", "A")
    b = mem(home, "proj-b", "feedback_x.md", "B")
    ms.sync_all(col)
    os.remove(a)
    ms.sync_all(col)
    left = col.get(where={"wing": {"$eq": "memory"}}, include=["metadatas"])["metadatas"]
    assert [m["source_file"] for m in left] == ["memory/proj-b/feedback_x.md"]


def test_project_without_memory_dir_is_skipped(col, home):
    (home / "projects" / "empty-proj").mkdir(parents=True)
    mem(home, "real", "a.md", "x")
    assert ms.sync_all(col)["errors"] == []


def test_hook_disabled_never_opens_collection(home, monkeypatch):
    path = mem(home, "p", "a.md", "x")
    called = []
    out = ms.run_hook(json.dumps({"tool_input": {"file_path": path}}),
                      collection_factory=lambda: called.append(1), enabled=False)
    assert out is None and called == []


def test_hook_enabled_reads_config(home):
    (home / "home").mkdir(parents=True, exist_ok=True)
    (home / "home" / "config.yml").write_text("memory:\n  sync_hook: true\n")
    assert ms.hook_enabled() is True
    (home / "home" / "config.yml").write_text("sources: []\n")
    assert ms.hook_enabled() is False


def test_hook_enabled_false_when_no_config(home):
    assert ms.hook_enabled() is False


def test_hook_skips_when_lock_busy(col, home):
    import fcntl
    path = mem(home, "p", "a.md", "x")
    lock = ms.lock_path()
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        out = ms.run_hook(json.dumps({"tool_input": {"file_path": path}}),
                          collection_factory=lambda: col, enabled=True)
    assert out == {"file": "a.md", "action": "skipped_lock_busy", "deleted": 0, "added": 0}
    assert "lock busy" in ms.hook_log_path().read_text()


def test_missing_palace_gives_actionable_error(home, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["memory_sync.py", "--all"])
    with pytest.raises(SystemExit) as e:
        ms.main()
    assert e.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert "run /mindgraph-setup first" in out["error"]


# --- I1: hook must be completely inert when the user hasn't opted in --------

def test_hook_inert_when_home_missing_and_not_opted_in(monkeypatch, tmp_path, capsys):
    home = tmp_path / "nohome"
    projects = tmp_path / "projects"
    monkeypatch.setenv("MINDGRAPH_HOME", str(home))
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(projects))
    payload = json.dumps({"tool_input": {"file_path": str(projects / "p" / "memory" / "a.md")}})
    monkeypatch.setattr(sys, "argv", ["memory_sync.py", "--hook"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    with pytest.raises(SystemExit) as exc:
        ms.main()
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert not home.exists()


def test_blocking_io_error_inside_sync_file_propagates(col, home, monkeypatch):
    path = mem(home, "p", "a.md", "x")

    def boom(*args, **kwargs):
        raise BlockingIOError()

    monkeypatch.setattr(ms, "sync_file", boom)
    with pytest.raises(BlockingIOError):
        ms.run_hook(json.dumps({"tool_input": {"file_path": path}}),
                    collection_factory=lambda: col, enabled=True)
