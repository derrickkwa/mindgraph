# MindGraph Plugin Install + Intelligent Wings — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship MindGraph as a Claude Code plugin installed and run entirely inside Claude Code, with pre-built multi-source adapters and wings/rooms derived from the concept graph instead of folders.

**Architecture:** The repo self-hosts as a plugin marketplace; the plugin bundles skills + Python under `plugins/mindgraph/` and runs read-only from `${CLAUDE_PLUGIN_ROOT}`. All writable state lives under a data home (`~/.mempalace`, overridable via `MINDGRAPH_HOME`). Adapters emit provisional `inbox` chunks; after ingest builds the concept graph, one LLM call proposes a nested wing→room tree, the user confirms it, and each note is assigned by deterministic concept overlap.

**Tech Stack:** Python 3.11+, PyYAML, ChromaDB + Mempalace KG (SQLite), Gemini/Claude via `urllib` (no SDK), pytest.

## Global Constraints

- Python ≥ 3.11 (copy verbatim: `requires-python = ">=3.11"`).
- No new heavy dependencies; LLM calls use `urllib` only (no `anthropic`/`google` SDKs). Existing deps: `pyyaml>=6.0`.
- Never write to `${CLAUDE_PLUGIN_ROOT}` at runtime — it is read-only. All writes go to the data home.
- Data home resolves to `MINDGRAPH_HOME` if set, else `~/.mempalace`.
- Adapters never assign wings: every emitted chunk has `wing="inbox"`, `room="general"`.
- `source_file` is namespaced `"{source_type}:{native_id_or_path}"`.
- Wing assignment is deterministic (no per-note LLM call); only `propose_tree` calls an LLM.
- Chunk schema required fields: `text`, `source_file`, `wing`, `room`, `filed_at`. Optional: `title`, `tags`, `source_url`.
- Commit after every task.

---

## File Structure

**New:**
- `.claude-plugin/marketplace.json` — marketplace manifest (name: `mindgraph`)
- `plugins/mindgraph/.claude-plugin/plugin.json` — plugin manifest
- `plugins/mindgraph/scripts/paths.py` — data-home resolver
- `plugins/mindgraph/scripts/write_config.py` — config writer
- `plugins/mindgraph/scripts/check_env.py` — preflight checks
- `plugins/mindgraph/scripts/wing_deriver.py` — propose/assign/apply wing→room tree
- `plugins/mindgraph/adapters/obsidian.py`, `notion.py`, `apple_notes.py`
- `plugins/mindgraph/skills/mindgraph-setup/SKILL.md`

**Moved (git mv, repo root → `plugins/mindgraph/`):** `scripts/`, `adapters/`, `skills/`, `tests/`, `_wiki/`, `docs/`, `config.yml.example`, `.env.example`.

**Modified:** `scripts/config.py`, `scripts/ingest.py`, `skills/brain-ingest/scripts/batch_ingest.py`, `skills/build-adapter/SKILL.md`, `adapters/markdown.py`, `README.md`.

> Paths below are relative to `plugins/mindgraph/` after Task 1 unless prefixed with repo root.

---

## Task 1: Repo → plugin layout

**Files:**
- Create: `.claude-plugin/marketplace.json`, `plugins/mindgraph/.claude-plugin/plugin.json`
- Move: all existing top-level content under `plugins/mindgraph/`

**Interfaces:**
- Produces: a working `/plugin install mindgraph@mindgraph`; all Python importable as before from the new root.

- [ ] **Step 1: Move existing content under the plugin dir**

```bash
cd <repo-root>
mkdir -p plugins/mindgraph
git mv scripts adapters skills tests _wiki docs config.yml.example .env.example pyproject.toml plugins/mindgraph/
# Leave README.md and .gitignore at repo root (README covers install; add plugin README in Task 14)
```

- [ ] **Step 2: Create the marketplace manifest**

Create `.claude-plugin/marketplace.json`:

```json
{
  "name": "mindgraph",
  "owner": { "name": "derrickkwa" },
  "plugins": [
    {
      "name": "mindgraph",
      "source": "./plugins/mindgraph",
      "description": "A Claude Code second brain: multi-source ingest, concept graph, and concept-derived wings."
    }
  ]
}
```

- [ ] **Step 3: Create the plugin manifest**

Create `plugins/mindgraph/.claude-plugin/plugin.json`:

```json
{
  "name": "mindgraph",
  "version": "0.2.0",
  "description": "Second brain on Mempalace — multi-source ingest, concept graph, intelligent wings.",
  "author": { "name": "derrickkwa" }
}
```

- [ ] **Step 4: Fix pytest rootdir**

Move `pyproject.toml`'s pytest config so tests run from the plugin dir. Verify `plugins/mindgraph/pyproject.toml` still contains:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
```

- [ ] **Step 5: Verify existing tests still pass from the new root**

Run: `cd plugins/mindgraph && python3 -m pytest tests/ -v`
Expected: PASS (same tests as before the move; imports like `from scripts.config import ...` resolve because pytest rootdir is `plugins/mindgraph`).

- [ ] **Step 6: Verify the plugin installs**

Run in Claude Code:
```
/plugin marketplace add <local-repo-path-or-derrickkwa/mindgraph>
/plugin install mindgraph@mindgraph
```
Expected: install succeeds; `/mindgraph:brain-retrieve` (existing skill) is listed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: restructure repo as a Claude Code plugin + marketplace"
```

---

## Task 2: Data-home resolver + relocate all writes

**Files:**
- Create: `scripts/paths.py`, `tests/test_paths.py`
- Modify: `skills/brain-ingest/scripts/batch_ingest.py` (checkpoint path), `skills/brain-ingest/scripts/concept_extractor.py` + `batch_ingest.py` (dotenv from data home)

