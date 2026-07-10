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
python3 skills/brain-lint/scripts/brain_lint.py \
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
import sqlite3, os
from datetime import date
conn = sqlite3.connect(os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3"))
keep, remove = "canonical-concept", "duplicate-concept"
conn.execute("UPDATE triples SET object=? WHERE object=? AND predicate='expresses'", (keep, remove))
conn.execute("UPDATE entities SET valid_to=? WHERE name=? AND type='concept'", (date.today().isoformat(), remove))
conn.commit()
conn.close()
```

**Prune:**
```python
import sqlite3, os
from datetime import date
conn = sqlite3.connect(os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3"))
concept = "[CONCEPT_TO_PRUNE]"
conn.execute("UPDATE entities SET valid_to=? WHERE name=? AND type='concept'", (date.today().isoformat(), concept))
conn.execute("UPDATE triples SET valid_to=? WHERE object=? AND predicate='expresses'", (date.today().isoformat(), concept))
conn.commit()
conn.close()
```

## Files

- `skills/brain-lint/scripts/brain_lint.py` — the lint script
- `_wiki/` — wiki pages checked for orphans and gaps
