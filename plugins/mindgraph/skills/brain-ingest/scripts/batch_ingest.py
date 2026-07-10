#!/usr/bin/env python3
"""
batch_ingest.py — Ingest chunks into Mempalace (ChromaDB + KG).

Accepts pre-formed chunks from an adapter (via stdin or --chunks-file).
Adds to ChromaDB, extracts concepts, writes KG triples. Fully resumable.

Usage:
    python3 batch_ingest.py --chunks-file /tmp/chunks.json --config config.yml
    python3 batch_ingest.py --chunks-file /tmp/chunks.json --dry-run
    python3 batch_ingest.py --status
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

sys.path.insert(0, str(SCRIPT_DIR))
from concept_extractor import extract_concepts_batched, get_provider

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from paths import checkpoints_dir, env_path

CHECKPOINT_FILE = checkpoints_dir() / "batch_ingest_checkpoint.json"


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


_load_env()


def get_chromadb_collection():
    import chromadb
    palace_path = os.path.expanduser("~/.mempalace/palace")
    client = chromadb.PersistentClient(path=palace_path)
    return client.get_or_create_collection("mempalace_drawers")


def get_kg():
    from mempalace.knowledge_graph import KnowledgeGraph
    return KnowledgeGraph()


def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
        print(f"[RESUME] {data['processed_count']} chunks done, {len(data['vocabulary'])} concepts", file=sys.stderr)
        return data
    return {"processed_count": 0, "vocabulary": [], "triples_written": 0, "entities_created": 0}


def save_checkpoint(state: dict):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f, indent=2)


def fetch_existing_concepts(kg) -> list[str]:
    import sqlite3
    conn = sqlite3.connect(os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3"))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT name FROM entities WHERE type='concept' ORDER BY name").fetchall()
    conn.close()
    return [r["name"] for r in rows]


def write_to_kg(kg, results: list[dict], today: str) -> tuple[int, int]:
    import sqlite3
    entities_created = triples_written = 0
    for result in results:
        source_file = result.get("source_file", "")
        wing = result.get("wing", "")
        all_concepts = result.get("matched_concepts", []) + result.get("new_concepts", [])
        confidences = result.get("concept_confidences", {})
        for concept in all_concepts:
            if not concept or not isinstance(concept, str):
                continue
            confidence = confidences.get(concept, 1.0)
            conn = kg._conn()
            eid = concept.lower().replace(" ", "_").replace("'", "")
            if not conn.execute("SELECT id FROM entities WHERE id=?", (eid,)).fetchone():
                kg.add_entity(concept, "concept")
                entities_created += 1
            triple_id = kg.add_triple(
                subject=source_file, predicate="expresses", obj=concept,
                valid_from=today, source_closet=wing, source_file=source_file,
                confidence=confidence,
            )
            if triple_id:
                triples_written += 1
    return entities_created, triples_written


def add_to_chromadb(col, chunks: list[dict]) -> int:
    added = 0
    for chunk in chunks:
        chunk_id = f"{chunk.get('wing', '')}_{chunk.get('room', '')}_{hashlib.sha256(chunk['text'].encode()).hexdigest()[:24]}"
        try:
            col.add(
                ids=[chunk_id],
                documents=[chunk["text"]],
                metadatas=[{
                    "source_file": chunk.get("source_file", ""),
                    "wing": chunk.get("wing", ""),
                    "room": chunk.get("room", ""),
                    "filed_at": chunk.get("filed_at", ""),
                    "title": chunk.get("title", ""),
                }],
            )
            added += 1
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"[WARN] ChromaDB add failed: {e}", file=sys.stderr)
    return added


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks-file")
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("[RESET] Checkpoint cleared.", file=sys.stderr)

    repo_root = Path(__file__).parent.parent.parent.parent
    sys.path.insert(0, str(repo_root / "scripts"))
    from config import load_config
    config = load_config(args.config)

    if args.status:
        state = load_checkpoint()
        try:
            kg = get_kg()
            stats = kg.stats()
            kg.close()
            print(f"KG: {stats.get('entities', '?')} entities, {stats.get('triples', '?')} triples")
        except Exception as e:
            print(f"KG unavailable: {e}")
        print(f"Checkpoint: {state['processed_count']} chunks, {state['triples_written']} triples")
        return

    if args.dry_run:
        print("[DRY RUN] No writes will occur.", file=sys.stderr)

    if args.chunks_file:
        with open(args.chunks_file) as f:
            all_chunks = json.load(f)
    else:
        all_chunks = json.loads(sys.stdin.read())

    state = load_checkpoint()
    today = date.today().isoformat()
    current_vocab = list(state["vocabulary"])

    col = None
    kg = None
    provider = None
    if not args.dry_run:
        col = get_chromadb_collection()
        kg = get_kg()
        provider = get_provider(config)
        if state["processed_count"] == 0:
            for c in fetch_existing_concepts(kg):
                if c not in current_vocab:
                    current_vocab.append(c)

    offset = state["processed_count"]
    total = len(all_chunks)
    page_size = args.page_size
    total_entities = state.get("entities_created", 0)
    total_triples = state.get("triples_written", 0)

    while offset < total:
        page = all_chunks[offset: offset + page_size]
        page_num = offset // page_size + 1
        total_pages = (total + page_size - 1) // page_size
        print(f"\n[PAGE {page_num}/{total_pages}] chunks {offset+1}–{offset+len(page)}/{total}", file=sys.stderr)

        if not args.dry_run and col:
            added = add_to_chromadb(col, page)
            print(f"  ChromaDB: +{added} chunks", file=sys.stderr)

        keyed = [{"id": f"{c.get('wing','')}_{c.get('room','')}_{i+offset}", **c} for i, c in enumerate(page)]
        if not args.dry_run and provider:
            extraction_results, current_vocab = extract_concepts_batched(
                keyed, current_vocab, provider=provider, batch_size=args.batch_size,
            )
        else:
            extraction_results = []

        if not args.dry_run and kg:
            entities_created, triples_written = write_to_kg(kg, extraction_results, today)
            total_entities += entities_created
            total_triples += triples_written

        offset += len(page)
        state.update({"processed_count": offset, "vocabulary": current_vocab,
                       "triples_written": total_triples, "entities_created": total_entities})
        save_checkpoint(state)

        if offset < total:
            time.sleep(1.0)

    if kg:
        kg.close()

    summary = {"status": "complete", "chunks_processed": offset,
                "entities_created": total_entities, "triples_written": total_triples}
    print(f"\n[DONE] {offset} chunks | {total_entities} entities | {total_triples} triples")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
