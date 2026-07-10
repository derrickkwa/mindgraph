# MindGraph

A Claude Code plugin second brain, built on [Mempalace](https://github.com/mempalace/mempalace).

Point it at your notes and get a fully operational AI-retrievable knowledge system — semantic search, concept graph, and wiki synthesis — organized into wings and rooms that are *derived from your own notes*, not folders you had to define up front.

---

## What problem this solves

Most "second brain" setups give you a place to store notes. MindGraph gives Claude Code a way to *think with* them.

The gap it closes: you can have thousands of notes and Claude still can't find the right one, because keyword search misses meaning and Claude has no knowledge of the connections between your ideas. MindGraph fixes this by running your notes through a concept extraction pipeline that builds a knowledge graph on top of semantic search — so Claude can traverse related ideas, not just match strings.

The other gap: most systems require your notes to live in a specific app, or require you to hand-design a folder structure before you can ingest anything. MindGraph uses an abstract adapter layer (ships with markdown, Obsidian, Notion, and Apple Notes; extend via the `build-adapter` skill for anything else), and it figures out your wings and rooms *from the concepts in your notes* after ingest, instead of asking you to pre-declare them.

---

## Install

Inside Claude Code:

```
/plugin marketplace add derrickkwa/mindgraph
/plugin install mindgraph@mindgraph
/mindgraph-setup
```

`/mindgraph-setup` installs dependencies, connects your note sources
(Obsidian, Notion, Apple Notes, or a custom source), ingests your notes,
and proposes a set of "wings" derived from the concepts in your own notes —
which you confirm. Everything lives under `~/.mempalace`. Update anytime with
`/plugin update mindgraph`.

**Want to hack the code?** Just clone this repo and wire the skills/scripts in
by hand — the same way you install any loose skill.

---

## What it does

MindGraph sits on top of Mempalace and adds:

- **Abstract adapter layer** — ingest notes from any source; ships with markdown, Obsidian, Notion, and Apple Notes, extend via the `build-adapter` skill
- **Concept extraction pipeline** — automatically identifies abstract themes across your notes and maps them into a knowledge graph
- **Concept-derived wings** — after your first ingest, an LLM call proposes a nested wing→room tree from the concepts actually present in your notes; you confirm it, then notes are filed by concept overlap — no folder mapping to hand-maintain
- **Cross-domain connection** — the graph links ideas across unrelated domains, surfacing patterns your notes share but you haven't noticed
- **Wiki synthesis layer** — Claude can synthesize distilled concept pages from multiple notes, stored in `_wiki/` as permanent, queryable knowledge
- **Skills** — `brain-ingest`, `brain-retrieve`, `brain-lint`, `build-adapter`, `mindgraph-setup`

---

## How it improves on standard Mempalace

[Mempalace](https://github.com/mempalace/mempalace) is the storage and retrieval engine — ChromaDB for semantic search, SQLite for the knowledge graph. MindGraph is the layer you actually live in:

| | Mempalace | MindGraph |
|--|-----------|-----------|
| Ingestion | Manual chunk insertion | Full pipeline: adapters → chunking → concept extraction → KG |
| Source support | Any (manual) | Plug-in adapters (markdown, Obsidian, Notion, Apple Notes); `build-adapter` skill generates new ones live |
| Wing/room structure | You define it yourself | Proposed from your notes' own concepts after ingest, then you confirm it |
| Concept graph | You write entities/triples | Auto-extracted from your notes via Gemini or Claude API |
| Retrieval | Raw MCP tool calls | `brain-retrieve` skill: wiki → KG traversal → semantic search → deduped results |
| Maintenance | None built in | `brain-lint` audits concept coverage and surfaces synthesis candidates |
| Setup | Manual config | `/mindgraph-setup` — one guided run inside Claude Code |

Mempalace handles the hard storage and search problems. MindGraph handles everything else.

---

## How it works

```
Your notes (any source)
    ↓
Source Adapter               adapters/markdown.py, obsidian.py, notion.py,
                              apple_notes.py — or a custom one from build-adapter
    ↓ provisional chunks [{text, wing="inbox", room="general", source_file, filed_at}]
Ingest Pipeline — Phase A     scripts/ingest.py
    ├── ChromaDB              semantic vector search via Mempalace
    └── Concept Extractor     scripts/concept_extractor.py
            ↓ (Gemini or Claude API — no SDK, pure urllib)
        Knowledge Graph       SQLite via Mempalace KG tools
            ↓
Ingest Pipeline — Phase B     scripts/wing_deriver.py (`ingest.py --derive-wings`)
    One LLM call proposes a nested wing→room tree from the concept vocabulary.
    You review and confirm (rename / merge / split) inside /mindgraph-setup.
            ↓
Ingest Pipeline — Phase C     `ingest.py --assign-wings`
    Every chunk is reassigned from inbox/general to its confirmed wing/room
    by deterministic concept overlap.
            ↓
Claude Code + skills
    brain-retrieve             wiki → KG → semantic search → ranked, deduped
    brain-ingest                add notes mid-conversation
    brain-lint                  graph health, synthesis candidates
    build-adapter                generate new source adapters, live
            ↓
_wiki/                         synthesized concept pages (permanent, queryable)
```

### Wings and rooms are derived, not declared

There is no folder-to-wing config to maintain. Every adapter emits chunks into
a single provisional `inbox` wing (`room="general"`). Once your notes are
ingested and their concepts extracted, one LLM call groups the concept
vocabulary into 5–9 wings, each with 2–4 rooms, using the language your own
notes actually use. You confirm, rename, merge, or split that tree during
`/mindgraph-setup`, and each note is then filed into its final wing/room by
concept overlap with the confirmed tree — a deterministic assignment, not
another LLM call per note.

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

The vocabulary grows with your notes. The more you ingest, the richer the graph — and the more specific the next wing proposal will be if you re-derive it.

---

## Requirements

- Python 3.11+
- Claude Code
- At least one API key: `GEMINI_API_KEY` or `ANTHROPIC_API_KEY`

---

## Where your data lives

All data — the palace (ChromaDB + SQLite), `config.yml`, `.env`, and any
adapters you build with `build-adapter` — lives under `~/.mempalace`. The
plugin code itself (`${CLAUDE_PLUGIN_ROOT}`) is read-only at runtime; nothing
is ever written back into the plugin directory.

---

## Adding a new adapter

Ask Claude in Claude Code:

> "Build an adapter for Notion"
> "Create a Bear adapter"
> "Add Roam Research support to MindGraph"

The `build-adapter` skill will ask guiding questions about the source, research the API, and write a complete working adapter conforming to the `AdapterBase` contract to `~/.mempalace/adapters/[source].py`. Every adapter — pre-built or generated — emits chunks with `wing="inbox"`, `room="general"`; final routing happens later, in the wing-derivation step above.

Or build one manually — see [`plugins/mindgraph/adapters/README.md`](plugins/mindgraph/adapters/README.md).

---

## Skills

| Skill | What it does |
|-------|-------------|
| `mindgraph-setup` | First-run setup: installs deps, connects sources, ingests, derives + confirms wings |
| `brain-ingest` | Add a note or passage to your second brain mid-conversation |
| `brain-retrieve` | Deep retrieval: wiki → KG traversal → semantic search → ranked results |
| `brain-lint` | Audit your concept graph — coverage gaps, synthesis candidates, orphaned chunks |
| `build-adapter` | Generate a new source adapter with guided questions + API research |

Skills ship inside the plugin (`plugins/mindgraph/skills/`) and are available automatically once the plugin is installed.

---

## Wiki synthesis

The `_wiki/` directory holds synthesized concept pages. These are different from raw notes — they're distillations Claude writes from multiple sources, representing a concept as it appears across your entire knowledge base.

To create one:

> "Synthesize [concept] from my notes"

Claude runs `brain-retrieve`, identifies the pattern, and writes a structured page to `_wiki/[concept].md`. Future retrievals check the wiki first — so the page acts as permanent, queryable knowledge that gets richer over time.

---

## Development

If you're hacking on MindGraph itself (not just using it), set
`MINDGRAPH_HOME` to a disposable directory before running anything — scripts
and tests default to `~/.mempalace`, and you don't want a dev run touching a
real store:

```bash
export MINDGRAPH_HOME=$(mktemp -d)
cd plugins/mindgraph
python3 -m pytest tests/ -v
```

Never run dev/test commands without `MINDGRAPH_HOME` set — the plugin should
never touch a real `~/.mempalace` implicitly.

---

## License

MIT
