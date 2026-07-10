import pytest
from pathlib import Path
from adapters.markdown import MarkdownAdapter
from adapters.base import validate_chunk

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG = {
    "notes_folder": str(FIXTURES / "notes"),
    "wings": [
        {"name": "work", "rooms": {"projects": ["work/projects/"], "meetings": ["work/meetings/"]}},
        {"name": "personal", "rooms": {"journal": ["personal/journal/"]}},
    ],
    "defaults": {"wing": "misc", "room": "general"},
}


def test_fetch_returns_chunks():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    assert len(chunks) >= 2


def test_chunks_pass_validation():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    for chunk in chunks:
        validate_chunk(chunk)


def test_wing_routing():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    work_chunks = [c for c in chunks if c["source_file"].startswith("work/")]
    assert all(c["wing"] == "work" for c in work_chunks)
    assert all(c["room"] == "projects" for c in work_chunks)


def test_personal_routing():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    personal_chunks = [c for c in chunks if c["source_file"].startswith("personal/")]
    assert all(c["wing"] == "personal" for c in personal_chunks)
    assert all(c["room"] == "journal" for c in personal_chunks)


def test_frontmatter_parsed():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    q2_chunks = [c for c in chunks if "q2-planning" in c["source_file"]]
    assert len(q2_chunks) >= 1
    assert q2_chunks[0]["title"] == "Q2 Planning"
    assert q2_chunks[0]["filed_at"] == "2026-04-01"


def test_no_empty_chunks():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(CONFIG)
    assert all(len(c["text"].strip()) > 0 for c in chunks)
