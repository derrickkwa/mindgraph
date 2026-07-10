import pytest

from adapters.markdown import MarkdownAdapter
from scripts.adapter_registry import get_adapter


def test_resolves_bundled_markdown():
    assert isinstance(get_adapter("markdown"), MarkdownAdapter)


@pytest.mark.xfail(reason="obsidian adapter lands in Task 8", strict=False)
def test_obsidian_is_markdown_subclass():
    from adapters.obsidian import ObsidianAdapter
    assert isinstance(get_adapter("obsidian"), ObsidianAdapter)


def test_unknown_type_raises():
    with pytest.raises(ValueError, match="unknown source type"):
        get_adapter("does-not-exist")
