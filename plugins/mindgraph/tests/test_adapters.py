import pytest
from adapters.base import AdapterBase, validate_chunk, ChunkValidationError


def test_adapter_base_is_abstract():
    with pytest.raises(TypeError):
        AdapterBase()


def test_valid_chunk_passes():
    chunk = {
        "text": "Some content here",
        "source_file": "work/projects/q2.md",
        "wing": "work",
        "room": "projects",
        "filed_at": "2026-05-09",
    }
    validate_chunk(chunk)  # should not raise


def test_chunk_missing_required_field_raises():
    chunk = {
        "text": "content",
        "source_file": "work/q2.md",
        "wing": "work",
    }
    with pytest.raises(ChunkValidationError, match="room"):
        validate_chunk(chunk)


def test_chunk_empty_text_raises():
    chunk = {
        "text": "",
        "source_file": "work/q2.md",
        "wing": "work",
        "room": "projects",
        "filed_at": "2026-05-09",
    }
    with pytest.raises(ChunkValidationError, match="text"):
        validate_chunk(chunk)


def test_chunk_optional_fields_allowed():
    chunk = {
        "text": "Some content",
        "source_file": "work/q2.md",
        "wing": "work",
        "room": "projects",
        "filed_at": "2026-05-09",
        "title": "Q2 Planning",
        "source_url": "https://example.com",
        "tags": ["planning", "q2"],
    }
    validate_chunk(chunk)  # should not raise
