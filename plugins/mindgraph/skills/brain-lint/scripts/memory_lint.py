#!/usr/bin/env python3
"""Lint Claude Code auto-memory folders, across every project.

Errors: MEMORY.md over the load ceiling; a memory file not reachable from
MEMORY.md directly or via one hub; a [[link]] that near-matches an existing
file (hyphen/underscore/case typo). Warnings: a [[link]] matching nothing
(may be an intentional "write this later" marker); memory-wing sync drift.
JSON output. Never calls an LLM.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from scripts.memory_sync import is_eligible, _where, source_file_for, projects_dir, get_collection

INDEX = "MEMORY.md"
INDEX_MAX_BYTES = 16384
WIKI_LINK = re.compile(r"\[\[([^\]]+)\]\]")
MD_LINK = re.compile(r"\]\(([^)\s]+\.md)\)")
FRONTMATTER_BLOCK = re.compile(r"\A---\n(.*?)\n---", re.S)
FM_NAME = re.compile(r"^name:\s*\"?([^\"\n]+)\"?\s*$", re.M)


def _norm(s):
    return s.strip().lower().replace("-", "_").removesuffix(".md")


def _load(memory_dir):
    files = {}
    for n in sorted(os.listdir(memory_dir)):
        if n.endswith(".md"):
            with open(os.path.join(memory_dir, n), encoding="utf-8") as f:
                text = f.read()
            name = ""
            fm = FRONTMATTER_BLOCK.match(text)
            if fm:
                m = FM_NAME.search(fm.group(1))
                if m:
                    name = m.group(1).strip()
            files[n] = {"text": text, "name": name}
    return files


def _targets(files):
    exact = {}
    for n, info in files.items():
        exact[n[:-3]] = n
        exact[n] = n
        if info["name"]:
            exact[info["name"]] = n
    norm = {_norm(k): v for k, v in exact.items()}
    return exact, norm


def _reachable(files):
    index = files.get(INDEX, {}).get("text", "")
    exact, _ = _targets(files)
    direct = {exact[t] for t in MD_LINK.findall(index) + WIKI_LINK.findall(index) if t in exact}
    reach = set(direct)
    for hub in [n for n in direct if n.startswith("hub_") or n == "archive.md"]:
        text = files[hub]["text"]
        reach |= {exact[t] for t in MD_LINK.findall(text) + WIKI_LINK.findall(text) if t in exact}
    return reach


def lint(memory_dir, col=None, project=None, max_bytes=INDEX_MAX_BYTES):
    files = _load(memory_dir)
    exact, norm = _targets(files)
    errors, warnings = [], []

    size = len(files.get(INDEX, {}).get("text", "").encode("utf-8"))
    if size > max_bytes:
        errors.append({"check": "index_size", "bytes": size, "limit": max_bytes})

    reach = _reachable(files)
    for n in files:
        if n != INDEX and n not in reach:
            errors.append({"check": "unreachable", "file": n})

    for n, info in files.items():
        for link in sorted(set(WIKI_LINK.findall(info["text"]))):
            if link in exact:
                continue
            if _norm(link) in norm:
                errors.append({"check": "near_match_link", "file": n, "link": link,
                               "suggest": norm[_norm(link)][:-3]})
            else:
                warnings.append({"check": "dangling_link", "file": n, "link": link})

    if col is not None:
        prefix = source_file_for(project, "") if project else "memory/"
        indexed = {m["source_file"][len(prefix):]
                   for m in (col.get(where=_where(project=project), include=["metadatas"]).get("metadatas") or [])}
        eligible = {n for n in files if is_eligible(n)}
        warnings += [{"check": "sync_missing", "file": n} for n in sorted(eligible - indexed)]
        warnings += [{"check": "sync_orphan", "file": n} for n in sorted(indexed - eligible)]
        warnings += _hnsw_canary(col, project)

    return {"errors": errors, "warnings": warnings,
            "stats": {"files": len(files), "index_bytes": size, "reachable": len(reach)}}


def _hnsw_canary(col, project, limit=5):
    """SQLite (col.get) and the HNSW vector index can drift apart — a chunk
    present in the metadata store but missing from the ANN index is
    retrievable by exact id but invisible to semantic search. Spot-check up
    to `limit` memory-wing chunks (deterministic: sorted by source_file, then
    chunk_index) by querying the collection with the chunk's own text and
    checking whether its own id comes back. Scoped to a single project when
    one is given, else the whole memory wing."""
    where = _where(project=project)
    res = col.get(where=where, include=["documents", "metadatas"])
    rows = sorted(
        zip(res.get("ids") or [], res.get("documents") or [], res.get("metadatas") or []),
        key=lambda r: (r[2].get("source_file", ""), r[2].get("chunk_index", 0)),
    )
    warnings = []
    for chunk_id, doc, meta in rows[:limit]:
        found = col.query(query_texts=[doc], n_results=3, where=where).get("ids") or [[]]
        if chunk_id not in found[0]:
            warnings.append({"check": "sync_vector_missing", "file": meta.get("source_file", ""),
                             "id": chunk_id})
    return warnings


def lint_all(col=None, max_bytes=INDEX_MAX_BYTES):
    projects = {}
    root = projects_dir()
    if root.is_dir():
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            mem_dir = entry / "memory"
            if (mem_dir / INDEX).exists():
                projects[entry.name] = lint(str(mem_dir), col, entry.name, max_bytes=max_bytes)
    return {"projects": projects}


def fix_near_matches(memory_dir):
    fixes = []
    for f in lint(memory_dir)["errors"]:
        if f["check"] != "near_match_link":
            continue
        path = os.path.join(memory_dir, f["file"])
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        new = text.replace(f"[[{f['link']}]]", f"[[{f['suggest']}]]")
        if new != text:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
            fixes.append({"file": f["file"], "from": f["link"], "to": f["suggest"]})
    return fixes


def _infer_project_from_memory_dir(memory_dir):
    """If memory_dir resolves to <projects_dir>/<slug>/memory, return <slug>.
    Otherwise return None."""
    resolved = Path(memory_dir).resolve()
    base = projects_dir().resolve()
    try:
        rel = resolved.relative_to(base)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) == 2 and parts[1] == "memory":
        return parts[0]
    return None


def _project_memory_dir(slug):
    """Return the memory dir for a project slug, or print a JSON error and
    exit 1 if that project has no memory folder."""
    memory_dir = projects_dir() / slug / "memory"
    if not memory_dir.is_dir():
        print(json.dumps({"error": f"no memory folder for project {slug} under {projects_dir()}"}))
        sys.exit(1)
    return str(memory_dir)


def _default_max_bytes():
    try:
        from scripts.config import load_config
        cfg = load_config()
    except Exception:
        return INDEX_MAX_BYTES
    return int((cfg.get("memory") or {}).get("index_max_bytes") or INDEX_MAX_BYTES)


def main():
    ap = argparse.ArgumentParser(description="Lint Claude Code auto-memory folders")
    ap.add_argument("--project", metavar="SLUG")
    ap.add_argument("--memory-dir")
    ap.add_argument("--check-sync", action="store_true")
    ap.add_argument("--fix-near-matches", action="store_true")
    ap.add_argument("--max-bytes", type=int, default=_default_max_bytes())
    args = ap.parse_args()

    if args.fix_near_matches:
        if args.memory_dir:
            memory_dir = args.memory_dir
        elif args.project:
            memory_dir = str(projects_dir() / args.project / "memory")
        else:
            print(json.dumps({"error": "--fix-near-matches requires --project or --memory-dir"}))
            sys.exit(1)
        print(json.dumps({"fixed": fix_near_matches(memory_dir)}))
        return

    if args.memory_dir:
        memory_dir = args.memory_dir
        project = args.project
        if args.check_sync and project is None:
            project = _infer_project_from_memory_dir(memory_dir)
            if project is None:
                print(json.dumps({"error": "--check-sync with --memory-dir needs --project "
                                            "<slug> (could not infer it from the path)"}))
                sys.exit(1)
    elif args.project:
        memory_dir = _project_memory_dir(args.project)
        project = args.project
    else:
        memory_dir = None
        project = None

    col = None
    if args.check_sync:
        try:
            col = get_collection()
        except Exception as exc:
            print(json.dumps({"error": f"palace not found; run /mindgraph-setup first: {exc}"}))
            sys.exit(1)

    if memory_dir is not None:
        print(json.dumps(lint(memory_dir, col, project, max_bytes=args.max_bytes)))
    else:
        print(json.dumps(lint_all(col, max_bytes=args.max_bytes)))


if __name__ == "__main__":
    main()
