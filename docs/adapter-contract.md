# Adapter Contract

Every MindGraph source adapter inherits from `AdapterBase` and implements `fetch()`.

## Required chunk fields

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | The chunk content. Must not be empty. |
| `source_file` | str | Stable identifier for the source (relative path or URL). |
| `wing` | str | Mempalace wing (top-level category). |
| `room` | str | Mempalace room within the wing. |
| `filed_at` | str | ISO date the note was written/modified (`YYYY-MM-DD`). |

## Optional chunk fields

| Field | Type | Description |
|-------|------|-------------|
| `title` | str | Human-readable title for the source. |
| `source_url` | str | URL if the source is web-based. |
| `tags` | list[str] | Tags from frontmatter or source metadata. |

## Routing

Wing and room must match entries in the user's `config.yml`. Adapters derive
wing/room from `config.yml` mappings — never hardcode them.

## Test mode

Every adapter should implement a `--test` CLI flag that runs against a small
fixture dataset and prints chunk count + a sample chunk. See `adapters/markdown.py`
for an example.

## Chunking

The adapter is responsible for chunking long documents before returning.
Target: ~400 tokens per chunk (~1600 chars). Overlap: retain last ~200 chars
of the previous chunk at the start of the next to avoid cutting mid-thought.
Short texts under 600 chars: return as a single chunk.
