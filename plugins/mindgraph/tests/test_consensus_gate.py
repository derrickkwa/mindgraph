import math

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from scripts import consensus_gate as cg


class FakeEF(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[float(len(t) % 7), 1.0, 0.5] for t in input]


def test_identical_vectors_are_tight():
    embs = [[1.0, 0.0, 0.0]] * 4
    result = cg.evaluate(embs, threshold=0.55, min_sources=3)
    assert result["n_sources"] == 4
    assert result["consensus_score"] > 0.99
    assert result["is_tight"] is True


def test_spread_vectors_are_not_tight():
    embs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [-1.0, 0.0, 0.0]]
    result = cg.evaluate(embs, threshold=0.55, min_sources=3)
    assert result["consensus_score"] < 0.55
    assert result["is_tight"] is False


def test_below_min_sources_never_tight():
    embs = [[1.0, 0.0], [1.0, 0.0]]  # only 2, identical
    result = cg.evaluate(embs, threshold=0.55, min_sources=3)
    assert result["n_sources"] == 2
    assert result["is_tight"] is False


def test_mean_pairwise_cosine_normalizes():
    # unnormalized but colinear vectors → cosine 1.0
    embs = [[2.0, 0.0], [5.0, 0.0], [0.3, 0.0]]
    assert math.isclose(cg.mean_pairwise_cosine(embs), 1.0, rel_tol=1e-6)


def test_dedupe_by_source_collapses_chunks_to_one_vote():
    # three chunks, only two distinct notes → two votes, not three
    embs = [[1.0, 0.0], [0.9, 0.1], [0.0, 1.0]]
    metas = [{"source_file": "a.md"}, {"source_file": "a.md"}, {"source_file": "b.md"}]
    out = cg._dedupe_by_source(embs, metas)
    assert out == [[1.0, 0.0], [0.0, 1.0]]


def test_exclude_memory_drops_memory_sources():
    assert cg.exclude_memory(["memory/a.md", "6 July", "memory/b.md", "notes/x"]) == ["6 July", "notes/x"]


def test_score_with_only_memory_sources_never_queries(monkeypatch):
    def boom(**kw):
        raise AssertionError("should not fetch")
    monkeypatch.setattr(cg, "_fetch_embeddings", boom)
    result = cg.score(source_files=["memory/a.md", "memory/b.md"])
    assert result["n_sources"] == 0
    assert result["is_tight"] is False


def test_score_passes_filtered_sources(monkeypatch):
    seen = {}
    def fake(source_files=None, query=None, palace_path=None):
        seen["sf"] = source_files
        return [[1.0, 0.0]] * 3
    monkeypatch.setattr(cg, "_fetch_embeddings", fake)
    cg.score(source_files=["memory/a.md", "n1", "n2", "n3"])
    assert seen["sf"] == ["n1", "n2", "n3"]


# --- F4: gate excludes memory-wing rows even when source_file matches -------

def test_fetch_embeddings_excludes_memory_wing_by_where_clause(tmp_path):
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(tmp_path / "palace"), settings=settings)
    col = client.get_or_create_collection("mempalace_drawers", embedding_function=FakeEF())
    # Same source_file in both wings — the wing clause, not just exclude_memory(),
    # must be what keeps the memory-wing chunk out.
    col.add(ids=["mem1"], documents=["memory verdict text"],
            metadatas=[{"wing": "memory", "source_file": "shared.md"}])
    col.add(ids=["note1"], documents=["raw note text"],
            metadatas=[{"wing": "clients", "source_file": "shared.md"}])

    embs = cg._fetch_embeddings(source_files=["shared.md"], palace_path=str(tmp_path / "palace"))
    assert len(embs) == 1
    # confirm it's the notes embedding, not the memory one
    expected = list(map(float, FakeEF()(["raw note text"])[0]))
    assert list(map(float, embs[0])) == expected


def test_query_mode_excludes_memory_wing(tmp_path):
    import chromadb
    from chromadb import Documents, EmbeddingFunction, Embeddings

    class EF(EmbeddingFunction):
        def __call__(self, input: Documents) -> Embeddings:
            return [[1.0, 0.0, 0.0] for _ in input]

    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(tmp_path / "palace"), settings=settings)
    col = client.get_or_create_collection("mempalace_drawers", embedding_function=EF())
    col.add(ids=["n1", "m1"], documents=["note text", "memory text"],
            metadatas=[{"wing": "notes", "source_file": "a"},
                       {"wing": "memory", "source_file": "memory/p/x.md"}])
    embs = cg._fetch_embeddings(query="text", palace_path=str(tmp_path / "palace"),
                                embedding_function=EF())
    assert len(embs) == 1


# --- M1: missing palace prints a clean JSON error, not a traceback ----------

def test_missing_palace_prints_json_error_and_exits_1(tmp_path, capsys, monkeypatch):
    import sys
    monkeypatch.setattr(sys, "argv", ["consensus_gate.py", "--query", "x",
                                      "--palace", str(tmp_path / "no-palace")])
    with __import__("pytest").raises(SystemExit) as exc:
        cg.main()
    assert exc.value.code == 1
    out = __import__("json").loads(capsys.readouterr().out)
    assert "palace not found at" in out["error"]
    assert "mindgraph-setup" in out["error"]