**Interfaces:**
- Produces:
  - `data_home() -> Path` — `MINDGRAPH_HOME` or `~/.mempalace`, created if missing.
  - `config_path() -> Path` — `data_home()/"config.yml"`.
  - `env_path() -> Path` — `data_home()/".env"`.
  - `wiki_dir() -> Path`, `adapters_dir() -> Path`, `checkpoints_dir() -> Path` — all under data home, created if missing.

- [ ] **Step 1: Write the failing test**

Create `tests/test_paths.py`:

```python
import importlib
from pathlib import Path


def _fresh(monkeypatch, home):
    monkeypatch.setenv("MINDGRAPH_HOME", str(home))
    import scripts.paths as paths
    return importlib.reload(paths)


def test_data_home_honors_env(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.data_home() == (tmp_path / "brain")
    assert paths.data_home().is_dir()


def test_default_is_dot_mempalace(monkeypatch):
    monkeypatch.delenv("MINDGRAPH_HOME", raising=False)
    import importlib, scripts.paths as paths
    paths = importlib.reload(paths)
    assert paths.data_home() == Path.home() / ".mempalace"


def test_derived_paths(tmp_path, monkeypatch):
    paths = _fresh(monkeypatch, tmp_path / "brain")
    assert paths.config_path() == tmp_path / "brain" / "config.yml"
    assert paths.env_path() == tmp_path / "brain" / ".env"
    assert paths.checkpoints_dir().is_dir()
    assert paths.adapters_dir().is_dir()
    assert paths.wiki_dir().is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.paths'`.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/paths.py`:

```python
"""Resolve MindGraph's writable data home. Never write inside the plugin dir."""
import os
from pathlib import Path


def data_home() -> Path:
    raw = os.environ.get("MINDGRAPH_HOME")
    home = Path(raw).expanduser() if raw else Path.home() / ".mempalace"
    home.mkdir(parents=True, exist_ok=True)
    return home


def config_path() -> Path:
    return data_home() / "config.yml"


def env_path() -> Path:
    return data_home() / ".env"


def _subdir(name: str) -> Path:
    d = data_home() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def wiki_dir() -> Path:
    return _subdir("_wiki")


def adapters_dir() -> Path:
    return _subdir("adapters")


def checkpoints_dir() -> Path:
    return _subdir("checkpoints")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_paths.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Point batch_ingest checkpoint + dotenv at the data home**

In `skills/brain-ingest/scripts/batch_ingest.py`, replace the checkpoint constant and dotenv loader:

```python
# near top, after imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from paths import checkpoints_dir, env_path

CHECKPOINT_FILE = checkpoints_dir() / "batch_ingest_checkpoint.json"
```

Replace the body of `_load_env()` with a single-file load from the data home:

```python
def _load_env():
    env = env_path()
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v.strip()
```

Apply the identical `_load_env()` replacement in `skills/brain-ingest/scripts/concept_extractor.py` (its `_load_dotenv()` function), importing `env_path` the same way.

- [ ] **Step 6: Delete the committed checkpoint artifact**

```bash
git rm --cached skills/brain-ingest/scripts/batch_ingest_checkpoint.json 2>/dev/null || true
echo "checkpoints/" >> .gitignore   # at repo root
```

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: resolve data home (~/.mempalace) and route all writes there"
```

---

## Task 3: Config v2 schema + v1 migration

**Files:**
- Modify: `scripts/config.py`
- Create fixtures: `tests/fixtures/config_v2.yml`, `tests/fixtures/config_v1.yml`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `load_config(path=None) -> dict` where a v2 config has `sources: list[dict]`, `llm_provider: str`, `wings: list[{name, rooms:[{name, concepts}]}]`, `defaults: {wing, room}`. A v1 config (`notes_folder`) is migrated in-memory to `sources: [{type: "markdown", path: <expanded>}]`. Default `path` is `config_path()` from `paths.py`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_config.py` with:

```python
import pytest
from pathlib import Path
from scripts.config import load_config, ConfigError

FIXTURES = Path(__file__).parent / "fixtures"


def test_v2_sources_loaded():
    config = load_config(FIXTURES / "config_v2.yml")
    assert config["sources"][0]["type"] == "obsidian"
    assert config["wings"][0]["rooms"][0]["name"] == "acquisition"
    assert config["defaults"]["wing"] == "inbox"


def test_v1_migrated_to_sources():
    config = load_config(FIXTURES / "config_v1.yml")
    assert config["sources"] == [{"type": "markdown", "path": config["sources"][0]["path"]}]
    assert "~" not in config["sources"][0]["path"]
    assert "notes_folder" not in config


def test_missing_config_raises():
    with pytest.raises(ConfigError, match="config.yml not found"):
        load_config("/nonexistent/config.yml")


def test_defaults_applied():
    config = load_config(FIXTURES / "config_v2.yml")
    assert config["llm_provider"] == "auto"
```

Create `tests/fixtures/config_v2.yml`:

```yaml
sources:
  - {type: obsidian, path: ~/vault}
llm_provider: auto
wings:
  - name: growth
    rooms:
      - {name: acquisition, concepts: [activation-friction, funnel-design]}
defaults: {wing: inbox, room: general}
```

Create `tests/fixtures/config_v1.yml`:

```yaml
notes_folder: ~/Documents/my-notes
llm_provider: auto
wings:
  - name: work
    rooms:
      projects: [work/projects/]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL (`test_v1_migrated_to_sources`, `test_v2_sources_loaded` — current loader requires `notes_folder`).

- [ ] **Step 3: Rewrite the loader**

Replace `scripts/config.py` with:

```python
from pathlib import Path
import yaml

from scripts.paths import config_path


class ConfigError(Exception):
    pass


