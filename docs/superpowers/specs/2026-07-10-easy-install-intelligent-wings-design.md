# MindGraph: Easy Install + Intelligent Wings

**Date:** 2026-07-10
**Status:** Approved design, pre-implementation

---

## Problem

MindGraph is a Claude Code second-brain template. Two things make it hard for a stranger to adopt:

1. **Install friction.** Today: `git clone` → `python3 scripts/setup.py`, a wizard that only understands a folder of markdown. There is no path for the note sources people actually use (Notion, Apple Notes).
2. **Wings assume folders.** The markdown adapter routes notes into wings by folder-path prefix. Our own Mempalace worked because our Apple Notes happened to be foldered to match a predefined taxonomy. A stranger with a flat pile of notes gets one useless `misc` wing — even though the concept graph (the actual intelligence) builds fine without folders.

This design makes install a single command with source selection, ships pre-built adapters for the common sources, and replaces folder-based wing routing with wings **derived from the concept graph and confirmed by the user**.

---

## Key insight: two layers, only one is "knowledge"

The pipeline already separates two concerns, and this design leans into that separation:

- **Wings / rooms** — coarse storage buckets (`wing`, `room` tags on each chunk). No intelligence. In our system they were a predefined taxonomy filled by folder path.
- **Concepts** — the knowledge graph. `concept_extractor.py` already sends every chunk to an LLM and extracts abstract concepts (`activation-friction`, `feedback-loops`) into KG entity nodes + `expresses` triples. **This needs no folders.** It reads meaning from text.

The concept graph is what makes retrieval smart, and it is folder-free today. Only the wing layer breaks on folderless sources. Since the LLM already reads every chunk during ingest, deriving wings from the resulting concept graph is nearly free.

---

## Decisions (locked)

| Decision | Choice |
|----------|--------|
| Install front door | Minimal `curl` bootstrap (files + deps only) → **Claude-Code-native setup skill** |
| Setup orchestration | A `mindgraph-setup` skill drives setup conversationally; Python scripts do the mechanical work |
| Adapter strategy | Pre-built, shipped in repo (Notion, Obsidian, Apple Notes); "Other" → `build-adapter`, run **live in-setup** |
| Source count | Multiple sources per install |
| Wing/room routing | Derived from concept graph, user-confirmed, assigned by concept overlap |
| Assignment mechanism | Deterministic concept-overlap, two-level (wing then room); no per-note LLM call |
| Folder-based routing | **Removed entirely** — everyone gets concept-derived wings/rooms |
| Rooms | **In scope** — sub-clusters of a wing's concepts (nested under wings) |

---

## Architecture

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
              User confirms tree  ──▶  config.yml `wings:` (with nested `rooms:`)
                              │
                              ▼  [free, deterministic]
        Assign each note: wing by overlap, then room within that wing by overlap
                              │
                              ▼
              update ChromaDB metadata (wing, room) + KG triple source_closet
