#!/usr/bin/env python3
"""
markdown.py — Plain markdown adapter for MindGraph.

Reads .md files from a single source {type, path}, emits every chunk into
the inbox wing ("general" room) with a namespaced source_file
("{SOURCE_TYPE}:{relpath}"). Wing/room routing is decided downstream
(by triage), not by the adapter.

Usage:
    python adapters/markdown.py --path ~/notes
    python adapters/markdown.py --config config.yml
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from adapters.base import AdapterBase

CHUNK_TARGET_CHARS = 1600
CHUNK_MIN_CHARS = 400
CHUNK_OVERLAP_CHARS = 200


class MarkdownAdapter(AdapterBase):
    SOURCE_TYPE = "markdown"

    def fetch(self, source: dict) -> list[dict]:
        folder = Path(source["path"]).expanduser()
        if not folder.exists():
            raise FileNotFoundError(f"source path not found: {folder}")

        chunks = []
        for md_file in sorted(folder.rglob("*.md")):
            rel = md_file.relative_to(folder)
            frontmatter, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
            title = frontmatter.get("title", md_file.stem.replace("-", " ").title())
            filed_at = _parse_date(frontmatter.get("date"), md_file)
            for chunk_text in _chunk(body):
                chunks.append({
                    "text": chunk_text,
                    "source_file": f"{self.SOURCE_TYPE}:{rel}",
                    "wing": "inbox",
                    "room": "general",
                    "filed_at": filed_at,
                    "title": title,
                    "tags": frontmatter.get("tags", []),
                })
        return chunks


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].strip()
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, body


def _parse_date(date_val, md_file: Path) -> str:
    if date_val:
        if hasattr(date_val, "isoformat"):
            return date_val.isoformat()
        try:
            return str(date_val)[:10]
        except Exception:
            pass
    return datetime.fromtimestamp(md_file.stat().st_mtime).date().isoformat()


def _chunk(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_TARGET_CHARS:
        return [text]

    chunks = []
    prev_overlap = ""
    remaining = text

    while remaining:
        candidate = prev_overlap + remaining
        if len(candidate) <= CHUNK_TARGET_CHARS:
            if len(candidate.strip()) >= CHUNK_MIN_CHARS:
                chunks.append(candidate.strip())
            break

        split_at = CHUNK_TARGET_CHARS
        para_break = candidate.rfind("\n\n", CHUNK_MIN_CHARS, split_at)
        if para_break == -1:
            para_break = candidate.rfind("\n", CHUNK_MIN_CHARS, split_at)
        if para_break == -1:
            para_break = split_at

        chunk = candidate[:para_break].strip()
        if chunk:
            chunks.append(chunk)

        consumed = para_break - len(prev_overlap)
        prev_overlap = remaining[max(0, consumed - CHUNK_OVERLAP_CHARS):consumed]
        remaining = remaining[consumed:]

    return [c for c in chunks if c.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=None, help="Path to a markdown notes folder")
    parser.add_argument("--config", default="config.yml", help="Used only if --path is omitted")
    args = parser.parse_args()

    if args.path:
        source = {"type": "markdown", "path": args.path}
    else:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scripts.config import load_config

        config = load_config(args.config)
        source = next(
            (s for s in config["sources"] if s.get("type") in ("markdown", "obsidian")),
            None,
        )
        if source is None:
            raise SystemExit("No markdown/obsidian source found in config.yml; pass --path instead.")

    adapter = MarkdownAdapter()
    chunks = adapter.fetch(source)

    print(f"Found {len(chunks)} chunks from {source['path']}")
    if chunks:
        print("\nSample chunk:")
        print(json.dumps(chunks[0], indent=2, default=str))
