# MindGraph

A Claude Code second brain template built on [Mempalace](https://github.com/mempalace/mempalace).

Clone it, point it at your notes, and get a fully operational AI-retrievable knowledge system — semantic search, concept graph, and wiki synthesis — in under 15 minutes.

---

## What problem this solves

Most "second brain" setups give you a place to store notes. MindGraph gives Claude Code a way to *think with* them.

The gap it closes: you can have thousands of notes and Claude still can't find the right one, because keyword search misses meaning and Claude has no knowledge of the connections between your ideas. MindGraph fixes this by running your notes through a concept extraction pipeline that builds a knowledge graph on top of semantic search — so Claude can traverse related ideas, not just match strings.

The other gap: most systems require your notes to live in a specific app. MindGraph uses an abstract adapter layer, so it works with plain markdown today and any source you write an adapter for tomorrow (Notion, Bear, Obsidian, Roam, Apple Notes, etc).

---

## What it does

MindGraph sits on top of Mempalace and adds:

- **Abstract adapter layer** — ingest notes from any source; ships with plain markdown, extend via the `build-adapter` skill
- **Concept extraction pipeline** — automatically identifies abstract themes across your notes and maps them into a knowledge graph
- **Cross-domain connection** — the graph links ideas across unrelated domains, surfacing patterns your notes share but you haven't noticed
- **Wiki synthesis layer** — Claude can synthesize distilled concept pages from multiple notes, stored in `_wiki/` as permanent, queryable knowledge
- **Four Claude Code skills** — `brain-ingest`, `brain-retrieve`, `brain-lint`, `build-adapter`

---

## How it improves on standard Mempalace

[Mempalace](https://github.com/mempalace/mempalace) is the storage and retrieval engine — ChromaDB for semantic search, SQLite for the knowledge graph. MindGraph is the layer you actually live in:

| | Mempalace | MindGraph |
|--|-----------|-----------|
| Ingestion | Manual chunk insertion | Full pipeline: adapters → chunking → concept extraction → KG |
| Source support | Any (manual) | Plug-in adapters; `build-adapter` skill generates new ones |
| Concept graph | You write entities/triples | Auto-extracted from your notes via Gemini or Claude API |
| Retrieval | Raw MCP tool calls | `brain-retrieve` skill: wiki → KG traversal → semantic search → deduped results |
| Maintenance | None built in | `brain-lint` audits concept coverage and surfaces synthesis candidates |
| Claude context | CLAUDE.md you write yourself | Pre-built template with retrieval behavior, wing routing, citation format |

Mempalace handles the hard storage and search problems. MindGraph handles everything else.

---

## Architecture

```
Your notes (any source)
    ↓
Source Adapter              adapters/markdown.py  ← or custom
    ↓ chunks [{text, wing, room, source_file, filed_at}]
Batch Ingest Pipeline       scripts/ingest.py
    ├── ChromaDB            semantic vector search via Mempalace
    └── Concept Extractor   scripts/concept_extractor.py
            ↓ (Gemini or Claude API — no SDK, pure urllib)
        Knowledge Graph     SQLite via Mempalace KG tools
            ↓
Claude Code + skills
    brain-retrieve          wiki → KG → semantic search → ranked, deduped
    brain-ingest            add notes mid-conversation
    brain-lint              graph health, synthesis candidates
    build-adapter           generate new source adapters
            ↓
_wiki/                      synthesized concept pages (permanent, queryable)
```

### Retrieval order

When you ask Claude something substantive, `brain-retrieve` runs three passes:

1. **Wiki check** — if a synthesized page exists for the topic, read it first. Wiki pages are distilled from multiple notes and are richer than any single source.
2. **KG concept lookup** — find the concept node in the graph, traverse related concepts, pull the linked chunks.
3. **Semantic search** — broad vector search over all chunks for anything the graph didn't surface.

Results are deduplicated by source file and ranked by relevance before Claude reads them.

### Concept extraction

After chunking your notes, the pipeline calls your LLM provider with each batch:

- Matches chunks against an existing concept vocabulary (concepts already in your graph)
- Identifies genuinely new concepts and adds them to the vocabulary
- Writes entity nodes and `expresses` triples to the knowledge graph
- Processes in resumable batches — safe to interrupt and restart

The vocabulary grows with your notes. The more you ingest, the richer the graph.

---

## Requirements

- Python 3.11+
- Claude Code
- At least one API key: `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`

---

## Setup

```bash
git clone https://github.com/derrickkwa/mindgraph
cd mindgraph
python3 scripts/setup.py
```

`setup.py` will:
1. Install Mempalace if not already installed (`uv tool install mempalace`)
2. Initialize your palace at `~/.mempalace`
3. Walk you through creating `config.yml`
4. Validate your API keys

Then run your first ingest:

```bash
python3 scripts/ingest.py
```

Open Claude Code in the `mindgraph` folder and try:

> "What do my notes say about [any topic]?"

---

## Configuration

Edit `config.yml` to define your wings (top-level categories) and map them to folders in your notes:

```yaml
notes_folder: ~/Documents/my-notes
llm_provider: auto  # auto | gemini | claude

wings:
  - name: work
    rooms:
      projects: [work/projects/]
      meetings: [work/meetings/]
  - name: personal
    rooms:
      journal: [personal/journal/]

defaults:
  wing: misc
  room: general
```

Wings are how Mempalace organizes your knowledge — think of them as top-level domains (work, personal, research). Rooms are subcategories within each wing.

**`llm_provider: auto`** uses Gemini if `GEMINI_API_KEY` is set, otherwise falls back to Claude API. No extra SDK required — both providers use standard `urllib`.

---

## Ingest flags

```bash
python3 scripts/ingest.py                        # full ingest
python3 scripts/ingest.py --dry-run              # validate without writing anything
python3 scripts/ingest.py --source ~/other/path  # override notes_folder
python3 scripts/ingest.py --status               # show current palace stats
```

`--dry-run` is useful for testing a new adapter or config change before committing to a full ingest.

---

## Adding a new adapter

Ask Claude in Claude Code:

> "Build an adapter for Notion"  
> "Create a Bear adapter"  
> "Add Roam Research support to MindGraph"

The `build-adapter` skill will ask guiding questions about the source, research the API, and write a complete working adapter conforming to the `AdapterBase` contract.

Or build one manually — see [`adapters/README.md`](adapters/README.md).

---

## Skills

| Skill | What it does |
|-------|-------------|
| `brain-ingest` | Add a note or passage to your second brain mid-conversation |
| `brain-retrieve` | Deep retrieval: wiki → KG traversal → semantic search → ranked results |
| `brain-lint` | Audit your concept graph — coverage gaps, synthesis candidates, orphaned chunks |
| `build-adapter` | Generate a new source adapter with guided questions + API research |

Skills live in `skills/` and are autoloaded by Claude Code via `CLAUDE.md`.

---

## Wiki synthesis

The `_wiki/` directory holds synthesized concept pages. These are different from raw notes — they're distillations Claude writes from multiple sources, representing a concept as it appears across your entire knowledge base.

To create one:

> "Synthesize [concept] from my notes"

Claude runs `brain-retrieve`, identifies the pattern, and writes a structured page to `_wiki/[concept].md`. Future retrievals check the wiki first — so the page acts as permanent, queryable knowledge that gets richer over time.

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

---

## Personalize CLAUDE.md

After setup, edit `CLAUDE.md` to add context about yourself — your role, active projects, and how your wings are structured. The more specific you make it, the more Claude's retrieval will feel like talking to someone who actually knows your work.

---

## License

MIT
