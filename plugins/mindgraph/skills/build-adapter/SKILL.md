---
name: build-adapter
description: Generates a complete MindGraph adapter for any note source. Asks guiding questions, researches the API or file format, and writes a production-ready adapter implementing AdapterBase.
triggers:
  - "build an adapter for [source]"
  - "create a [source] adapter"
  - "add [source] support to MindGraph"
  - "/build-adapter"
---

# build-adapter

Generates a complete, working adapter for any note source. Asks targeted questions, researches the API, and writes `~/.mempalace/adapters/[source].py` implementing `AdapterBase` (the plugin dir is read-only at runtime — never write inside `${CLAUDE_PLUGIN_ROOT}`).

## Steps

### 1. Ask guiding questions (one at a time)

Ask in sequence — wait for each answer:

1. **What is the source?** (e.g. Notion, Bear, Roam Research, a custom API, a folder of files)
2. **File-based or API-based?**
   - File-based: What format? Where are files stored?
   - API-based: Do you have an API docs link? Or should I find them?
3. **Authentication?** (API key, OAuth, no auth, local file access)
4. **What content matters?** (titles, body text, tags, dates, linked pages, comments?)
5. **Any pagination, rate limits, or cursors to handle?**

### 2. Research the API / format

Use `WebSearch` to find official API docs or file format specs. Use `WebFetch` to read relevant pages. Focus on:
- Authentication method
- How to list/fetch all items
- Response shape: where is the text, title, date, tags?
- Pagination: cursor, page number, or offset?
- Rate limits and 429 handling

### 3. Generate the adapter

Write `~/.mempalace/adapters/[source_slug].py` inheriting `AdapterBase`:

```python
from adapters.base import AdapterBase
from adapters.markdown import _chunk  # reuse chunking logic

class [Source]Adapter(AdapterBase):
    SOURCE_TYPE = "[source_slug]"

    def fetch(self, config: dict) -> list[dict]:
        """Returns chunks conforming to the AdapterBase contract."""
        # Load credentials from environment
        # Fetch all items with pagination
        # Chunk long texts using _chunk()
        # Return list of dicts with: text, source_file, wing, room, filed_at
```

Requirements:
- Must inherit `AdapterBase` and implement `fetch()`
- Every chunk must set `wing="inbox"`, `room="general"` — the adapter never
  decides final routing. Wings/rooms are derived later from the concept
  graph (Phase B of ingest) and confirmed by the user; adapters only produce
  provisional inbox chunks.
- `source_file` must be `"<source_slug>:<id>"` (e.g. `"notion:page-abc123"`,
  `"obsidian:daily/2026-07-10.md"`) — a stable, namespaced identifier so
  chunks from different sources never collide.
- Must handle pagination until all items are fetched
- Must handle rate limits (429 → exponential backoff)
- Must parse dates into `YYYY-MM-DD`
- Must chunk long texts using `_chunk()` from `adapters/markdown.py`
- Must load credentials from `~/.mempalace/.env` using the inline dotenv
  loader pattern from `concept_extractor.py`
- Must include a `--test` CLI flag that fetches up to 5 items and prints a sample chunk

### 4. Verify

Run test mode:
```bash
python3 ~/.mempalace/adapters/[source_slug].py --test
```

Fix any errors before reporting done.

### 5. Report

Tell the user:
- Adapter file created: `~/.mempalace/adapters/[source_slug].py`
- Env vars to add to `~/.mempalace/.env`
- How to ingest: re-run `/mindgraph-setup` or `ingest.py` (no other changes needed)
- Any limitations discovered (rate limits, content types unavailable, etc.)

## Adapter contract reference

See `docs/adapter-contract.md` for the full chunk schema and chunking guidelines.
See `adapters/markdown.py` for a reference implementation.
