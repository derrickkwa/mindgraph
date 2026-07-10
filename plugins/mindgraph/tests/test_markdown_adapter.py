from pathlib import Path
from adapters.markdown import MarkdownAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "notes"


def test_emits_inbox_and_namespaced_source_file():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch({"type": "markdown", "path": str(FIXTURES)})
    assert chunks, "expected chunks from fixture notes"
    for c in chunks:
        assert c["wing"] == "inbox"
        assert c["room"] == "general"
        assert c["source_file"].startswith("markdown:")
        assert set(["text", "source_file", "wing", "room", "filed_at"]) <= set(c)


def test_source_type_prefix_overridable():
    class FakeObsidian(MarkdownAdapter):
        SOURCE_TYPE = "obsidian"
    chunks = FakeObsidian().fetch({"type": "obsidian", "path": str(FIXTURES)})
    assert all(c["source_file"].startswith("obsidian:") for c in chunks)
