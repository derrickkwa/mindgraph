---
name: brain-retrieve
description: Unified retrieval across semantic search (ChromaDB) and concept graph (KG). Deduplicates by source_file, ranks by relevance, surfaces wiki pages when they exist. Single entry point for all knowledge retrieval.
triggers:
  - "what do I have on [topic]"
  - "what do my notes say about [topic]"
  - "check my notes for [topic]"
  - "any notes about [topic]"
  - "search mempalace [topic]"
  - "brain-retrieve [topic]"
  - "retrieve [topic]"
---

# brain-retrieve

Unified knowledge retrieval combining semantic search and concept graph traversal. Returns deduplicated, ranked results from both sources plus a wiki page reference if one exists.

## When to use

Use brain-retrieve for substantive topics where cross-domain connections matter. Use `mempalace_search` directly (scoped) for targeted lookups with a known wing + room.

## Steps

### 1. Check wiki first

Check `_wiki/index.md` for a matching page. If one exists, read it via the Read tool and use it as primary context.

### 2. KG concept lookup

```python
import sqlite3, sys
sys.path.insert(0, "${CLAUDE_PLUGIN_ROOT}/scripts")  # use the data-home resolver, not a hardcoded path
from paths import kg_db_path
conn = sqlite3.connect(str(kg_db_path()))
conn.row_factory = sqlite3.Row
query_term = "[USER_QUERY_NORMALISED]"  # lowercase, hyphenated

concepts = conn.execute(
    "SELECT name FROM entities WHERE type='concept' AND name LIKE ? ORDER BY name LIMIT 5",
    (f"%{query_term}%",)
).fetchall()
concept_names = [r["name"] for r in concepts]

if concept_names:
    rows = conn.execute(
        """SELECT DISTINCT t.source_file, t.source_closet as wing
           FROM triples t
           WHERE t.object=? AND t.predicate='expresses' AND t.valid_to IS NULL""",
        (concept_names[0],)
    ).fetchall()
    kg_sources = [{"source_file": r["source_file"], "wing": r["wing"]} for r in rows]
else:
    kg_sources = []
conn.close()
```

### 3. Semantic search

Call `mcp__mempalace__mempalace_search` with `limit=10`. Scope by wing if query has a clear domain.

### 4. Deduplicate and rank

Combine KG sources and semantic results, deduplicate by `source_file`. Priority:
1. Wiki page (always first)
2. KG + semantic match (appears in both)
3. Semantic only (strong similarity)
4. KG only (structural match)

### 5. Present results

```
## Retrieval: [query]

**Top sources** (N unique):
1. [wing/source_file] (date) — one-sentence summary
2. ...

**Cross-domain signal:** [if concept appears in 3+ wings, note it]
```

Weave findings into your response — don't dump raw chunks.

### 6. Note synthesis gaps

If a concept has 20+ KG sources but no wiki page, note: "Worth synthesising — [N] sources but no wiki page yet."

### Prior conclusions (memory wing)

Run one extra scoped search: `mempalace_search(query, wing="memory", limit=5)`. These are Claude's own saved conclusions from Claude Code memory, not notes. Show them in a separate **Prior conclusions** block; never merge them into ranking, dedup, or the FORK gate. For each hit, `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/belief_ledger.py --by-memory-file <filename>` — if the entry has a `revised` history line, add "revised YYYY-MM-DD".

### FORK — counter-pressure

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/consensus_gate.py --query "<the user's query>"
```

If `is_tight` is false, stop. Otherwise resolve a concept key (matched KG concept name, else the topic slugified) and check `belief_ledger.py --get "<key>"`; if `in_cooldown`, stop. Otherwise read the retrieved notes: only if they share a *stance* (not merely a topic), add exactly one line — `⚠ Your notes all lean [X]. Strongest case against: [one sentence].` — then `belief_ledger.py --log-surfaced --concept '<key>' --stance '<X>' --counter '<case>' --belief '<belief>'` (single-quote arguments; `$` is otherwise lost).

Ledger questions: "what have I changed my mind about" → `--list flipped`; "what do I hold but never tested" → `--list untested`; a belief's history → `--history '<key>'`.

## Files

- `_wiki/` — synthesised pages (check first)
- `palace_dir()` (via `scripts/paths.py`) — ChromaDB semantic search, under `$MINDGRAPH_HOME` (defaults to `~/.mempalace/palace`)
- `kg_db_path()` (via `scripts/paths.py`) — concept graph, under `$MINDGRAPH_HOME` (defaults to `~/.mempalace/knowledge_graph.sqlite3`)
