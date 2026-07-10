# MindGraph: Plugin Install + Intelligent Wings

**Date:** 2026-07-10
**Status:** Approved design, pre-implementation

---

## Problem

MindGraph is a Claude Code second-brain system. Two things make it hard for a normal person to adopt:

1. **Install friction.** Today: `git clone` → `python3 scripts/setup.py`, a wizard that only understands a folder of markdown. There is no path for the note sources people actually use (Notion, Apple Notes), and it assumes comfort with a terminal and a cloned repo.
2. **Wings assume folders.** The markdown adapter routes notes into wings by folder-path prefix. Our own Mempalace worked because our Apple Notes happened to be foldered to match a predefined taxonomy. A stranger with a flat pile of notes gets one useless `misc` wing — even though the concept graph (the actual intelligence) builds fine without folders.

This design ships MindGraph as a **Claude Code plugin** installed and run entirely inside Claude Code, with pre-built adapters for the common sources, and replaces folder-based wing routing with wings/rooms **derived from the concept graph and confirmed by the user**.

---

## Key insight: two layers, only one is "knowledge"

The pipeline already separates two concerns, and this design leans into that separation:

- **Wings / rooms** — coarse storage buckets (`wing`, `room` tags on each chunk). No intelligence. In our system they were a predefined taxonomy filled by folder path.
- **Concepts** — the knowledge graph. `concept_extractor.py` already sends every chunk to an LLM and extracts abstract concepts (`activation-friction`, `feedback-loops`) into KG entity nodes + `expresses` triples. **This needs no folders.** It reads meaning from text.

The concept graph is what makes retrieval smart, and it is folder-free today. Only the wing layer breaks on folderless sources. Since the LLM already reads every chunk during ingest, deriving wings/rooms from the resulting concept graph is nearly free.

---

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Distribution | **Claude Code plugin**; the repo self-hosts as its own marketplace |
| Install path | `/plugin marketplace add` → `/plugin install` → `/mindgraph-setup`, all inside Claude Code |
| Code location | **Plugin-owned** — scripts/skills run from `${CLAUDE_PLUGIN_ROOT}` (read-only) |
| Data location | **All under `~/.mempalace`** (palace, `config.yml`, `_wiki/`, `.env`, checkpoints); `MINDGRAPH_HOME` overrides |
| Updates | `/plugin update` — nothing to re-sync |
| "I want to hack the code" path | Clone the repo directly (like installing skills by hand); not a built feature |
| Setup orchestration | `mindgraph-setup` skill drives setup conversationally; Python scripts do mechanical work |
| Adapter strategy | Pre-built, shipped in plugin (Notion, Obsidian, Apple Notes); "Other" → `build-adapter`, run **live in-setup** |
| Source count | Multiple sources per install |
| Wing/room routing | Derived from concept graph, user-confirmed, assigned by concept overlap |
| Assignment mechanism | Deterministic concept-overlap, two-level (wing then room); no per-note LLM call |
| Folder-based routing | **Removed entirely** — everyone gets concept-derived wings/rooms |
| Rooms | Sub-clusters of a wing's concepts, nested under wings |

---

## Architecture

### Repo → plugin layout

The repo doubles as a marketplace and carries the plugin:

```
mindgraph/                          (the GitHub repo)
├── .claude-plugin/
│   └── marketplace.json            name: mindgraph
└── plugins/
    └── mindgraph/
        ├── .claude-plugin/plugin.json
        ├── skills/
        │   ├── mindgraph-setup/SKILL.md
        │   ├── brain-ingest/ …
        │   ├── brain-retrieve/ …
        │   ├── brain-lint/ …
        │   └── build-adapter/ …
        ├── scripts/                ingest.py, wing_deriver.py, config.py, check_env.py, write_config.py, paths.py
        └── adapters/               base.py, markdown.py, obsidian.py, notion.py, apple_notes.py
```

Skills reference bundled code via `${CLAUDE_PLUGIN_ROOT}` (e.g. `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py`). The plugin cache is read-only; **all writes go to the data home**, never to `${CLAUDE_PLUGIN_ROOT}`.