def load_config(path=None) -> dict:
    config_path_ = Path(path) if path is not None else config_path()
    if not config_path_.exists():
        raise ConfigError(
            f"config.yml not found at {config_path_}. Run /mindgraph-setup."
        )

    with open(config_path_) as f:
        config = yaml.safe_load(f) or {}

    # v1 → v2 migration: notes_folder becomes a single markdown source.
    if "notes_folder" in config and "sources" not in config:
        expanded = str(Path(config.pop("notes_folder")).expanduser())
        config["sources"] = [{"type": "markdown", "path": expanded}]

    config.setdefault("sources", [])
    for src in config["sources"]:
        if "path" in src:
            src["path"] = str(Path(src["path"]).expanduser())

    config.setdefault("llm_provider", "auto")
    config.setdefault("wings", [])
    config.setdefault("defaults", {"wing": "inbox", "room": "general"})
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS (4 tests). Delete now-obsolete fixtures `config_valid.yml`, `config_minimal.yml`, `config_no_notes.yml`, `config_adapter_test.yml` if unreferenced (grep first).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: config v2 (sources + nested wings/rooms) with v1 migration"
```

---

## Task 4: Adapter contract change (markdown → inbox + namespaced)

**Files:**
- Modify: `adapters/markdown.py`
- Modify: `tests/test_markdown_adapter.py`

**Interfaces:**
- Consumes: `config["sources"]` entries of `{type: markdown|obsidian, path}`.
- Produces: `MarkdownAdapter().fetch(source: dict) -> list[dict]` — takes a single source dict (not the whole config). Every chunk: `wing="inbox"`, `room="general"`, `source_file="markdown:{relpath}"`. `SOURCE_TYPE = "markdown"` class attribute used for the namespace prefix (subclasses override).

- [ ] **Step 1: Write the failing test**

Replace `tests/test_markdown_adapter.py` with:

```python
from pathlib import Path
from adapters.markdown import MarkdownAdapter

FIXTURES = Path(__file__).parent / "fixtures" / "notes"


def test_emits_inbox_and_namespaced_source_file():
    adapter = MarkdownAdapter()
    chunks = adapter.fetch({"type": "markdown", "path": str(FIXTURES)})
    assert chunks, "expected chunks from fixture notes"
    for c in chunks:
        assert c["wing"] == "inbox"
        assert c["room"] == "general"
        assert c["source_file"].startswith("markdown:")
        assert set(["text", "source_file", "wing", "room", "filed_at"]) <= set(c)


def test_source_type_prefix_overridable():
    class FakeObsidian(MarkdownAdapter):
        SOURCE_TYPE = "obsidian"
    chunks = FakeObsidian().fetch({"type": "obsidian", "path": str(FIXTURES)})
    assert all(c["source_file"].startswith("obsidian:") for c in chunks)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_markdown_adapter.py -v`
Expected: FAIL (`fetch` currently expects `config["notes_folder"]` and routes wings by folder).

- [ ] **Step 3: Rewrite the adapter**

In `adapters/markdown.py`, replace the `fetch` method and delete `_build_mappings`/`_route` (folder routing is gone). Keep `_parse_frontmatter`, `_parse_date`, `_chunk`.

```python
class MarkdownAdapter(AdapterBase):
    SOURCE_TYPE = "markdown"

    def fetch(self, source: dict) -> list[dict]:
        folder = Path(source["path"]).expanduser()
        if not folder.exists():
            raise FileNotFoundError(f"source path not found: {folder}")

        chunks = []
        for md_file in sorted(folder.rglob("*.md")):
            rel = md_file.relative_to(folder)
            frontmatter, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
            title = frontmatter.get("title", md_file.stem.replace("-", " ").title())
            filed_at = _parse_date(frontmatter.get("date"), md_file)
            for chunk_text in _chunk(body):
                chunks.append({
                    "text": chunk_text,
                    "source_file": f"{self.SOURCE_TYPE}:{rel}",
                    "wing": "inbox",
                    "room": "general",
                    "filed_at": filed_at,
                    "title": title,
                    "tags": frontmatter.get("tags", []),
                })
        return chunks
```

Update the `if __name__ == "__main__":` block: build a `source` dict from `--path` (default the first markdown/obsidian source in config) and print sample.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_markdown_adapter.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: adapters emit inbox chunks with namespaced source_file (drop folder routing)"
```

---

## Task 5: write_config helper

**Files:**
- Create: `scripts/write_config.py`, `tests/test_write_config.py`

**Interfaces:**
- Consumes: `paths.config_path()`.
- Produces:
  - `set_sources(sources: list[dict]) -> None` — writes `sources`, preserving existing `wings`/`defaults`; creates the file with v2 defaults if absent.
  - `set_wings(wings: list[dict]) -> None` — writes the confirmed nested `wings` tree.
  - `read() -> dict` — current config or a v2 skeleton.

- [ ] **Step 1: Write the failing test**

Create `tests/test_write_config.py`:

```python
import importlib
import scripts.paths as paths


def _mod(monkeypatch, tmp_path):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path))
    importlib.reload(paths)
    import scripts.write_config as wc
    return importlib.reload(wc)


def test_set_sources_then_wings_roundtrip(tmp_path, monkeypatch):
    wc = _mod(monkeypatch, tmp_path)
    wc.set_sources([{"type": "notion"}])
    wc.set_wings([{"name": "growth", "rooms": [{"name": "acq", "concepts": ["funnel-design"]}]}])
    cfg = wc.read()
    assert cfg["sources"] == [{"type": "notion"}]
    assert cfg["wings"][0]["rooms"][0]["concepts"] == ["funnel-design"]
    assert cfg["defaults"] == {"wing": "inbox", "room": "general"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_write_config.py -v`
Expected: FAIL (`No module named 'scripts.write_config'`).

- [ ] **Step 3: Write implementation**

Create `scripts/write_config.py`:

```python
import yaml
from scripts.paths import config_path

_SKELETON = {"sources": [], "llm_provider": "auto", "wings": [],
             "defaults": {"wing": "inbox", "room": "general"}}


def read() -> dict:
    p = config_path()
    if not p.exists():
        return dict(_SKELETON)
    data = yaml.safe_load(p.read_text()) or {}
    for k, v in _SKELETON.items():
        data.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return data


def _write(cfg: dict) -> None:
    config_path().write_text(yaml.safe_dump(cfg, sort_keys=False))


def set_sources(sources: list) -> None:
    cfg = read()
    cfg["sources"] = sources
    _write(cfg)


def set_wings(wings: list) -> None:
    cfg = read()
    cfg["wings"] = wings
    _write(cfg)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_write_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: write_config helper for sources + confirmed wing tree"
```

