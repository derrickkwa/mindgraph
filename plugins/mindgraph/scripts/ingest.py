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