### Data home

`scripts/paths.py` resolves the data home once: `MINDGRAPH_HOME` env var if set, else `~/.mempalace`. Everything writable lives there:

- `~/.mempalace/palace/` — ChromaDB (existing)
- `~/.mempalace/knowledge_graph.sqlite3` — KG (existing)
- `~/.mempalace/config.yml` — sources + confirmed wing/room tree
- `~/.mempalace/.env` — API keys
- `~/.mempalace/_wiki/` — synthesized pages
- `~/.mempalace/checkpoints/batch_ingest_checkpoint.json` — moved out of the code dir

Set `PYTHONPYCACHEPREFIX` (in the skill's Bash invocations) so Python never tries to write `__pycache__` into the read-only plugin dir.

### Data flow

```
Source(s)  ──adapter──▶  chunks (wing=inbox, namespaced source_file)
                              │
                              ▼
              ChromaDB add  +  concept extraction  ──▶  KG (concepts, expresses triples)
                              │
                              ▼  [setup / on-demand only]
        Phase B: group concept vocabulary into a nested wing→room tree (1 LLM call)
                              │
                              ▼
              User confirms tree  ──▶  ~/.mempalace/config.yml `wings:` (nested `rooms:`)
                              │
                              ▼  [free, deterministic]
        Assign each note: wing by overlap, then room within that wing by overlap
                              │
                              ▼
              update ChromaDB metadata (wing, room) + KG triple source_closet
```

### Component boundaries

**Adapters** (`adapters/*.py`) — one job: fetch + chunk + emit chunks. They no longer assign wings.
- Output chunk schema: `text`, `source_file` (namespaced), `filed_at`, optional `title`, `tags`, `source_url`. `wing` is always the provisional `inbox`; `room` is `general`.
- `source_file` is namespaced by source type to prevent cross-source collisions: `obsidian:work/note.md`, `notion:<page_id>`, `apple_notes:<note_id>`.
- Each adapter keeps a `--test` CLI flag (fetch ≤5 items, print a sample chunk).

**Ingest orchestrator** (`scripts/ingest.py`) — loops over `config.sources`, dispatches each to its adapter, aggregates chunks, then drives `batch_ingest` (Phase A). It does **not** confirm wings — human confirmation lives in the setup skill. `ingest.py --derive-wings` prints the proposed tree (`propose_tree`) as JSON for the skill to present; `ingest.py --assign-wings` applies a confirmed tree from `config.yml`. On routine re-ingest of new notes (wings already confirmed), Phase A runs, then new notes are auto-assigned to the existing tree by overlap with no re-proposal.

**Wing deriver** (new: `scripts/wing_deriver.py`) —
- `propose_tree(kg) -> list[{name, rooms:[{name, concepts}]}]`: reads the concept vocabulary from the KG; one LLM call groups concepts into a nested tree — 5–9 named wings, each sub-divided into named rooms. A wing's concept set is the union of its rooms' concepts. Wings too small to sub-divide get a single `general` room.
- `assign(kg, wings) -> dict[source_file, {wing, room}]`: for each note, tallies its expressed concepts against each wing's concept set → max-overlap wing; then against that wing's rooms → max-overlap room (falls back to the wing's `general` room when no room overlaps). Ties broken by highest summed confidence, then first entry. Pure graph math — no LLM.
- `apply(...)`: writes wing + room back to ChromaDB chunk metadata and the KG triple `source_closet`.

**Setup skill** (new: `skills/mindgraph-setup/SKILL.md`) — orchestrates setup conversationally inside Claude Code; calls the Python helpers for mechanical steps. See Setup flow.

**Setup helpers** (`scripts/`) — small, independently-runnable, testable scripts the skill invokes:
- `paths.py` — resolves the data home.
- `check_env.py` — reports which API keys / dependencies are present.
- `write_config.py` — writes/updates `~/.mempalace/config.yml` (sources, then the confirmed wing/room tree).
- `config.py`, `ingest.py`, `wing_deriver.py` — as above.

### Config schema (v2), at `~/.mempalace/config.yml`

```yaml
sources:
  - {type: obsidian, path: ~/vault}
  - {type: apple_notes}            # macOS only; optional folders: [Work, Personal]
  - {type: notion}                 # token from .env NOTION_TOKEN
llm_provider: auto                 # auto | gemini | claude
wings:                             # empty until Phase B confirmed
  - name: growth
    rooms:
      - {name: acquisition, concepts: [activation-friction, funnel-design]}
      - {name: retention,   concepts: [retention, churn]}
  - name: personal
    rooms:
      - {name: general, concepts: [habit-formation, reflection]}
defaults: {wing: inbox, room: general}
```

A wing's concept set is the union of its rooms' concepts; there is no wing-level `concepts` key. `config.py` accepts v2 (nested wings/rooms). If a legacy v1 config is found (old `notes_folder:` at the repo root), setup offers to import it as `sources: [{type: markdown, path: <notes_folder>}]`. The plain `markdown` adapter is retained as the generic base type (Obsidian is a variant); `markdown` remains a valid config `type` for any folder of `.md` files.

---

## Install

Entirely inside Claude Code (which is a hard prerequisite — MindGraph can't be used without it):

```
/plugin marketplace add derrickkwa/mindgraph
/plugin install mindgraph@mindgraph
/mindgraph-setup
```

`/plugin update mindgraph` pulls new adapters and fixes; user data under `~/.mempalace` is untouched.

**Hack path (advanced, not a built feature):** `git clone derrickkwa/mindgraph` and wire the skills/scripts in by hand, the same way one installs loose skills. No template-copy tooling is shipped.

---

## Setup flow (`mindgraph-setup` skill)

The user runs `/mindgraph-setup`. The skill orchestrates; Python helpers do the mechanical work. Because it runs inside Claude, every step is conversational and Claude troubleshoots errors live.

1. **Preflight** — `check_env.py`: verify Python ≥ 3.11; install Mempalace + deps if missing (`uv tool install mempalace` if `uv` present, else `pip`); ensure `~/.mempalace` and `~/.mempalace/.env` exist.
2. **API key check** — if no `GEMINI_API_KEY`/`ANTHROPIC_API_KEY`, Claude explains how to get one and writes it to `~/.mempalace/.env`.
3. **Source selection** — Claude asks which sources (Obsidian / Notion / Apple Notes / Other), accepts several. Apple Notes only offered on macOS.
4. **Per-source config**
   - Obsidian → ask vault path; validate it exists.
   - Notion → Claude walks the user through creating an internal integration and sharing pages, then captures `NOTION_TOKEN`.
   - Apple Notes → trigger the export once to surface the automation-permission prompt; Claude guides granting it. Optional folder filter.
   - Other → Claude runs the `build-adapter` skill **live** to generate the adapter in-session.
5. **Write config** — `write_config.py` writes `~/.mempalace/config.yml` (sources + empty wings + defaults).
6. **First ingest (Phase A)** — `ingest.py`; builds the concept graph.
7. **Derive + confirm tree (Phase B)** — `ingest.py --derive-wings`; Claude presents the wing→room tree, the user renames / merges / splits / accepts by talking, Claude writes the confirmed tree via `write_config.py`.
8. **Assign (Phase C)** — `ingest.py --assign-wings`; report note counts per wing/room.
9. **Done** — Claude suggests a first retrieval query.

---

## Adapters to build

| Adapter | Mechanism | Notes |
|---------|-----------|-------|
| `obsidian.py` | Extends markdown adapter | Handle `[[wikilinks]]` (record as `tags`/links, strip syntax from text); ignore `.obsidian/`. Path-based. |
| `apple_notes.py` | AppleScript via `osascript` | Export title, body (HTML→text), folder, created/modified. Namespace by note id. macOS-only guard. Guided automation-permission prompt on first run. |
| `notion.py` | Notion API via `urllib` (no SDK) | `POST /v1/search` to list pages/databases; fetch block children for text; paginate via `next_cursor`; 429 → exponential backoff (reuse pattern from `concept_extractor.py`). Bearer token from `NOTION_TOKEN`. |
| Other | Existing `build-adapter` skill | Run **live during setup**; the only path for non-shipped sources. |

`build-adapter` skill must be updated: adapters no longer do wing/room routing (remove that requirement) and write into the plugin's `adapters/` at `${CLAUDE_PLUGIN_ROOT}` is not possible at runtime — a live-generated adapter is written into the data home (`~/.mempalace/adapters/`) and the ingest loader checks there in addition to the bundled adapters.

---

## Error handling

The Python scripts fail loudly with clear messages and exit codes; the `mindgraph-setup` skill catches these and troubleshoots with the user conversationally (its advantage over a rigid wizard).

- **Preflight:** missing Python ≥ 3.11 → clear message + install link; dependency install failure → surface the command that failed.
- **No API key:** ingest refuses to run with an explicit message (both concept extraction and wing derivation need it); the skill helps the user obtain and place a key.
- **Invalid Notion token:** `notion.py --test` fails fast; the skill surfaces the error and re-prompts.
- **Apple Notes permission denied:** the export script emits a recognizable automation-permission error; the skill walks the user through granting access to Notes, then retries.
- **Wing proposal fails** (LLM error / unparseable): fall back to a single `inbox` wing with a `general` room; the user can re-run `ingest.py --derive-wings` later.
- **Rate limits:** already handled by backoff in `concept_extractor.py`; the Notion adapter mirrors it.

---

## Testing

Unit tests on logic that can break silently:
- `paths.py` — data-home resolution (`MINDGRAPH_HOME` override vs default).
- `config.py` v2 loader (nested wings/rooms) + v1→v2 migration.
- `write_config.py` round-trips a confirmed wing/room tree.
- `source_file` namespacing per adapter.
- `wing_deriver.assign` — deterministic two-level overlap (wing then room), including tie-breaking and the `general`-room fallback, fixture-driven with a stub KG.
- `wing_deriver.propose_tree` — parses a nested tree from a mocked LLM provider.

Lighter fixture smoke tests for adapters:
- Obsidian on a fixture vault (wikilinks, `.obsidian/` ignored).
- Notion with a mocked API response (search + block children).
- Apple Notes with mocked `osascript` output.

Per project convention, adapters are simple data-mapping; verify with fixture runs rather than exhaustive TDD. The wing-assignment, config, and path logic get real unit tests.

---

## Out of scope

- A built template-copy / scaffolding path (advanced users clone the repo directly).
- A terminal bootstrap (`install.sh`) — the plugin is the only supported install.
- Publishing to the official/global marketplace (self-hosted repo marketplace is enough; can submit later).
- Incremental / delta re-ingest optimizations beyond the existing checkpoint resume.
- Deeper-than-two-level hierarchy (sub-rooms); wing → room is the ceiling.

---

## Implementation phases (for the plan)

1. **Repo → plugin layout** — `marketplace.json`, `plugin.json`, move skills/scripts/adapters under `plugins/mindgraph/`; verify `/plugin install` works.
2. **Data-home refactor** — `paths.py`; route `config.yml`, `.env`, `_wiki/`, checkpoints to `~/.mempalace`; set `PYTHONPYCACHEPREFIX` in skill Bash calls.
3. **Config v2 schema** (nested wings/rooms) + v1→v2 migration + loader tests.
4. **Adapter contract change** (wing=inbox, namespaced source_file); refactor markdown adapter; update `build-adapter` skill (drop routing; write to `~/.mempalace/adapters/`).
5. **`wing_deriver.py`** (`propose_tree` / `assign` / `apply`, two-level) + tests.
6. **Two-phase `ingest.py`** orchestration over multiple sources (`--derive-wings`, `--assign-wings`) + bundled/data adapter loading.
7. **Obsidian adapter.**
8. **Notion adapter.**
9. **Apple Notes adapter.**
10. **Setup helpers** (`check_env.py`, `write_config.py`) + tests.
11. **`mindgraph-setup` skill** — orchestration, conversational confirm, live `build-adapter` for "Other".
12. **README + docs** — plugin install commands, app-like model, source list, concept-derived wing/room model, the clone-to-hack note.
