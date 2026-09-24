#!/usr/bin/env python3
"""Mirror per-project Claude Code auto-memory files into the Mempalace
`memory` wing.

Memory files live under `<CLAUDE_PROJECTS_DIR>/<project>/memory/`. Each
project's files are synced independently, and the same filename in two
different projects never collides — the source_file is prefixed with the
project slug.

Mempalace chunk IDs are content hashes, so re-adding an edited file would
leave the old chunk searchable next to the new one. Every sync therefore
deletes the file's chunks first, then adds the current version. Every delete
is scoped to wing == "memory" — the palace is shared with MindGraph and notes.
JSON output. Never calls an LLM. No KG concept extraction.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import sys
sys.dont_write_bytecode = True
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paths import data_home, palace_dir

COLLECTION = "mempalace_drawers"
WING = "memory"
MAX_CHUNK_CHARS = 4000
EXCLUDED_NAMES = {"MEMORY.md", "archive.md"}
_WING_CLAUSE = {"wing": {"$eq": WING}}
_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.S)
_META_LINE = re.compile(r"\s*(name|description|type):\s*(.*)$")


def projects_dir() -> Path:
    raw = os.environ.get("CLAUDE_PROJECTS_DIR")
    return Path(raw).expanduser() if raw else Path.home() / ".claude" / "projects"


def lock_path() -> Path:
    return data_home() / "palace.write.lock"


def hook_log_path() -> Path:
    return data_home() / "logs" / "memory_sync_hook.log"


def project_of(path):
    p = Path(path).resolve()
    root = projects_dir().resolve()
    try:
        rel = p.relative_to(root)
    except ValueError:
        return None
    parts = rel.parts
    return parts[0] if len(parts) == 3 and parts[1] == "memory" else None


def source_file_for(project, filename):
    return f"memory/{project}/{filename}"


@contextlib.contextmanager
def palace_write_lock(blocking=True):
    """Exclusive flock over lock_path(). No-op when
    MEMPALACE_WRITE_LOCK_HELD=1 — a parent process (daily_sync.py) already
    holds it; re-locking in a child would deadlock. When blocking=False,
    raises BlockingIOError if another process holds the lock."""
    if os.environ.get("MEMPALACE_WRITE_LOCK_HELD") == "1":
        yield
        return
    path = lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as lf:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        fcntl.flock(lf, flags)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def _maybe_locked(is_dry_run, fn, *args, **kwargs):
    """Run fn under the palace write lock unless is_dry_run (dry runs write
    nothing, so they take no lock)."""
    if is_dry_run:
        return fn(*args, **kwargs)
    with palace_write_lock():
        return fn(*args, **kwargs)


def is_eligible(filename):
    return (filename.endswith(".md") and filename not in EXCLUDED_NAMES
            and not filename.startswith("hub_"))


def parse_memory(text):
    meta, body = {}, text
    m = _FRONTMATTER.match(text)
    if m:
        body = text[m.end():]
        for line in m.group(1).splitlines():
            mm = _META_LINE.match(line)
            if mm and mm.group(1) not in meta:
                meta[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return meta, body.strip()


def chunk_body(body, max_chars=MAX_CHUNK_CHARS):
    if not body:
        return []
    if len(body) <= max_chars:
        return [body]
    chunks, cur = [], ""
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        if not para:
            continue
        while len(para) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            chunks.append(para[:max_chars])
            para = para[max_chars:]
        if cur and len(cur) + 2 + len(para) > max_chars:
            chunks.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        chunks.append(cur)
    return chunks


def build_records(project, filename, text):
    meta, body = parse_memory(text)
    sf = source_file_for(project, filename)
    now = dt.datetime.now().isoformat(timespec="seconds")
    ids, docs, metas = [], [], []
    room = meta.get("type") or "unknown"
    memory_name = meta.get("name", "")
    description = meta.get("description", "")
    for i, chunk in enumerate(chunk_body(body)):
        # Hash includes chunk content plus metadata (project, room, name,
        # description) so that frontmatter-only edits trigger re-sync
        h = hashlib.sha256(
            "\x1f".join([project, room, memory_name, description, chunk]).encode("utf-8")
        ).hexdigest()
        slot = hashlib.sha256(f"{sf}#{i}".encode("utf-8")).hexdigest()[:12]
        ids.append(f"drawer_memory_{slot}_{h[:12]}")
        docs.append(chunk)
        metas.append({"wing": WING, "room": room, "project": project,
                      "source_file": sf, "content_hash": h[:24], "added_by": "memory_sync",
                      "filed_at": now, "memory_name": memory_name,
                      "description": description, "chunk_index": i})
    return ids, docs, metas


def _where(source_file=None, project=None):
    clauses = [dict(_WING_CLAUSE)]
    if source_file is not None:
        clauses.append({"source_file": {"$eq": source_file}})
    if project is not None:
        clauses.append({"project": {"$eq": project}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _has_wing_clause(where):
    return where == _WING_CLAUSE or _WING_CLAUSE in where.get("$and", [])


def safe_delete(col, where):
    if not _has_wing_clause(where):
        raise ValueError(f"refusing delete without wing == {WING!r} clause: {where}")
    col.delete(where=where)


def _existing(col, source_file):
    res = col.get(where=_where(source_file), include=["metadatas"])
    return sorted((m.get("chunk_index", 0), m.get("content_hash", ""))
                  for m in (res.get("metadatas") or []))


def sync_file(col, path, dry_run=False):
    filename = os.path.basename(path)
    project = project_of(path)
    if project is None:
        return {"file": filename, "action": "skipped", "deleted": 0, "added": 0}
    if not is_eligible(filename):
        return {"file": filename, "action": "skipped", "deleted": 0, "added": 0}
    sf = source_file_for(project, filename)
    old = _existing(col, sf)
    if not os.path.exists(path):
        if old and not dry_run:
            safe_delete(col, _where(sf))
        return {"file": filename, "action": "deleted" if old else "noop",
                "deleted": len(old), "added": 0}
    with open(path, encoding="utf-8") as f:
        ids, docs, metas = build_records(project, filename, f.read())
    new = sorted((m["chunk_index"], m["content_hash"]) for m in metas)
    if new == old:
        return {"file": filename, "action": "unchanged", "deleted": 0, "added": 0}
    if not dry_run:
        if old:
            safe_delete(col, _where(sf))
        if ids:
            col.add(ids=ids, documents=docs, metadatas=metas)
    return {"file": filename, "action": "synced", "deleted": len(old), "added": len(ids)}


def _summarize(results, errors):
    count = lambda a: sum(1 for r in results if r["action"] == a)
    return {"synced": count("synced"), "unchanged": count("unchanged"),
            "skipped": count("skipped"),
            "deleted": sum(r["deleted"] for r in results),
            "added": sum(r["added"] for r in results),
            "errors": errors,
            "files": [r for r in results if r["action"] != "unchanged"]}


def sync_project(col, project, dry_run=False):
    results, errors = [], []
    mem_dir = projects_dir() / project / "memory"
    on_disk = {n for n in os.listdir(mem_dir) if is_eligible(n)} if mem_dir.is_dir() else set()
    prefix = f"memory/{project}/"
    indexed = {m["source_file"][len(prefix):]
               for m in (col.get(where=_where(project=project), include=["metadatas"]).get("metadatas") or [])}
    for name in sorted(on_disk | indexed):
        try:
            results.append(sync_file(col, str(mem_dir / name), dry_run))
        except Exception as exc:  # one bad file must not stop the reconcile
            errors.append({"file": name, "error": str(exc)})
    return _summarize(results, errors)


def sync_all(col, dry_run=False):
    root = projects_dir()
    on_disk_projects = set()
    if root.is_dir():
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "memory").is_dir():
                on_disk_projects.add(entry.name)
    indexed_projects = {
        m.get("project") for m in (col.get(where=_where(), include=["metadatas"]).get("metadatas") or [])
        if m.get("project")
    }
    projects = on_disk_projects | indexed_projects
    summaries = [sync_project(col, project, dry_run) for project in sorted(projects)]
    merged = {"synced": 0, "unchanged": 0, "skipped": 0, "deleted": 0, "added": 0,
              "errors": [], "files": []}
    for s in summaries:
        for key in ("synced", "unchanged", "skipped", "deleted", "added"):
            merged[key] += s[key]
        merged["errors"] += s["errors"]
        merged["files"] += s["files"]
    return merged


def get_collection(palace_path=None, embedding_function=None):
    import chromadb
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    path = str(palace_path or palace_dir())
    client = chromadb.PersistentClient(path=path, settings=settings)
    if embedding_function is not None:
        # Test-only path: a real palace always already has the collection,
        # so production code fails loudly instead of silently recreating it.
        return client.get_or_create_collection(COLLECTION, embedding_function=embedding_function)
    return client.get_collection(COLLECTION)


def _log_hook_error(msg):
    log_path = hook_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().isoformat(timespec="seconds")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"{ts} {msg}\n")


def hook_enabled():
    cfg_path = Path(os.environ.get("MINDGRAPH_HOME") or (Path.home() / ".mempalace")).expanduser() / "config.yml"
    if not cfg_path.exists():
        return False
    try:
        from scripts.config import load_config
        cfg = load_config(cfg_path)
    except Exception:
        return False
    return bool((cfg.get("memory") or {}).get("sync_hook"))


def run_hook(stdin_text, collection_factory=get_collection, enabled=None):
    if not (hook_enabled() if enabled is None else enabled):
        return None
    try:
        payload = json.loads(stdin_text or "{}")
    except json.JSONDecodeError:
        return None
    path = ((payload or {}).get("tool_input") or {}).get("file_path", "")
    if not path.endswith(".md"):
        return None
    if project_of(path) is None:
        return None
    if not is_eligible(os.path.basename(path)):
        return None
    cm = palace_write_lock(blocking=False)
    try:
        cm.__enter__()
    except BlockingIOError:
        _log_hook_error("skipped (lock busy): " + os.path.basename(path))
        return {"file": os.path.basename(path), "action": "skipped_lock_busy", "deleted": 0, "added": 0}
    try:
        return sync_file(collection_factory(), path)
    finally:
        cm.__exit__(None, None, None)


def main():
    ap = argparse.ArgumentParser(
        description="Sync per-project Claude Code memory files into the Mempalace memory wing")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file")
    mode.add_argument("--project", metavar="SLUG")
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--hook", action="store_true", help="PostToolUse hook: read stdin JSON")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--palace", default=None)
    args = ap.parse_args()

    if args.hook:
        try:  # a hook must never block or crash the session, and must stay silent
            run_hook(sys.stdin.read(),
                     collection_factory=lambda: get_collection(args.palace or str(palace_dir())))
        except Exception as exc:
            _log_hook_error(str(exc))
        sys.exit(0)

    palace_path = args.palace or str(palace_dir())
    try:
        col = get_collection(palace_path)
    except Exception as exc:
        print(json.dumps({"error": f"palace not found at {palace_path}; run /mindgraph-setup first: {exc}"}))
        sys.exit(1)

    if args.all:
        result = _maybe_locked(args.dry_run, sync_all, col, dry_run=args.dry_run)
        print(json.dumps(result))
        if result["errors"]:
            sys.exit(1)
    elif args.project:
        result = _maybe_locked(args.dry_run, sync_project, col, args.project, dry_run=args.dry_run)
        print(json.dumps(result))
        if result["errors"]:
            sys.exit(1)
    else:
        print(json.dumps(_maybe_locked(args.dry_run, sync_file, col, args.file, dry_run=args.dry_run)))


if __name__ == "__main__":
    main()
