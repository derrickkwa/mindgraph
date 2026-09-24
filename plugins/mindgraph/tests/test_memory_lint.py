import json
import sys
from pathlib import Path

import chromadb
import pytest
from chromadb import Documents, EmbeddingFunction, Embeddings

sys.path.insert(0, str(Path(__file__).parent.parent / "skills/brain-lint/scripts"))
import memory_lint as ml


class FakeEF(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t) % 7), 1.0, 0.5] for t in input]


def mk(d, name, body, fm_name=None):
    fm_name = fm_name or name[:-3]
    (d / name).write_text(f"---\nname: {fm_name}\ndescription: x\nmetadata:\n  type: project\n---\n\n{body}\n")


def setup(tmp_path, index):
    d = tmp_path / "memory"
    d.mkdir()
    (d / "MEMORY.md").write_text(index)
    return d


def checks(result, level):
    return {(f["check"], f.get("file"), f.get("link")) for f in result[level]}


def test_index_size_error(tmp_path):
    d = setup(tmp_path, "x" * 20000)
    assert ("index_size", None, None) in checks(ml.lint(str(d)), "errors")


def test_reachable_directly_and_via_hub(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n- [Hub](hub_clients.md)\n")
    mk(d, "project_a.md", "a")
    mk(d, "hub_clients.md", "- [B](project_b.md)")
    mk(d, "project_b.md", "b")
    mk(d, "project_c.md", "c")
    errs = checks(ml.lint(str(d)), "errors")
    assert ("unreachable", "project_c.md", None) in errs
    assert not any(f == "project_a.md" or f == "project_b.md" for _, f, _ in errs)


def test_link_resolves_by_stem_or_frontmatter_name(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n")
    mk(d, "project_a.md", "see [[feedback-x]] and [[project_a]]")
    mk(d, "feedback_x.md", "x", fm_name="feedback-x")
    (d / "MEMORY.md").write_text("- [A](project_a.md)\n- [X](feedback_x.md)\n")
    r = ml.lint(str(d))
    assert not r["warnings"] and not r["errors"]


def test_near_match_is_error_dangling_is_warning(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n- [T](project_tool_y.md)\n")
    mk(d, "project_a.md", "[[project-tool-y]] and [[project_future_idea]]")
    mk(d, "project_tool_y.md", "y")
    r = ml.lint(str(d))
    assert ("near_match_link", "project_a.md", "project-tool-y") in checks(r, "errors")
    assert ("dangling_link", "project_a.md", "project_future_idea") in checks(r, "warnings")


def test_name_only_read_from_frontmatter(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n- [B](project_b.md)\n")
    (d / "project_b.md").write_text(
        "---\ndescription: x\nmetadata:\n  type: project\n---\n\n"
        "body text\nname: bogus\n---\nmore body\n"
    )
    mk(d, "project_a.md", "[[bogus]]")
    r = ml.lint(str(d))
    assert ("dangling_link", "project_a.md", "bogus") in checks(r, "warnings")
    assert not checks(r, "errors")


def test_hnsw_canary_passes_when_vectors_present(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n")
    mk(d, "project_a.md", "canary body text")
    client = chromadb.PersistentClient(path=str(tmp_path / "palace"))
    col = client.get_or_create_collection("mempalace_drawers", embedding_function=FakeEF())
    col.add(ids=["drawer_memory_abc123"], documents=["canary body text"],
            metadatas=[{"wing": "memory", "room": "project",
                       "source_file": "memory/project_a.md", "chunk_index": 0}])
    r = ml.lint(str(d), col=col)
    assert not any(w["check"] == "sync_vector_missing" for w in r["warnings"])
    assert not any(w["check"] in ("sync_missing", "sync_orphan") for w in r["warnings"])


def test_hnsw_canary_warns_when_own_id_missing_from_query_results(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n")
    mk(d, "project_a.md", "canary body text")
    client = chromadb.PersistentClient(path=str(tmp_path / "palace"))
    col = client.get_or_create_collection("mempalace_drawers", embedding_function=FakeEF())
    col.add(ids=["drawer_memory_abc123"], documents=["canary body text"],
            metadatas=[{"wing": "memory", "room": "project",
                       "source_file": "memory/project_a.md", "chunk_index": 0}])

    real_query = col.query

    def stub_query(*args, **kwargs):
        res = real_query(*args, **kwargs)
        res["ids"] = [[]]
        return res
    col.query = stub_query

    r = ml.lint(str(d), col=col)
    warns = [w for w in r["warnings"] if w["check"] == "sync_vector_missing"]
    assert warns == [{"check": "sync_vector_missing", "file": "memory/project_a.md",
                      "id": "drawer_memory_abc123"}]


def test_fix_near_matches_rewrites_links(tmp_path):
    d = setup(tmp_path, "- [A](project_a.md)\n- [T](project_tool_y.md)\n")
    mk(d, "project_a.md", "[[project-tool-y]] twice [[project-tool-y]]")
    mk(d, "project_tool_y.md", "y")
    fixes = ml.fix_near_matches(str(d))
    assert fixes == [{"file": "project_a.md", "from": "project-tool-y", "to": "project_tool_y"}]
    assert "[[project_tool_y]] twice [[project_tool_y]]" in (d / "project_a.md").read_text()
    assert not ml.lint(str(d))["errors"]


def test_lint_all_skips_projects_without_index(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path))
    (tmp_path / "no-memory").mkdir()
    (tmp_path / "no-index" / "memory").mkdir(parents=True)
    d = tmp_path / "ok" / "memory"; d.mkdir(parents=True)
    (d / "MEMORY.md").write_text("# Memory\n")
    out = ml.lint_all()
    assert list(out["projects"]) == ["ok"]


def test_lint_all_scopes_sync_checks_per_project(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path))
    d1 = tmp_path / "proj-a" / "memory"; d1.mkdir(parents=True)
    (d1 / "MEMORY.md").write_text("- [A](project_a.md)\n")
    mk(d1, "project_a.md", "a body")
    d2 = tmp_path / "proj-b" / "memory"; d2.mkdir(parents=True)
    (d2 / "MEMORY.md").write_text("- [B](project_b.md)\n")
    mk(d2, "project_b.md", "b body")

    client = chromadb.PersistentClient(path=str(tmp_path / "palace"))
    col = client.get_or_create_collection("mempalace_drawers", embedding_function=FakeEF())
    col.add(
        ids=["drawer_memory_a1", "drawer_memory_b1"],
        documents=["a body", "b body"],
        metadatas=[
            {"wing": "memory", "room": "project", "project": "proj-a",
             "source_file": "memory/proj-a/project_a.md", "chunk_index": 0},
            {"wing": "memory", "room": "project", "project": "proj-b",
             "source_file": "memory/proj-b/project_b.md", "chunk_index": 0},
        ],
    )
    out = ml.lint_all(col=col)
    assert list(out["projects"]) == ["proj-a", "proj-b"]
    for slug in ("proj-a", "proj-b"):
        warns = out["projects"][slug]["warnings"]
        assert not any(w["check"] in ("sync_missing", "sync_orphan") for w in warns)


# --- M3: --memory-dir --check-sync infers project; clean JSON on failure ---

def test_check_sync_infers_project_from_memory_dir(tmp_path, monkeypatch):
    proj_root = tmp_path / "projects" / "proj-a" / "memory"
    proj_root.mkdir(parents=True)
    (proj_root / "MEMORY.md").write_text("# Memory\n")
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(ml, "get_collection", lambda: object())
    captured = {}

    def fake_lint(memory_dir, col, project=None, max_bytes=ml.INDEX_MAX_BYTES):
        captured["project"] = project
        return {"errors": [], "warnings": [], "stats": {}}

    monkeypatch.setattr(ml, "lint", fake_lint)
    monkeypatch.setattr(sys, "argv", ["memory_lint.py", "--memory-dir", str(proj_root), "--check-sync"])
    ml.main()
    assert captured["project"] == "proj-a"


def test_check_sync_memory_dir_outside_projects_dir_prints_json_error(tmp_path, monkeypatch, capsys):
    outside = tmp_path / "somewhere" / "memory"
    outside.mkdir(parents=True)
    (outside / "MEMORY.md").write_text("# Memory\n")
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(ml, "get_collection", lambda: object())
    monkeypatch.setattr(sys, "argv", ["memory_lint.py", "--memory-dir", str(outside), "--check-sync"])
    with pytest.raises(SystemExit) as exc:
        ml.main()
    assert exc.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert "--project" in out["error"]


def test_nonexistent_project_prints_json_error_not_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setattr(sys, "argv", ["memory_lint.py", "--project", "ghost-project"])
    with pytest.raises(SystemExit) as exc:
        ml.main()
    assert exc.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert "error" in out
