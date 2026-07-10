#!/usr/bin/env python3
"""
obsidian.py — Obsidian vault adapter for MindGraph.

Extends MarkdownAdapter to ignore the .obsidian/ config directory and
extract [[wikilinks]] into tags, stripping the bracket syntax from the
chunk text.
"""

import re
from pathlib import Path
from adapters.markdown import MarkdownAdapter, _parse_frontmatter, _parse_date, _chunk

_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


class ObsidianAdapter(MarkdownAdapter):
    SOURCE_TYPE = "obsidian"

    def fetch(self, source: dict) -> list[dict]:
        folder = Path(source["path"]).expanduser()
        if not folder.exists():
            raise FileNotFoundError(f"source path not found: {folder}")
        chunks = []
        for md_file in sorted(folder.rglob("*.md")):
            if ".obsidian" in md_file.parts:
                continue
            rel = md_file.relative_to(folder)
            fm, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
            links = [link.split("|")[0] for link in _WIKILINK.findall(body)]
            body = _WIKILINK.sub(lambda m: m.group(1).split("|")[0], body)
            title = fm.get("title", md_file.stem.replace("-", " ").title())
            filed_at = _parse_date(fm.get("date"), md_file)
            tags = list(fm.get("tags", [])) + links
            for chunk_text in _chunk(body):
                chunks.append({
                    "text": chunk_text, "source_file": f"obsidian:{rel}",
                    "wing": "inbox", "room": "general", "filed_at": filed_at,
                    "title": title, "tags": tags,
                })
        return chunks