```

### Component boundaries

**Adapters** (`adapters/*.py`) — one job: fetch + chunk + emit chunks. They no longer assign wings.
- Output chunk schema (unchanged fields, new rule): `text`, `source_file` (namespaced), `filed_at`, optional `title`, `tags`, `source_url`. `wing` is always the provisional `inbox`; `room` is `general`.
- `source_file` is namespaced by source type to prevent cross-source collisions: `obsidian:work/note.md`, `notion:<page_id>`, `apple_notes:<note_id>`.
- Each adapter keeps a `--test` CLI flag (fetch ≤5 items, print a sample chunk).

**Ingest orchestrator** (`scripts/ingest.py`) — loops over `config.sources`, dispatches each to its adapter, aggregates chunks, then drives `batch_ingest` (Phase A). It does **not** confirm wings — human confirmation lives in the setup skill. `ingest.py --derive-wings` prints the proposed tree (`propose_tree`) as JSON for the skill to present; a separate `ingest.py --assign-wings` applies a confirmed tree from `config.yml`. On routine re-ingest of new notes (wings already confirmed), Phase A runs, then new notes are auto-assigned to the existing tree by overlap with no re-proposal.

**Wing deriver** (new: `scripts/wing_deriver.py`) —
- `propose_tree(kg) -> list[{name, rooms:[{name, concepts}]}]`: reads the concept vocabulary from the KG; one LLM call groups concepts into a nested tree — 5–9 named wings, each sub-divided into named rooms. A wing's concept set is the union of its rooms' concepts. Wings too small to sub-divide get a single `general` room.
- `assign(kg, wings) -> dict[source_file, {wing, room}]`: for each note, tallies its expressed concepts against each wing's concept set → max-overlap wing; then against that wing's rooms → max-overlap room (falls back to the wing's `general` room when no room overlaps). Ties broken by highest summed confidence, then first entry. Pure graph math — no LLM.
- `apply(...)`: writes wing + room back to ChromaDB chunk metadata and the KG triple `source_closet`.

**Setup skill** (new: `skills/mindgraph-setup/SKILL.md`) — orchestrates setup conversationally inside Claude Code; calls the Python helpers below for mechanical steps. See Setup flow.

**Setup helpers** (`scripts/`) — small, independently-runnable, testable scripts the skill invokes:
- `check_env.py` — reports which API keys are present.
- `write_config.py` — writes/updates `config.yml` (sources, then the confirmed wing/room tree).
- `ingest.py`, `wing_deriver.py` — as above.

**Bootstrap** (new: `install.sh`) — see Install.

### Config schema (v2)

```yaml
sources:
  - {type: obsidian, path: ~/vault}
  - {type: apple_notes}            # macOS only; optional folders: [Work, Personal]
  - {type: notion}                 # token read from .env NOTION_TOKEN
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

A wing's concept set is the union of its rooms' concepts; there is no wing-level `concepts` key.

`config.py` loader must accept v2 (`sources:` list). A v1 config (`notes_folder:` + folder-routed `wings:`) is migrated on load to `sources: [{type: markdown, path: <notes_folder>}]` with a one-time notice, so existing users don't break. The plain `markdown` adapter is retained as the generic base type (Obsidian is a variant of it); the wizard surfaces "Obsidian" but `markdown` remains a valid config `type` for any folder of `.md` files.

---

## Install (the bootstrap floor)

MindGraph requires Claude Code to be used at all, so setup assumes it. The only thing that must happen before Claude Code can help is getting files onto disk — that is the bootstrap, and it is deliberately minimal (no config, no questions).

`install.sh` (hosted in repo, run via raw GitHub URL):

1. Verify `python3` ≥ 3.11 and `git`; friendly abort with install hints if missing.
2. Clone repo to `~/mindgraph` (skip if it already exists; offer to update).
3. Install Mempalace + deps (`uv tool install mempalace` if `uv` present, else `pip`).
4. Copy `.env.example` → `.env` if absent.
5. Print: **"Done. Open this folder in Claude Code and say 'set me up'."**

Command: `curl -fsSL https://raw.githubusercontent.com/derrickkwa/mindgraph/main/install.sh | bash`

---

## Setup flow (`mindgraph-setup` skill)

The user opens `~/mindgraph` in Claude Code and says "set me up" (or runs `/mindgraph-setup`). The skill orchestrates; Python helpers do the mechanical work. Because it runs inside Claude, every step is conversational and Claude troubleshoots errors live.

1. **API key check** — run `check_env.py`. If no `GEMINI_API_KEY`/`ANTHROPIC_API_KEY`, Claude explains how to get one and where to put it in `.env`.
2. **Source selection** — Claude asks which sources (Obsidian / Notion / Apple Notes / Other), accepts several. Apple Notes only offered on macOS.
3. **Per-source config**
   - Obsidian → ask vault path; validate it exists.
   - Notion → Claude walks the user through creating an internal integration and sharing pages, then captures `NOTION_TOKEN` into `.env`.
   - Apple Notes → trigger the export once to surface the automation-permission prompt; Claude guides granting it. Optional folder filter.
   - Other → Claude runs the `build-adapter` skill **live** to generate the adapter in-session (now possible because setup is inside Claude Code).
4. **Write `config.yml`** — via `write_config.py` (sources + empty wings + defaults).
5. **First ingest (Phase A)** — run `ingest.py`; builds the concept graph.
6. **Derive + confirm tree (Phase B)** — `wing_deriver.propose_tree`; Claude presents the wing→room tree, the user renames / merges / splits / accepts by talking, Claude writes the confirmed tree via `write_config.py`.
7. **Assign (Phase C)** — `wing_deriver.assign` + `apply`; report note counts per wing/room.
8. **Done** — Claude suggests a first retrieval query to try.

Advanced users can bypass the skill and run the Python steps directly; the skill is orchestration, not logic.

---

## Adapters to build

| Adapter | Mechanism | Notes |
|---------|-----------|-------|
| `obsidian.py` | Extends markdown adapter | Handle `[[wikilinks]]` (record as `tags`/links, strip syntax from text); ignore `.obsidian/`. Path-based. |
| `apple_notes.py` | AppleScript via `osascript` | Export title, body (HTML→text), folder, created/modified. Namespace by note id. macOS-only guard. Guided automation-permission prompt on first run. |
| `notion.py` | Notion API via `urllib` (no SDK) | `POST /v1/search` to list pages/databases; fetch block children for text; paginate via `next_cursor`; 429 → exponential backoff (reuse pattern from `concept_extractor.py`). Bearer token from `NOTION_TOKEN`. |
| Other | Existing `build-adapter` skill | Run **live during setup** by the `mindgraph-setup` skill; the only path for non-shipped sources. |

`build-adapter` skill must be updated: adapters no longer do wing/room routing (remove that requirement from the skill's generated-adapter contract).

---

## Error handling

The Python scripts fail loudly with clear messages and exit codes; the `mindgraph-setup` skill catches these and troubleshoots with the user conversationally (its advantage over a rigid wizard).

- **Bootstrap:** missing python/git → clear message + install link, non-zero exit.
- **No API key:** ingest refuses to run with an explicit message (both concept extraction and wing derivation need it); the skill helps the user obtain and place a key.
- **Invalid Notion token:** `notion.py --test` fails fast; the skill surfaces the error and re-prompts.
- **Apple Notes permission denied:** the export script emits a recognizable automation-permission error; the skill walks the user through granting Claude/Terminal access to Notes, then retries.
- **Wing proposal fails** (LLM error / unparseable): fall back to a single `inbox` wing with a `general` room; the user can re-run `ingest.py --derive-wings` later.
- **Rate limits:** already handled by backoff in `concept_extractor.py`; the Notion adapter mirrors it.

---

## Testing

Unit tests on logic that can break silently:
- `config.py` v2 loader (nested wings/rooms) + v1→v2 migration.
- `write_config.py` round-trips a confirmed wing/room tree.
- `source_file` namespacing per adapter.
- `wing_deriver.assign` — deterministic two-level overlap (wing then room), including tie-breaking and the `general`-room fallback, fixture-driven with a stub KG.
- `wing_deriver.propose_tree` — parses a nested tree from a mocked LLM provider.

Lighter fixture smoke tests for adapters:
- Obsidian on a fixture vault (wikilinks, `.obsidian/` ignored).
- Notion with a mocked API response (search + block children).
- Apple Notes with mocked `osascript` output.

Per project convention, adapters are simple data-mapping; verify with fixture runs rather than exhaustive TDD. The wing-assignment and config logic get real unit tests.

---

## Out of scope

- Claude Code **plugin distribution** (`/plugin install mindgraph` to skip even the bootstrap) — attractive future path, not this build.
- A hosted install domain (raw GitHub URL is sufficient; prettify later).
- Incremental / delta re-ingest optimizations beyond the existing checkpoint resume.
- Deeper-than-two-level hierarchy (sub-rooms); wing → room is the ceiling.

---

## Implementation phases (for the plan)

1. Config v2 schema (nested wings/rooms) + v1→v2 migration + loader tests.
2. Adapter contract change (wing=inbox, namespaced source_file); refactor markdown adapter; update `build-adapter` skill to drop routing.
3. `wing_deriver.py` (`propose_tree` / `assign` / `apply`, two-level) + tests.
4. Two-phase `ingest.py` orchestration over multiple sources (+ `--derive-wings`).
5. Obsidian adapter.
6. Notion adapter.
7. Apple Notes adapter.
8. Setup helpers (`check_env.py`, `write_config.py`) + tests.
9. `mindgraph-setup` skill (orchestration, conversational confirm, live `build-adapter` for "Other").
10. `install.sh` bootstrap.
11. README + docs update (new install command, "open in Claude Code → set me up", source list, concept-derived wing/room model).
