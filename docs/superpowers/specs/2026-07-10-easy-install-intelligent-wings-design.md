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
| Install front door | One-line `curl` bootstrap → interactive wizard |
| Adapter strategy | Pre-built, shipped in repo (Notion, Obsidian, Apple Notes); "Other" → `build-adapter` skill |
| Source count | Multiple sources per install |
| Wing routing | Derived from concept graph, user-confirmed, assigned by concept overlap |
| Wing assignment mechanism | Deterministic concept-overlap (no per-note LLM call) |
| Folder-based routing | **Removed entirely** — everyone gets concept-derived wings |
| Rooms | Defaulted to `general`; sub-clustering is a future enhancement, out of scope |

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
        Phase B: group concept vocabulary into 5–9 named wings (1 LLM call)
                              │
                              ▼
              User confirms wings  ──▶  config.yml `wings:`
                              │
                              ▼  [free, deterministic]
        Assign each note to best-overlap wing  ──▶  update ChromaDB metadata + KG triple source_closet
```

### Component boundaries

**Adapters** (`adapters/*.py`) — one job: fetch + chunk + emit chunks. They no longer assign wings.
- Output chunk schema (unchanged fields, new rule): `text`, `source_file` (namespaced), `filed_at`, optional `title`, `tags`, `source_url`. `wing` is always the provisional `inbox`; `room` is `general`.
- `source_file` is namespaced by source type to prevent cross-source collisions: `obsidian:work/note.md`, `notion:<page_id>`, `apple_notes:<note_id>`.
- Each adapter keeps a `--test` CLI flag (fetch ≤5 items, print a sample chunk).

**Ingest orchestrator** (`scripts/ingest.py`) — loops over `config.sources`, dispatches each to its adapter, aggregates chunks, then drives `batch_ingest`. After Phase A, if wings are unconfirmed (or `--derive-wings` passed), runs Phase B → confirm → assign.

**Wing deriver** (new: `scripts/wing_deriver.py`) —
- `propose_wings(kg) -> list[{name, concepts}]`: reads the concept vocabulary from the KG, one LLM call groups concepts into 5–9 coherent named themes.
- `assign_wings(kg, wings) -> dict[source_file, wing]`: for each note, tallies its expressed concepts against each wing's concept set, assigns the max-overlap wing (ties broken by highest summed confidence, then first wing). Pure graph math — no LLM.
- `apply_wings(...)`: writes assignments back to ChromaDB chunk metadata and KG triple `source_closet`.

**Setup wizard** (`scripts/setup.py`, rewritten) — see Wizard flow.

**Bootstrap** (new: `install.sh`) — see Install.

### Config schema (v2)

```yaml
sources:
  - {type: obsidian, path: ~/vault}
  - {type: apple_notes}            # macOS only; optional folders: [Work, Personal]
  - {type: notion}                 # token read from .env NOTION_TOKEN
llm_provider: auto                 # auto | gemini | claude
wings:                             # empty until Phase B confirmed
  - {name: growth, concepts: [activation-friction, retention, funnel-design]}
  - {name: personal, concepts: [habit-formation, reflection]}
defaults: {wing: inbox, room: general}
```

`config.py` loader must accept v2 (`sources:` list). A v1 config (`notes_folder:` + folder-routed `wings:`) is migrated on load to `sources: [{type: markdown, path: <notes_folder>}]` with a one-time notice, so existing users don't break. The plain `markdown` adapter is retained as the generic base type (Obsidian is a variant of it); the wizard surfaces "Obsidian" but `markdown` remains a valid config `type` for any folder of `.md` files.

---

## Install

`install.sh` (hosted in repo, run via raw GitHub URL):

1. Verify `python3` ≥ 3.11 and `git`; friendly abort with install hints if missing.
2. Clone repo to `~/mindgraph` (skip if it already exists; offer to update).
3. Install Mempalace + deps (`uv tool install mempalace` if `uv` present, else `pip`).
4. Copy `.env.example` → `.env` if absent.
5. Launch `python3 scripts/setup.py`.

Command: `curl -fsSL https://raw.githubusercontent.com/derrickkwa/mindgraph/main/install.sh | bash`

---

## Wizard flow (`setup.py`)

1. **API key check** — confirm `GEMINI_API_KEY` or `ANTHROPIC_API_KEY` in `.env`; if missing, prompt to paste one (concept extraction and wing derivation both require it).
2. **Source selection** — multi-select: Obsidian / Notion / Apple Notes / Other. Apple Notes hidden unless `sys.platform == "darwin"`.
3. **Per-source config**
   - Obsidian → prompt for vault path; validate it exists.
   - Notion → walk through creating an internal integration + sharing pages; prompt to paste `NOTION_TOKEN` into `.env`.
   - Apple Notes → no credentials; optional folder filter.
   - Other → tell the user to open the repo in Claude Code and run `build-adapter`; skip live gen in the wizard.
4. **Write `config.yml`** (sources + empty wings + defaults).
5. **First ingest (Phase A)** — run `ingest.py`; builds concept graph.
6. **Derive + confirm wings (Phase B)** — show proposed wings; let user rename / merge / split / accept; write to `config.yml`.
7. **Assign wings** — apply overlap assignment; report counts per wing.
8. **Done** — print retrieval example.

---

## Adapters to build

| Adapter | Mechanism | Notes |
|---------|-----------|-------|
| `obsidian.py` | Extends markdown adapter | Handle `[[wikilinks]]` (record as `tags`/links, strip syntax from text); ignore `.obsidian/`. Path-based. |
| `apple_notes.py` | AppleScript via `osascript` | Export title, body (HTML→text), folder, created/modified. Namespace by note id. macOS-only guard. Guided automation-permission prompt on first run. |
| `notion.py` | Notion API via `urllib` (no SDK) | `POST /v1/search` to list pages/databases; fetch block children for text; paginate via `next_cursor`; 429 → exponential backoff (reuse pattern from `concept_extractor.py`). Bearer token from `NOTION_TOKEN`. |
| Other | Existing `build-adapter` skill | Unchanged; now the only path for non-shipped sources. |

`build-adapter` skill must be updated: adapters no longer do wing/room routing (remove that requirement from the skill's generated-adapter contract).

---

## Error handling

- **Bootstrap:** missing python/git → clear message + install link, non-zero exit.
- **No API key:** ingest refuses to run with an explicit message (both concept extraction and wing derivation need it).
- **Invalid Notion token:** `notion.py --test` fails fast; wizard surfaces the error and re-prompts.
- **Apple Notes permission denied:** detect the automation-permission error, print steps to grant Terminal access to Notes, offer retry.
- **Wing proposal fails** (LLM error / unparseable): fall back to a single `inbox` wing; tell the user they can re-run `ingest.py --derive-wings` later.
- **Rate limits:** already handled by backoff in `concept_extractor.py`; Notion adapter mirrors it.

---

## Testing

Unit tests on logic that can break silently:
- `config.py` v2 loader + v1→v2 migration.
- `source_file` namespacing per adapter.
- `wing_deriver.assign_wings` — deterministic overlap, including tie-breaking, fixture-driven with a stub KG.
- `wing_deriver.propose_wings` — parsing with a mocked LLM provider.

Lighter fixture smoke tests for adapters:
- Obsidian on a fixture vault (wikilinks, `.obsidian/` ignored).
- Notion with a mocked API response (search + block children).
- Apple Notes with mocked `osascript` output.

Per project convention, adapters are simple data-mapping; verify with fixture runs rather than exhaustive TDD. The wing-assignment and config logic get real unit tests.

---

## Out of scope

- Rooms / sub-clustering within a wing (defaulted to `general` for now).
- Live adapter generation inside the wizard ("Other" defers to `build-adapter` in Claude Code).
- A hosted install domain (raw GitHub URL is sufficient; prettify later).
- Incremental / delta re-ingest optimizations beyond the existing checkpoint resume.

---

## Implementation phases (for the plan)

1. Config v2 schema + migration + loader tests.
2. Adapter contract change (wing=inbox, namespaced source_file); refactor markdown adapter; update `build-adapter` skill.
3. `wing_deriver.py` (propose / assign / apply) + tests.
4. Two-phase `ingest.py` orchestration over multiple sources.
5. Obsidian adapter.
6. Notion adapter.
7. Apple Notes adapter.
8. `setup.py` wizard rewrite.
9. `install.sh` bootstrap.
10. README + docs update (new install command, source list, wing model).