---

## Task 6: wing_deriver (propose_tree / assign / apply)

**Files:**
- Create: `scripts/wing_deriver.py`, `tests/test_wing_deriver.py`

**Interfaces:**
- Consumes: `concept_extractor.get_provider`, KG read access.
- Produces:
  - `propose_tree(concepts_by_note: dict[str, list[str]], provider) -> list[dict]` — nested `[{name, rooms:[{name, concepts}]}]`; groups the concept vocabulary via one `provider.complete()` call.
  - `assign(concepts_by_note: dict[str, list[str]], wings: list[dict]) -> dict[str, dict]` — `{source_file: {"wing": w, "room": r}}`, deterministic overlap.
  - `apply(assignments: dict, col, kg) -> None` — updates ChromaDB metadata + KG triple `source_closet`.

- [ ] **Step 1: Write the failing tests (assignment logic — the deterministic core)**

Create `tests/test_wing_deriver.py`:

```python
from scripts.wing_deriver import assign, propose_tree

WINGS = [
    {"name": "growth", "rooms": [
        {"name": "acquisition", "concepts": ["funnel-design", "activation-friction"]},
        {"name": "retention", "concepts": ["churn", "retention"]},
    ]},
    {"name": "personal", "rooms": [
        {"name": "general", "concepts": ["habit-formation"]},
    ]},
]


def test_assigns_to_max_overlap_wing_and_room():
    notes = {"notion:a": ["funnel-design", "activation-friction"], "notion:b": ["churn"]}
    out = assign(notes, WINGS)
    assert out["notion:a"] == {"wing": "growth", "room": "acquisition"}
    assert out["notion:b"] == {"wing": "growth", "room": "retention"}


def test_no_room_overlap_falls_back_to_general():
    # matches wing 'growth' via a wing-level concept but no specific room? construct a wing with general
    wings = [{"name": "growth", "rooms": [
        {"name": "general", "concepts": []},
        {"name": "acquisition", "concepts": ["funnel-design"]},
    ]}]
    notes = {"notion:c": ["some-unknown-but-still-growth"]}
    # no overlap anywhere → default inbox/general
    assert assign(notes, wings)["notion:c"] == {"wing": "inbox", "room": "general"}


def test_tie_breaks_to_first_wing():
    wings = [
        {"name": "a", "rooms": [{"name": "general", "concepts": ["x"]}]},
        {"name": "b", "rooms": [{"name": "general", "concepts": ["x"]}]},
    ]
    assert assign({"n:1": ["x"]}, wings)["n:1"]["wing"] == "a"


def test_propose_tree_parses_nested_json():
    class Stub:
        def complete(self, prompt):
            return ('[{"name":"growth","rooms":[{"name":"acquisition",'
                    '"concepts":["funnel-design"]}]}]')
    tree = propose_tree({"n:1": ["funnel-design"]}, Stub())
    assert tree[0]["name"] == "growth"
    assert tree[0]["rooms"][0]["concepts"] == ["funnel-design"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_wing_deriver.py -v`
Expected: FAIL (`No module named 'scripts.wing_deriver'`).

- [ ] **Step 3: Write implementation**

Create `scripts/wing_deriver.py`:

```python
"""Derive a nested wing→room tree from the concept graph, then assign notes by overlap."""
import json

DEFAULT = {"wing": "inbox", "room": "general"}

PROMPT = """You organize a personal knowledge graph. Given this list of concepts,
group them into 5-9 coherent top-level WINGS, each split into 2-4 ROOMS.
Every concept must appear in exactly one room. Use short, lowercase, human names.

CONCEPTS:
{concepts}

Return ONLY JSON, no prose:
[{{"name": "wing-name", "rooms": [{{"name": "room-name", "concepts": ["c1","c2"]}}]}}]
"""


def propose_tree(concepts_by_note: dict, provider) -> list:
    vocab = sorted({c for cs in concepts_by_note.values() for c in cs})
    raw = provider.complete(PROMPT.format(concepts=json.dumps(vocab)))
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("```")[1]
        if clean.startswith("json"):
            clean = clean[4:]
    return json.loads(clean.strip())


def _room_concepts(wing: dict) -> dict:
    return {r["name"]: set(r.get("concepts", [])) for r in wing.get("rooms", [])}


def assign(concepts_by_note: dict, wings: list) -> dict:
    out = {}
    for note, concepts in concepts_by_note.items():
        cset = set(concepts)
        best_wing, best_room, best_score = None, "general", 0
        for wing in wings:  # first-wins tie-break via strict >
            rooms = _room_concepts(wing)
            wing_score = len(cset & set().union(*rooms.values())) if rooms else 0
            if wing_score > best_score:
                best_score = wing_score
                best_wing = wing["name"]
                # pick best room within this wing
                r_best, r_score = "general", 0
                for rname, rconcepts in rooms.items():
                    s = len(cset & rconcepts)
                    if s > r_score:
                        r_score, r_best = s, rname
                best_room = r_best
        if best_wing is None:
            out[note] = dict(DEFAULT)
        else:
            out[note] = {"wing": best_wing, "room": best_room}
    return out


def apply(assignments: dict, col, kg) -> None:
    import sqlite3
    for source_file, wr in assignments.items():
        # ChromaDB: update metadata on all chunks of this note
        got = col.get(where={"source_file": source_file})
        for cid, meta in zip(got.get("ids", []), got.get("metadatas", [])):
            meta.update(wr)
            col.update(ids=[cid], metadatas=[meta])
        # KG: update source_closet on triples from this source_file
        conn = kg._conn()
        conn.execute("UPDATE triples SET source_closet=? WHERE source_file=?",
                     (wr["wing"], source_file))
        conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_wing_deriver.py -v`
Expected: PASS (4 tests).

> Note: `apply` is covered by the Task 7 integration fixture run, not a unit test (it needs live ChromaDB/KG).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: wing_deriver — propose nested tree + deterministic two-level assign"
```

