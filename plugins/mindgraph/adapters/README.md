# Building a MindGraph Adapter

Adapters translate any note source into the standard chunk format that MindGraph can ingest.

---

## Quickest path: use the build-adapter skill

Open Claude Code in the mindgraph folder and say:

> "Build an adapter for [source]"

Claude will ask guiding questions, research the API, and write the adapter for you.

---

## Manual path

### 1. Create `adapters/your_source.py`

```python
from adapters.base import AdapterBase
from adapters.markdown import _chunk  # reuse chunking logic

class YourSourceAdapter(AdapterBase):
    def fetch(self, config: dict) -> list[dict]:
        # 1. Load credentials from os.environ
        # 2. Fetch content from source (with pagination)
        # 3. Route to wings/rooms using config["wings"]
        # 4. Chunk long texts using _chunk()
        # 5. Return list of chunks
        ...
```

### 2. Every chunk must include

| Field | Type | Example |
|-------|------|---------|
| `text` | str | `"The key activation metric dropped..."` |
| `source_file` | str | `"work/projects/q2.md"` |
| `wing` | str | `"work"` |
| `room` | str | `"projects"` |
| `filed_at` | str (YYYY-MM-DD) | `"2026-05-09"` |

Optional: `title`, `source_url`, `tags`.

### 3. Wing/room routing

Use `config["wings"]` mappings — never hardcode wing or room names:

```python
from adapters.markdown import _build_mappings, _route

def _get_wing_room(self, identifier: str, config: dict) -> tuple[str, str]:
    mappings = _build_mappings(config["wings"])
    default = config["defaults"]
    return _route(identifier, mappings, default["wing"], default["room"])
```

### 4. Chunking

Import and use `_chunk()` from `adapters/markdown.py`:

```python
from adapters.markdown import _chunk

for long_text in documents:
    for chunk_text in _chunk(long_text):
        chunks.append({
            "text": chunk_text,
            ...
        })
```

### 5. Credentials

Load from environment using the inline dotenv loader (see `concept_extractor.py` for the pattern). Never hardcode API keys.

### 6. Add a --test mode

```python
if __name__ == "__main__":
    import argparse, json, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--config", default="config.yml")
    args = parser.parse_args()
    from scripts.config import load_config
    config = load_config(args.config)
    adapter = YourSourceAdapter()
    chunks = adapter.fetch(config)
    print(f"{len(chunks)} chunks")
    if chunks:
        print(json.dumps(chunks[0], indent=2, default=str))
```

### 7. Test it

```bash
python adapters/your_source.py --test --config config.yml
python3 -m pytest tests/ -v
```

### 8. Run ingest

No changes to `ingest.py` needed — just update `config.yml` if your adapter needs additional config keys.

---

## Full contract

See [`docs/adapter-contract.md`](../docs/adapter-contract.md).
