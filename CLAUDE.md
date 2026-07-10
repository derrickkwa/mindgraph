# MindGraph — Claude Instructions

This file is autoloaded by Claude Code. It configures how Claude uses your second brain.

---

## Your Second Brain

Your notes are stored in Mempalace — a local semantic search + knowledge graph system.

**Mempalace tools available:**
- `mcp__mempalace__mempalace_search` — semantic search over your notes
- `mcp__mempalace__mempalace_kg_query` — query the concept graph
- `mcp__mempalace__mempalace_add_drawer` — add new notes
- `mcp__mempalace__mempalace_kg_add` — add to knowledge graph

---

## Default Retrieval Behavior

**Retrieve first, respond second.** For any substantive question — strategy, ideas, projects, decisions — search your notes before forming a response.

**Two speeds:**
- **Pulse** (default): a quick `mempalace_search` with `limit=5`. Use reflexively for most topics.
- **Full brain-retrieve** (invoke the skill): wiki check → KG lookup → semantic search → ranked results. Use when depth matters.

**When NOT to retrieve:**
- Mechanical requests (file edits, code, formatting)
- Follow-up turns where you already retrieved on this topic

---

## Wing/Room Routing

Your notes are organized into **wings** (top-level domains) and **rooms** (sub-topics). These are **derived from the concepts in your notes**, not declared by hand: `/mindgraph-setup` builds the concept graph, proposes a wing→room tree, you confirm it, and each note is assigned by concept overlap. The confirmed tree is stored in `config.yml`; re-derive later with `ingest.py --derive-wings`.

For scoped lookups, pass `wing` and `room` to `mempalace_search`:
```
mcp__mempalace__mempalace_search(query="...", wing="work", room="projects", limit=5)
```

For broad searches, omit wing/room.

---

## Citation

When referencing notes, cite inline: `(note, YYYY-MM-DD)` or `(undated note)`. Keep it minimal — bracket format only, no lengthy attribution prose.

---

## Skills Available

- `mindgraph-setup` — first-run setup: connect sources, ingest, derive + confirm your wings
- `brain-ingest` — add text to your second brain
- `brain-retrieve` — deep retrieval with KG traversal
- `brain-lint` — concept graph health review
- `build-adapter` — generate a new source adapter

---

## TODO: Personalize This File

Replace this section with context specific to you:

```
# About Me
# [Your name, role, what you work on day-to-day]

# Wing Structure
# [Brief description of your wings and what goes in each]

# Key Projects
# [Active projects Claude should be aware of]

# Working Preferences
# [How you like responses formatted, any domain-specific context]
```
