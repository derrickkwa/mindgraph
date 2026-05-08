# MindGraph

A Claude Code second brain template built on [Mempalace](https://github.com/mempalace/mempalace).

Clone it, point it at your notes, and get a fully operational AI-retrievable knowledge system — semantic search, concept graph, and wiki synthesis — in under 15 minutes.

---

## What it does

MindGraph sits on top of Mempalace and adds:

- **Abstract adapter layer** — ingest notes from any source (ships with plain markdown)
- **Concept extraction pipeline** — automatically maps abstract themes across your notes using Gemini or Claude API
- **Knowledge graph** — finds connections between ideas across domains
- **Claude Code skills** — `brain-ingest`, `brain-retrieve`, `brain-lint`, `build-adapter`
- **`build-adapter` skill** — ask Claude to generate a new adapter for any note source

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
1. Install Mempalace if not already installed
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

Edit `config.yml` to define your wings (top-level categories) and map them to folders in your notes folder.

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

**`llm_provider: auto`** uses Gemini if `GEMINI_API_KEY` is set, otherwise falls back to Claude API. No extra SDK required — both providers are called via standard `urllib`.

---

## Adding a new adapter

Ask Claude in Claude Code:

> "Build an adapter for Notion"  
> "Create a Bear adapter"  
> "Add Roam Research support to MindGraph"

The `build-adapter` skill will ask guiding questions, research the API, and write a complete working adapter.

Or build one manually — see [`adapters/README.md`](adapters/README.md).

---

## How it works

```
Your notes (any source)
    ↓
Source Adapter  (adapters/markdown.py or custom)
    ↓ chunks [{text, wing, room, source_file, filed_at}]
Batch Ingest Pipeline
    ├── ChromaDB  (semantic search via Mempalace)
    └── Concept Extractor → Knowledge Graph
            ↓
Claude Code + skills
    (brain-retrieve, brain-ingest, brain-lint)
```

---

## Running tests

```bash
python3 -m pytest tests/ -v
```

---

## Personalize CLAUDE.md

After setup, edit `CLAUDE.md` to add context about yourself — your role, active projects, and how your wings are structured. This is what makes Claude's retrieval feel personal rather than generic.

---

## License

MIT