---

## Task 7: ingest.py — multi-source + two-phase orchestration

**Files:**
- Modify: `scripts/ingest.py`
- Create: `scripts/adapter_registry.py`, `tests/test_adapter_registry.py`

**Interfaces:**
- Consumes: `config["sources"]`, all adapters, `wing_deriver`, `batch_ingest`.
- Produces:
  - `adapter_registry.get_adapter(source_type: str) -> AdapterBase` — resolves bundled adapters (`markdown`, `obsidian`, `notion`, `apple_notes`) and any user adapter in `paths.adapters_dir()`.
  - `ingest.py` flags: default (Phase A ingest all sources), `--derive-wings` (print proposed tree JSON), `--assign-wings` (apply confirmed tree from config), `--status`, `--dry-run`.

- [ ] **Step 1: Write the failing test for the registry**

Create `tests/test_adapter_registry.py`:

```python
from adapters.markdown import MarkdownAdapter
from scripts.adapter_registry import get_adapter


def test_resolves_bundled_markdown():
    assert isinstance(get_adapter("markdown"), MarkdownAdapter)


def test_obsidian_is_markdown_subclass():
    from adapters.obsidian import ObsidianAdapter
    assert isinstance(get_adapter("obsidian"), ObsidianAdapter)


def test_unknown_type_raises():
    import pytest
    with pytest.raises(ValueError, match="unknown source type"):
        get_adapter("does-not-exist")
```

> `test_obsidian_is_markdown_subclass` will pass only after Task 8; mark it xfail until then or land Task 8 first. Recommended order: land the registry with `markdown` + `notion` + `apple_notes` mappings, then Tasks 8–11 fill in the classes.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_adapter_registry.py::test_resolves_bundled_markdown -v`
Expected: FAIL (`No module named 'scripts.adapter_registry'`).

- [ ] **Step 3: Write the registry**

Create `scripts/adapter_registry.py`:

```python
import importlib
import sys
from scripts.paths import adapters_dir

_BUNDLED = {
    "markdown": ("adapters.markdown", "MarkdownAdapter"),
    "obsidian": ("adapters.obsidian", "ObsidianAdapter"),
    "notion": ("adapters.notion", "NotionAdapter"),
    "apple_notes": ("adapters.apple_notes", "AppleNotesAdapter"),
}


