#!/usr/bin/env python3
"""
markdown.py — Plain markdown adapter for MindGraph.

Reads .md files from notes_folder, routes to wings/rooms via config.yml
folder mappings, parses frontmatter, and chunks content.

Usage (test mode):
    python adapters/markdown.py --test --config config.yml
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
    def fetch(self, config: dict) -> list[dict]:
        notes_folder = Path(config["notes_folder"]).expanduser()
        if not notes_folder.exists():
            raise FileNotFoundError(f"notes_folder not found: {notes_folder}")

        mappings = _build_mappings(config["wings"])
        default_wing = config["defaults"]["wing"]
        default_room = config["defaults"]["room"]

        chunks = []
        for md_file in sorted(notes_folder.rglob("*.md")):
            rel = md_file.relative_to(notes_folder)
            wing, room = _route(str(rel), mappings, default_wing, default_room)
            frontmatter, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))

            title = frontmatter.get("title", md_file.stem.replace("-", " ").title())
            filed_at = _parse_date(frontmatter.get("date"), md_file)

            for chunk_text in _chunk(body):
                chunks.append({
                    "text": chunk_text,
                    "source_file": str(rel),
                    "wing": wing,
                    "room": room,
                    "filed_at": filed_at,
                    "title": title,
                    "tags": frontmatter.get("tags", []),
                })
        return chunks


def _build_mappings(wings: list[dict]) -> list[tuple[str, str, str]]:
    """Returns [(folder_prefix, wing, room)] sorted longest-first for greedy match."""
    mappings = []
    for wing_def in wings:
        wing_name = wing_def["name"]
        for room_name, folders in wing_def.get("rooms", {}).items():
            for folder in folders:
                mappings.append((folder.rstrip("/"), wing_name, room_name))
    return sorted(mappings, key=lambda x: len(x[0]), reverse=True)


def _route(rel_path: str, mappings: list, default_wing: str, default_room: str) -> tuple[str, str]:
    for prefix, wing, room in mappings:
        if rel_path.startswith(prefix):
            return wing, room
    return default_wing, default_room


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
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.config import load_config

    config = load_config(args.config)
    adapter = MarkdownAdapter()
    chunks = adapter.fetch(config)

    print(f"Found {len(chunks)} chunks from {config['notes_folder']}")
    if chunks:
        print("\nSample chunk:")
        print(json.dumps(chunks[0], indent=2, default=str))
