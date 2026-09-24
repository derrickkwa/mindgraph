# Changelog

All notable changes to MindGraph are documented here.

## [0.3.0] — 2026-09-24

The memory layer and FORK were developed in the author's private second brain between July and September 2026, and are first published here on 2026-09-24.

### Added

- **Claude Code memory sync + opt-in hook.** `memory_sync.py` mirrors per-project Claude Code auto-memory files into a dedicated `memory` wing in the palace, so past conclusions are retrievable alongside notes. Off by default; `/mindgraph-setup` step 6b asks once, and enabling it turns on a hook that runs after file edits and exits immediately unless the edited file is a memory file. `MEMORY.md` itself is excluded from sync.
- **Memory lint (`brain-lint` / `memory_lint.py`).** Audits Claude Code memory files across projects: flags `MEMORY.md` size against its load ceiling, checks every memory file is reachable from `MEMORY.md` directly or via one topic hub, and can fix near-miss `[[links]]` with `--fix-near-matches`.
- **Belief ledger (`belief_ledger.py`).** An append-only event log of conclusions and their revisions. Records a conclusion once, records later revisions as `reversal` or `refinement` with an effective date and reason, and replays a belief's full history with `--history`. Supports per-claim sub-keys (`<file>--<claim>`) for memory files that carry several verdicts.
- **Consensus gate with query mode (`consensus_gate.py`).** A cheap dispersion score over retrieved source files that gates whether FORK's stance read runs at all — spread sources short-circuit with no model call. Excludes the `memory` wing from its count so a system's own summaries never vote as extra agreement.
- **FORK counter-pressure in `brain-retrieve`.** On a tight, stance-sharing retrieval, surfaces one labelled line of steelman against the notes' position and logs it to the belief ledger (no confidence change) unless the belief is in cooldown. Also surfaces "prior conclusions" (memory-wing hits) as a separate line from note evidence.
- **Docs.** `docs/memory-index.md` (the admission test, topic hubs, and belief-ledger pattern that keeps `MEMORY.md` small) and `docs/lessons.md` (architecture, write path, wiki-as-cache, read path, FORK, and lessons from running the system).

### Changed

- **License → [PolyForm Noncommercial License 1.0.0](LICENSE), effective 0.3.0.** Versions 0.2.0 and earlier remain available under MIT.

## [0.2.0] — 2026-07-10

A ground-up repackaging: MindGraph goes from a "clone-and-run" template to an installable **Claude Code plugin**, and wing/room organization becomes **concept-derived** instead of folder-declared.

### Added

- **Claude Code plugin + self-hosted marketplace.** The repo now ships `.claude-plugin/marketplace.json` and `plugins/mindgraph/.claude-plugin/plugin.json`. Install entirely inside Claude Code:
  ```
  /plugin marketplace add derrickkwa/mindgraph
  /plugin install mindgraph@mindgraph
  /mindgraph-setup
  ```
- **`mindgraph-setup` skill** — conversational first-run setup: preflight (Python/Mempalace/API key), source selection, per-source config (incl. a live Notion-token walkthrough and Apple Notes permission guidance), first ingest, wing/room derivation + confirmation, and assignment.
- **Multi-source ingestion.** `config.yml` now takes a `sources:` list; `ingest.py` loops over every configured source. Pre-built adapters:
  - `markdown` — a folder of `.md` files
  - `obsidian` — a vault; extracts `[[wikilinks]]` as tags, ignores `.obsidian/`
  - `notion` — Notion API via `urllib` (no SDK); paginated search + block text
  - `apple_notes` — macOS export via `osascript`
  - "Other" sources are generated on demand by the `build-adapter` skill, run live during setup, written to `~/.mempalace/adapters/`.
- **Concept-derived wings & rooms.** After ingest builds the concept graph, `ingest.py --derive-wings` makes a single LLM call to propose a nested wing→room tree from your concept vocabulary; you confirm it; `ingest.py --assign-wings` then assigns every note by deterministic concept-overlap (no per-note LLM call). Re-derivable any time.
- **Data-home isolation.** `scripts/paths.py` resolves every writable path (`config.yml`, `.env`, `_wiki/`, palace, KG, checkpoints) under a single data home — `$MINDGRAPH_HOME` if set, else `~/.mempalace`. Setting `MINDGRAPH_HOME` fully isolates a dev/test store from a real one.
- **`check_env.py`** preflight helper (Python version, Mempalace presence, API keys) and **`write_config.py`** CLI (`set-sources` / `set-wings` from stdin JSON).
- **`CHANGELOG.md`** (this file).

### Changed

- **Adapters no longer assign wings.** Every adapter now emits provisional `wing="inbox"`, `room="general"` chunks with a namespaced `source_file` (`"<type>:<id>"`, e.g. `notion:<page_id>`) so multiple sources can't collide. Wing/room are applied later by the derivation step.
- **`config.yml` schema v2** (`sources:` + nested `wings:`/`rooms:` + `defaults: {wing: inbox, room: general}`). A legacy v1 config (`notes_folder:` + folder-routed wings) is auto-migrated in memory on load.
- **Code runs read-only from `${CLAUDE_PLUGIN_ROOT}`;** all data lives under the data home. Bundled skills reference their scripts via `${CLAUDE_PLUGIN_ROOT}`.
- Docs rewritten for the plugin model: `README.md`, `docs/adapter-contract.md`, `plugins/mindgraph/adapters/README.md`, and the `build-adapter` skill contract (adapters must emit `inbox`/`general` + namespaced `source_file`; generated adapters write to `~/.mempalace/adapters/`).

### Removed

- **Folder-based wing routing.** Wings are no longer mapped from folder paths; the `markdown` adapter and `config.yml` dropped the `folder → wing` mappings.
- **`scripts/setup.py`** — the old interactive Python installer, superseded by the `mindgraph-setup` skill and `check_env.py`. (It also wrote into the now-read-only plugin directory and emitted the retired v1 schema.)

### Fixed

- Notion title detection now matches the title property by **payload shape** (its value carries a `title` list) rather than by a property key literally named `"title"`, avoiding a wrong-title selection on multi-property databases.
- Apple Notes parsing uses `maxsplit` so a stray field separator inside a note body can't shift the folder/title/date fields.
- `check_env.py` / `write_config.py` are runnable as direct scripts from any working directory (package-import bootstrap), which the setup skill depends on.

### Migration (existing single-user installs)

Your data in `~/.mempalace` is unchanged. On first load, an old `config.yml` with `notes_folder:` is migrated to `sources: [{type: markdown, path: <notes_folder>}]`. To adopt concept-derived wings, run `ingest.py --derive-wings`, confirm the proposed tree, then `ingest.py --assign-wings`.

### Note for contributors

MindGraph shares the default `~/.mempalace` store with any real Mempalace brain on the machine. **Always `export MINDGRAPH_HOME=$(mktemp -d)` (or a dedicated dev dir) before running any ingest/script in development** so tests never touch a real store. See the Development section in `README.md`.
