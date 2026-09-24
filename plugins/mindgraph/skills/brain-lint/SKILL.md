---
name: brain-lint
description: Concept graph health review. Surfaces noise concepts, duplicate candidates, synthesis gaps, and orphaned wiki pages for human review.
triggers:
  - "brain-lint"
  - "lint the concept graph"
  - "concept graph health"
  - "clean up the knowledge graph"
  - "which concepts should I synthesize next"
  - "what's stale in the wiki"
---

# brain-lint

Concept graph maintenance. Runs `brain_lint.py`, presents findings grouped by action type, and handles user confirmations for merges and prunes.

## When to use

- After a large batch ingest
- Before a synthesis session (to identify best candidates)
- When the graph feels noisy or duplicative

## Steps

### 1. Run the lint script

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/brain-lint/scripts/brain_lint.py \
  --wiki-dir _wiki \
  --top-gaps 20 \
  --min-links 3 \
  2>/dev/null
```

Parse the JSON output. Extract all four finding categories.

### 2. Present findings

**Graph health:** total concepts | viable (≥3 links) | noise | wiki pages | gaps | orphans

**Section A — Synthesis gaps** (high-link concepts with no wiki page)
Top 10 by link count. Format: `concept-name (N sources)`. Ask: "Want me to synthesize any of these?"

**Section B — Duplicate candidates**
Top 8 pairs with similarity score. Suggest canonical name. Ask user to confirm merges.

**Section C — Orphaned wiki pages**
List all. Domain overview pages are expected orphans.

**Section D — Noise summary**
Count + 10-item sample only.

### 3. Handle confirmations

**Merge:**
```python
import sqlite3, sys
from datetime import date
sys.path.insert(0, "${CLAUDE_PLUGIN_ROOT}/scripts")  # use the data-home resolver, not a hardcoded path
from paths import kg_db_path
conn = sqlite3.connect(str(kg_db_path()))
keep, remove = "canonical-concept", "duplicate-concept"
conn.execute("UPDATE triples SET object=? WHERE object=? AND predicate='expresses'", (keep, remove))
conn.execute("UPDATE entities SET valid_to=? WHERE name=? AND type='concept'", (date.today().isoformat(), remove))
conn.commit()
conn.close()
```

**Prune:**
```python
import sqlite3, sys
from datetime import date
sys.path.insert(0, "${CLAUDE_PLUGIN_ROOT}/scripts")  # use the data-home resolver, not a hardcoded path
from paths import kg_db_path
conn = sqlite3.connect(str(kg_db_path()))
concept = "[CONCEPT_TO_PRUNE]"
conn.execute("UPDATE entities SET valid_to=? WHERE name=? AND type='concept'", (date.today().isoformat(), concept))
conn.execute("UPDATE triples SET valid_to=? WHERE object=? AND predicate='expresses'", (date.today().isoformat(), concept))
conn.commit()
conn.close()
```

### 4. Memory lint (Claude Code memory)

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/brain-lint/scripts/memory_lint.py --check-sync
```

Per project: report errors first (`index_size` → move non-rule lines into a hub; `unreachable` → add the file's line to a hub; `near_match_link` → offer `--fix-near-matches`), then warnings (`dangling_link` list only; `sync_missing`/`sync_orphan`/`sync_vector_missing` → run `memory_sync.py --all`). Method: `docs/memory-index.md` in the MindGraph repo (https://github.com/derrickkwa/mindgraph/blob/main/docs/memory-index.md).

## Files

- `skills/brain-lint/scripts/brain_lint.py` — the lint script
- `skills/brain-lint/scripts/memory_lint.py` — Claude Code memory index health check
- `_wiki/` — wiki pages checked for orphans and gaps