def get_adapter(source_type: str):
    if source_type in _BUNDLED:
        mod_name, cls_name = _BUNDLED[source_type]
        return getattr(importlib.import_module(mod_name), cls_name)()
    # user-generated adapter in the data home
    user_dir = adapters_dir()
    candidate = user_dir / f"{source_type}.py"
    if candidate.exists():
        sys.path.insert(0, str(user_dir))
        mod = importlib.import_module(source_type)
        cls = next(v for k, v in vars(mod).items() if k.endswith("Adapter") and isinstance(v, type))
        return cls()
    raise ValueError(f"unknown source type: {source_type}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_adapter_registry.py::test_resolves_bundled_markdown tests/test_adapter_registry.py::test_unknown_type_raises -v`
Expected: PASS (2 tests; the obsidian test lands after Task 8).

- [ ] **Step 5: Rewrite `ingest.py`**

Replace `scripts/ingest.py` with:

```python
#!/usr/bin/env python3
"""MindGraph ingest — multi-source, two-phase (build graph, then derive/assign wings)."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.config import load_config
from scripts.adapter_registry import get_adapter

BATCH = ROOT / "skills/brain-ingest/scripts/batch_ingest.py"


def _fetch_all(config) -> list:
    chunks = []
    for source in config["sources"]:
        adapter = get_adapter(source["type"])
        got = adapter.fetch_and_validate(source)
        print(f"[INFO] {source['type']}: {len(got)} chunks", file=sys.stderr)
        chunks.extend(got)
    return chunks


def _concepts_by_note() -> dict:
    """Read expressed concepts per source_file from the KG."""
    import os, sqlite3
    db = os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3")
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT source_file, object FROM triples WHERE predicate='expresses'").fetchall()
    conn.close()
    out = {}
    for sf, concept in rows:
        out.setdefault(sf, []).append(concept)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--derive-wings", action="store_true")
    ap.add_argument("--assign-wings", action="store_true")
    args = ap.parse_args()
    config = load_config(args.config)

    if args.status:
        subprocess.run([sys.executable, str(BATCH), "--status"], check=True)
        return

    if args.derive_wings:
        from scripts.wing_deriver import propose_tree
        sys.path.insert(0, str(ROOT / "skills/brain-ingest/scripts"))
        from concept_extractor import get_provider
        tree = propose_tree(_concepts_by_note(), get_provider(config))
        print(json.dumps(tree, indent=2))
        return

    if args.assign_wings:
        from scripts.wing_deriver import assign, apply
        sys.path.insert(0, str(ROOT / "skills/brain-ingest/scripts"))
        from batch_ingest import get_chromadb_collection, get_kg
        assignments = assign(_concepts_by_note(), config["wings"])
        apply(assignments, get_chromadb_collection(), get_kg())
        counts = {}
        for wr in assignments.values():
            counts[wr["wing"]] = counts.get(wr["wing"], 0) + 1
        print(json.dumps({"assigned": counts}))
        return

    # Phase A
    chunks = _fetch_all(config)
    if not chunks:
        print("[WARN] No chunks found across configured sources.")
        return
    cmd = [sys.executable, str(BATCH)]
    if args.dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, input=json.dumps(chunks).encode())
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
```

Update `batch_ingest.py` to no longer require `--config`/`load_config` for chunk ingest (it already reads chunks from stdin); it does not need wing routing.

- [ ] **Step 6: Fixture integration run (Phase A + derive + assign on the fixture vault)**

Run:
```bash
export MINDGRAPH_HOME=$(mktemp -d)
printf 'sources:\n  - {type: markdown, path: tests/fixtures/notes}\nllm_provider: auto\nwings: []\ndefaults: {wing: inbox, room: general}\n' > "$MINDGRAPH_HOME/config.yml"
cp .env "$MINDGRAPH_HOME/.env" 2>/dev/null || true   # needs a real key for concept extraction
python3 scripts/ingest.py
python3 scripts/ingest.py --derive-wings
```
Expected: Phase A prints chunk counts and `[DONE]`; `--derive-wings` prints a nested JSON tree. (Requires a live LLM key; skip if unavailable and note it.)

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: multi-source two-phase ingest (Phase A + derive/assign wings)"
```

---

## Task 8: Obsidian adapter

**Files:**
- Create: `adapters/obsidian.py`, `tests/test_obsidian_adapter.py`, `tests/fixtures/obsidian_vault/`

**Interfaces:**
- Consumes: `MarkdownAdapter`.
- Produces: `ObsidianAdapter(MarkdownAdapter)` with `SOURCE_TYPE="obsidian"`; ignores `.obsidian/`; extracts `[[wikilinks]]` into `tags` and strips the brackets from text.

- [ ] **Step 1: Write the failing test + fixtures**

Create `tests/fixtures/obsidian_vault/note.md`:

```markdown
# Idea
This connects to [[activation]] and [[funnel design]].
```
Create `tests/fixtures/obsidian_vault/.obsidian/app.json` with `{}`.

Create `tests/test_obsidian_adapter.py`:

```python
from pathlib import Path
from adapters.obsidian import ObsidianAdapter

VAULT = Path(__file__).parent / "fixtures" / "obsidian_vault"


def test_ignores_obsidian_dir_and_extracts_wikilinks():
    chunks = ObsidianAdapter().fetch({"type": "obsidian", "path": str(VAULT)})
    assert all(".obsidian" not in c["source_file"] for c in chunks)
    joined_tags = [t for c in chunks for t in c["tags"]]
    assert "activation" in joined_tags and "funnel design" in joined_tags
    assert "[[" not in chunks[0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_obsidian_adapter.py -v`
Expected: FAIL (`No module named 'adapters.obsidian'`).

- [ ] **Step 3: Write implementation**

Create `adapters/obsidian.py`:

```python
import re
from pathlib import Path
from adapters.markdown import MarkdownAdapter, _parse_frontmatter, _parse_date, _chunk

_WIKILINK = re.compile(r"\[\[([^\]]+)\]\]")


class ObsidianAdapter(MarkdownAdapter):
    SOURCE_TYPE = "obsidian"

    def fetch(self, source: dict) -> list[dict]:
        folder = Path(source["path"]).expanduser()
        if not folder.exists():
            raise FileNotFoundError(f"source path not found: {folder}")
        chunks = []
        for md_file in sorted(folder.rglob("*.md")):
            if ".obsidian" in md_file.parts:
                continue
            rel = md_file.relative_to(folder)
            fm, body = _parse_frontmatter(md_file.read_text(encoding="utf-8"))
            links = _WIKILINK.findall(body)
            body = _WIKILINK.sub(lambda m: m.group(1).split("|")[0], body)
            title = fm.get("title", md_file.stem.replace("-", " ").title())
            filed_at = _parse_date(fm.get("date"), md_file)
            tags = list(fm.get("tags", [])) + links
            for chunk_text in _chunk(body):
                chunks.append({
                    "text": chunk_text, "source_file": f"obsidian:{rel}",
                    "wing": "inbox", "room": "general", "filed_at": filed_at,
                    "title": title, "tags": tags,
                })
        return chunks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_obsidian_adapter.py tests/test_adapter_registry.py -v`
Expected: PASS (obsidian test + the previously-pending registry test).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Obsidian adapter (wikilinks → tags, ignore .obsidian)"
```

---

## Task 9: Notion adapter

**Files:**
- Create: `adapters/notion.py`, `tests/test_notion_adapter.py`

**Interfaces:**
- Consumes: `AdapterBase`, `NOTION_TOKEN` from env, `_chunk` from markdown.
- Produces: `NotionAdapter` with `fetch(source)`, a `--test` CLI, and a `_extract(page_json, blocks_json) -> dict` pure function that maps a page + its blocks to a chunk-ready record (unit-tested with fixtures, no network).

- [ ] **Step 1: Write the failing test with mocked API JSON**

Create `tests/test_notion_adapter.py`:

```python
from adapters.notion import _plain_text, _extract


def test_plain_text_joins_rich_text():
    blocks = {"results": [
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Hello "}, {"plain_text": "world"}]}},
        {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Title"}]}},
    ]}
    assert _plain_text(blocks) == "Hello world\nTitle"


def test_extract_builds_namespaced_record():
    page = {"id": "abc-123", "created_time": "2026-01-02T00:00:00.000Z",
            "properties": {"title": {"title": [{"plain_text": "My Page"}]}}}
    blocks = {"results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Body text here."}]}}]}
    rec = _extract(page, blocks)
    assert rec["source_file"] == "notion:abc-123"
    assert rec["title"] == "My Page"
    assert rec["filed_at"] == "2026-01-02"
    assert "Body text here." in rec["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_notion_adapter.py -v`
Expected: FAIL (`No module named 'adapters.notion'`).

- [ ] **Step 3: Write implementation**

Create `adapters/notion.py`:

```python
#!/usr/bin/env python3
"""Notion adapter — Notion API via urllib, no SDK."""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.base import AdapterBase
from adapters.markdown import _chunk

API = "https://api.notion.com/v1"
VERSION = "2022-06-28"
CTX = ssl.create_default_context()


def _headers():
    token = os.environ["NOTION_TOKEN"]
    return {"Authorization": f"Bearer {token}", "Notion-Version": VERSION,
            "Content-Type": "application/json"}


def _post(path, body, retries=5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                         headers=_headers(), method="POST")
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt); continue
            raise ValueError(f"Notion API {e.code}: {e.read().decode()}")
    raise ValueError("Notion API failed after retries")


def _get(path, retries=5):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(f"{API}{path}", headers=_headers(), method="GET")
            with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt); continue
            raise ValueError(f"Notion API {e.code}: {e.read().decode()}")
    raise ValueError("Notion API failed after retries")


def _plain_text(blocks: dict) -> str:
    lines = []
    for b in blocks.get("results", []):
        payload = b.get(b.get("type"), {})
        rt = payload.get("rich_text", [])
        text = "".join(seg.get("plain_text", "") for seg in rt)
        if text:
            lines.append(text)
    return "\n".join(lines)


def _title_of(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in prop.get("title", [])) or "Untitled"
    return "Untitled"


def _extract(page: dict, blocks: dict) -> dict:
    return {
        "text": _plain_text(blocks),
        "source_file": f"notion:{page['id']}",
        "title": _title_of(page),
        "filed_at": page.get("created_time", "")[:10],
    }


class NotionAdapter(AdapterBase):
    def fetch(self, source: dict) -> list[dict]:
        pages, cursor = [], None
        while True:
            body = {"filter": {"property": "object", "value": "page"}, "page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            resp = _post("/search", body)
            pages.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")

        chunks = []
        for page in pages:
            blocks = _get(f"/blocks/{page['id']}/children?page_size=100")
            rec = _extract(page, blocks)
            for chunk_text in _chunk(rec["text"]):
                chunks.append({**rec, "text": chunk_text, "wing": "inbox",
                               "room": "general", "tags": []})
        return chunks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true")
    ap.parse_args()
    got = NotionAdapter().fetch({"type": "notion"})[:5]
    print(f"Fetched {len(got)} sample chunks")
    if got:
        print(json.dumps(got[0], indent=2))
```

- [ ] **Step 4: Run unit tests to verify they pass**

Run: `python3 -m pytest tests/test_notion_adapter.py -v`
Expected: PASS (2 tests — pure functions, no network).

- [ ] **Step 5: Live smoke (manual, needs a token)**

Run: `NOTION_TOKEN=secret_xxx python3 adapters/notion.py --test`
Expected: prints a sample `notion:<id>` chunk. Fix pagination/shape against the live response if needed.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: Notion adapter (urllib, paginated search + block text)"
```

---

## Task 10: Apple Notes adapter

**Files:**
- Create: `adapters/apple_notes.py`, `tests/test_apple_notes_adapter.py`

**Interfaces:**
- Consumes: `AdapterBase`, `osascript`, `_chunk`.
- Produces: `AppleNotesAdapter` (macOS-only guard); `_parse_export(raw: str) -> list[dict]` pure function that maps the AppleScript record-separated output into chunk-ready records (unit-tested, no `osascript`).

- [ ] **Step 1: Write the failing test with mocked osascript output**

Create `tests/test_apple_notes_adapter.py`:

```python
from adapters.apple_notes import _parse_export

RAW = (
    "NOTE\x1fWork\x1fMeeting notes\x1f2026-03-01\x1fDiscussed the funnel and churn.\x1e"
    "NOTE\x1fPersonal\x1fJournal\x1f2026-03-02\x1fFelt good about habits today.\x1e"
)


def test_parse_export_builds_records():
    recs = _parse_export(RAW)
    assert len(recs) == 2
    assert recs[0]["source_file"].startswith("apple_notes:")
    assert recs[0]["title"] == "Meeting notes"
    assert recs[0]["filed_at"] == "2026-03-01"
    assert "funnel" in recs[0]["text"]
    assert recs[0]["tags"] == ["Work"]  # folder recorded as a tag
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_apple_notes_adapter.py -v`
Expected: FAIL (`No module named 'adapters.apple_notes'`).

- [ ] **Step 3: Write implementation**

Create `adapters/apple_notes.py`:

```python
#!/usr/bin/env python3
"""Apple Notes adapter — exports via osascript (macOS only)."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.base import AdapterBase
from adapters.markdown import _chunk

FIELD, RECORD = "\x1f", "\x1e"

# Fields per note: folder, title, iso-date, body (plain text)
_SCRIPT = f'''
set out to ""
tell application "Notes"
  repeat with n in notes
    set f to name of container of n
    set t to name of n
    set d to (creation date of n) as «class isot» as string
    set b to plaintext of n
    set out to out & f & "{FIELD}" & t & "{FIELD}" & d & "{FIELD}" & b & "{RECORD}"
  end repeat
end tell
return out
'''


def _parse_export(raw: str) -> list[dict]:
    recs = []
    for chunk in raw.split(RECORD):
        if not chunk.strip():
            continue
        folder, title, date, body = (chunk.split(FIELD) + ["", "", "", ""])[:4]
        nid = hashlib.sha256((title + date).encode()).hexdigest()[:16]
        recs.append({
            "text": body.strip(),
            "source_file": f"apple_notes:{nid}",
            "title": title.strip() or "Untitled",
            "filed_at": date.strip()[:10],
            "tags": [folder.strip()] if folder.strip() else [],
        })
    return recs


class AppleNotesAdapter(AdapterBase):
    def fetch(self, source: dict) -> list[dict]:
        if sys.platform != "darwin":
            raise RuntimeError("Apple Notes is only available on macOS")
        proc = subprocess.run(["osascript", "-e", _SCRIPT], capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"osascript failed (grant Notes automation permission): {proc.stderr}")
        folders = source.get("folders")
        chunks = []
        for rec in _parse_export(proc.stdout):
            if folders and (rec["tags"] and rec["tags"][0] not in folders):
                continue
            for chunk_text in _chunk(rec["text"]):
                chunks.append({**rec, "text": chunk_text, "wing": "inbox", "room": "general"})
        return chunks


if __name__ == "__main__":
    argparse.ArgumentParser().parse_args()
    got = AppleNotesAdapter().fetch({"type": "apple_notes"})[:5]
    print(f"Fetched {len(got)} sample chunks")
    if got:
        print(json.dumps(got[0], indent=2))
```

- [ ] **Step 4: Run unit test to verify it passes**

Run: `python3 -m pytest tests/test_apple_notes_adapter.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: Apple Notes adapter (osascript export, macOS-only)"
```

---

## Task 11: check_env preflight

**Files:**
- Create: `scripts/check_env.py`, `tests/test_check_env.py`

**Interfaces:**
- Produces: `check() -> dict` with keys `python_ok: bool`, `python_version: str`, `mempalace: bool`, `keys: {gemini: bool, claude: bool}`, `ready: bool` (`python_ok and mempalace and (gemini or claude)`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_env.py`:

```python
import importlib
import scripts.paths as paths


def test_check_reports_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path))
    importlib.reload(paths)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=abc\n")
    import scripts.check_env as ce
    ce = importlib.reload(ce)
    result = ce.check()
    assert result["keys"]["gemini"] is True
    assert isinstance(result["python_ok"], bool)
    assert "python_version" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_check_env.py -v`
Expected: FAIL (`No module named 'scripts.check_env'`).

- [ ] **Step 3: Write implementation**

Create `scripts/check_env.py`:

```python
#!/usr/bin/env python3
import importlib.util
import json
import sys
from scripts.paths import env_path


def _env_keys() -> dict:
    keys = {"gemini": False, "claude": False}
    p = env_path()
    if p.is_file():
        text = p.read_text()
        keys["gemini"] = "GEMINI_API_KEY=" in text and not _blank(text, "GEMINI_API_KEY")
        keys["claude"] = "ANTHROPIC_API_KEY=" in text and not _blank(text, "ANTHROPIC_API_KEY")
    return keys


def _blank(text: str, key: str) -> bool:
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip() == ""
    return True


def check() -> dict:
    python_ok = sys.version_info >= (3, 11)
    mempalace = importlib.util.find_spec("mempalace") is not None
    keys = _env_keys()
    return {
        "python_ok": python_ok,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "mempalace": mempalace,
        "keys": keys,
        "ready": python_ok and mempalace and (keys["gemini"] or keys["claude"]),
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_check_env.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: check_env preflight (python, mempalace, keys)"
```

---

## Task 12: mindgraph-setup skill

**Files:**
- Create: `skills/mindgraph-setup/SKILL.md`

**Interfaces:**
- Consumes: `check_env.py`, `write_config.py`, `ingest.py`, `build-adapter` skill, all via `${CLAUDE_PLUGIN_ROOT}`.
- Produces: a conversational setup flow. Not unit-testable; verified by a dry walkthrough.

- [ ] **Step 1: Write the skill**

Create `skills/mindgraph-setup/SKILL.md`:

```markdown
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
Build the `sources` list and call `write_config.set_sources(...)` (run a short python -c, or
`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/write_config.py` with the sources on stdin).

### 4. First ingest (Phase A)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py`. Report the chunk/entity/triple counts.

### 5. Derive + confirm wings (Phase B)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py --derive-wings`. Show the proposed
wing→room tree in a readable outline. Let the user rename / merge / split / accept by talking.
Write the confirmed tree with `write_config.set_wings(...)`.

### 6. Assign (Phase C)
Run `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/ingest.py --assign-wings`. Report counts per wing.

### 7. Done
Suggest: "Ask me: 'what do my notes say about <topic>?'" (uses the brain-retrieve skill).
```

- [ ] **Step 2: Dry walkthrough verification**

In Claude Code (plugin installed), run `/mindgraph-setup` against the fixture vault with `MINDGRAPH_HOME` set to a temp dir. Confirm each step runs its script and the config file ends up populated.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: mindgraph-setup skill (conversational install + wing confirm)"
```

---

## Task 13: Update build-adapter skill + docs

**Files:**
- Modify: `skills/build-adapter/SKILL.md`
- Modify: repo-root `README.md`; create `plugins/mindgraph/README.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Update build-adapter contract**

In `skills/build-adapter/SKILL.md`: remove the "Wing/room routing must use config mappings" requirement; add "Every chunk must set `wing='inbox'`, `room='general'`; `source_file` must be `'<source>:<id>'`." Change the write target to `~/.mempalace/adapters/[source_slug].py` (the plugin dir is read-only) and the test command to `python3 ~/.mempalace/adapters/[source_slug].py --test`.

- [ ] **Step 2: Rewrite README install section**

Replace the Setup section of repo-root `README.md` with:

````markdown
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
````

Update the "How it works" and wing sections to describe concept-derived wings/rooms (delete folder-routing language). Add a one-paragraph `plugins/mindgraph/README.md` pointing back to the root.

- [ ] **Step 3: Full test sweep**

Run: `cd plugins/mindgraph && python3 -m pytest tests/ -v`
Expected: PASS (all unit tests across paths, config, write_config, wing_deriver, markdown, obsidian, notion, apple_notes, check_env, adapter_registry).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: plugin install + concept-derived wings; build-adapter contract update"
```

---

## Self-Review notes

- **Spec coverage:** plugin layout (T1), data home + read-only writes (T2), config v2 + migration (T3), adapter contract change (T4), write_config (T5), wing_deriver propose/assign/apply (T6), two-phase multi-source ingest (T7), Obsidian/Notion/Apple Notes adapters (T8–T10), check_env (T11), setup skill with live build-adapter (T12), build-adapter update + docs (T13). All spec sections mapped.
- **Deferred/covered-by-integration:** `wing_deriver.apply` has no isolated unit test (needs live ChromaDB/KG) — exercised in T7 Step 6.
- **Ordering note:** land T7's registry with all four type mappings before T8–T10 so `get_adapter` resolves; the obsidian registry test passes after T8.
