from adapters.notion import _plain_text, _extract


def test_plain_text_joins_rich_text():
    blocks = {"results": [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]}},
        {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Title"}]}},
    ]}
    assert _plain_text(blocks) == "Hello world\nTitle"


def test_extract_builds_namespaced_record():
    page = {"id": "abc-123", "created_time": "2026-01-02T00:00:00.000Z",
            "properties": {"title": {"title": [{"plain_text": "My Page"}]}}}
    blocks = {"results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Body text here."}]}}]}
    rec = _extract(page, blocks)
    assert rec["source_file"] == "notion:abc-123"
    assert rec["title"] == "My Page"
    assert rec["filed_at"] == "2026-01-02"
    assert "Body text here." in rec["text"]
