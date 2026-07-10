# Changelog

All notable changes to MindGraph are documented here.

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
