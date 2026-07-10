---
name: mindgraph-setup
description: First-run setup for MindGraph. Installs deps, picks note sources, ingests, and derives your wings. Triggers on "set me up", "/mindgraph-setup", "set up my second brain".
---

# mindgraph-setup

Run all Python via `PYTHONPYCACHEPREFIX=/tmp/mgpyc python3 ${CLAUDE_PLUGIN_ROOT}/scripts/<script>.py`
(the plugin dir is read-only — never write inside `${CLAUDE_PLUGIN_ROOT}`).

## Steps

### 1. Preflight
Run `check_env.py`. If `python_ok` is false, tell the user to install Python ≥ 3.11 and stop.
If `mempalace` is false, run `uv tool install mempalace` (or `pip install mempalace`).
If neither key is present, ask the user for a Gemini or Anthropic key and append it to
`~/.mempalace/.env` (`GEMINI_API_KEY=…`). Re-run `check_env.py` until `ready` is true.

### 2. Choose sources (one at a time)
Ask: "Where do you keep your notes?" Offer Obsidian, Notion, Apple Notes (macOS only), Other.
Accept multiple. For each:
- **Obsidian** — ask the vault path; confirm it exists.
- **Notion** — walk them through https://www.notion.so/my-integrations (create internal
  integration → copy token → share the pages/databases with it). Save `NOTION_TOKEN=` to
  `~/.mempalace/.env`. Verify with `python3 ${CLAUDE_PLUGIN_ROOT}/adapters/notion.py --test`.
- **Apple Notes** — run `python3 ${CLAUDE_PLUGIN_ROOT}/adapters/apple_notes.py`; if it errors
  with a permission message, walk them through System Settings → Privacy & Security →
  Automation → allow access to Notes, then retry. Optional: ask which folders to include.
- **Other** — invoke the `build-adapter` skill live; it writes the new adapter into
  `~/.mempalace/adapters/<source>.py`.

### 3. Write config
Build the `sources` list as JSON and pipe it to the CLI:
`echo '<json sources>' | PYTHONPYCACHEPREFIX=/tmp/mgpyc python3 ${CLAUDE_PLUGIN_ROOT}/scripts/write_config.py set-sources`

### 4. First ingest (Phase A)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py`. Report the chunk/entity/triple counts.

### 5. Derive + confirm wings (Phase B)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py --derive-wings`. Show the proposed
wing→room tree in a readable outline. Let the user rename / merge / split / accept by talking.
Write the confirmed tree as JSON piped to the CLI:
`echo '<json wing tree>' | PYTHONPYCACHEPREFIX=/tmp/mgpyc python3 ${CLAUDE_PLUGIN_ROOT}/scripts/write_config.py set-wings`

### 6. Assign (Phase C)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py --assign-wings`. Report counts per wing.

### 7. Done
Suggest: "Ask me: 'what do my notes say about <topic>?'" (uses the brain-retrieve skill).
