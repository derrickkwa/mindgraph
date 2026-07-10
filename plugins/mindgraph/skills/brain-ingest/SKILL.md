---
name: brain-ingest
description: Ingest any text input into the second brain — chunks it, stores in ChromaDB (semantic search), extracts abstract concepts, writes concept nodes + expresses triples to the KG. Universal entry point for notes, pastes, articles, anything.
triggers:
  - "ingest this"
  - "add this to my brain"
  - "/brain-ingest"
  - "save this to mempalace"
  - "store this note"
---

# brain-ingest

Universal ingest pipeline for the second brain. Any text in → concept graph + semantic search out.

## What this does

1. Chunks the input (~400 tokens per chunk, overlap ~50 tokens)
2. Adds each chunk to ChromaDB via `mempalace_add_drawer`
3. Fetches current concept vocabulary from the KG
4. Runs concept extraction via `skills/brain-ingest/scripts/concept_extractor.py`
5. Writes concept nodes + "expresses" triples to the KG

## Inputs

| Argument | Required | Notes |
|----------|----------|-------|
| text | Yes | Raw text to ingest |
| wing | Yes | Mempalace wing (matches a wing in your config.yml) |
| room | Yes | Room within the wing |
| source_file | Optional | Stable identifier for the source. Defaults to wing/room/date |

## Freeform paste mode

When the user pastes text without specifying wing/room, determine them from content:
- Work topics, projects, meetings → `wing` matching your work wing
- Personal notes, journal → `wing` matching your personal wing
- Unclear → ask: "Where should I file this: [option A] or [option B]?"

## Steps

### 1. Chunk the input

Split text into ~1600 char chunks (min 400 chars). Overlap: retain last ~200 chars of previous chunk at start of next. Single chunk if under 600 chars.

Chunk ID: `{wing}_{room}_{sha256(chunk_text)[:24]}`

### 2. Add chunks to ChromaDB

For each chunk call `mcp__mempalace__mempalace_add_drawer`:
```
wing: [wing]
room: [room]
content: [chunk text]
source_file: [source_file]
```

### 3. Fetch concept vocabulary

```python
import sqlite3, sys
sys.path.insert(0, "scripts")  # repo-root-relative; use the data-home resolver, not a hardcoded path
from paths import kg_db_path
conn = sqlite3.connect(str(kg_db_path()))
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT name FROM entities WHERE type='concept' ORDER BY name").fetchall()
vocabulary = [r["name"] for r in rows]
conn.close()
```

### 4. Run concept extraction

```bash
echo '[{"id":"...","text":"...","source_file":"...","wing":"...","room":"..."}]' > /tmp/brain_ingest_chunks.json

python3 skills/brain-ingest/scripts/concept_extractor.py \
  --chunks-file /tmp/brain_ingest_chunks.json \
  > /tmp/brain_ingest_results.json
```

### 5. Write to KG

```python
import json, sys
sys.path.insert(0, "scripts")  # repo-root-relative; use the data-home resolver, not a hardcoded path
from paths import kg_db_path
from mempalace.knowledge_graph import KnowledgeGraph
from datetime import date

with open("/tmp/brain_ingest_results.json") as f:
    output = json.load(f)

kg = KnowledgeGraph(db_path=str(kg_db_path()))
today = date.today().isoformat()

for result in output["results"]:
    source_file = result["source_file"]
    wing = result["wing"]
    for concept in result["matched_concepts"] + result["new_concepts"]:
        kg.add_entity(concept, "concept")
        kg.add_triple(
            subject=source_file, predicate="expresses", obj=concept,
            valid_from=today, source_closet=wing, source_file=source_file,
        )
kg.close()
```

### 6. Report

"Ingested [N] chunks → [wing]/[room]. Concepts linked: [list]."

## Files

- `skills/brain-ingest/scripts/concept_extractor.py` — concept extraction (Gemini or Claude API)
- `skills/brain-ingest/scripts/batch_ingest.py` — bulk ingest with checkpoint
- `scripts/ingest.py` — CLI entry point
