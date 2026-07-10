from pathlib import Path
from adapters.obsidian import ObsidianAdapter

VAULT = Path(__file__).parent / "fixtures" / "obsidian_vault"


def test_ignores_obsidian_dir_and_extracts_wikilinks():
    chunks = ObsidianAdapter().fetch({"type": "obsidian", "path": str(VAULT)})
    assert all(".obsidian" not in c["source_file"] for c in chunks)
    joined_tags = [t for c in chunks for t in c["tags"]]
    assert "activation" in joined_tags and "funnel design" in joined_tags
    assert "[[" not in chunks[0]["text"]


def test_aliased_wikilink_tags_use_target_not_alias():
    chunks = ObsidianAdapter().fetch({"type": "obsidian", "path": str(VAULT)})
    joined_tags = [t for c in chunks for t in c["tags"]]
    assert "retention" in joined_tags
    assert "retention|Retention Loops" not in joined_tags
    assert "Retention Loops" not in joined_tags
    assert "Retention Loops" not in chunks[0]["text"]
    assert "|" not in chunks[0]["text"]
