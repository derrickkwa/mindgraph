#!/usr/bin/env python3
"""Consensus gate for FORK dissent layer.

Scores how tightly a set of retrieved chunks cluster in embedding space.
Used as a CHEAP GATE only — a high score means the chunks are topically
close, NOT that they share a stance. The skill's stance read is the real
filter. This deliberately over-fires; raise THRESHOLD if it fires too often.

Skills call `--query "<the search query>"`. `--source-files` needs full
stored names; search results return basenames, so never feed them here.
"""
import argparse
import json

import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paths import palace_dir

# --- Tuning knobs (calibrate against the live corpus) ---
THRESHOLD = 0.55      # mean pairwise cosine above this = "tight" cluster
MIN_SOURCES = 3        # fewer than this = not enough to call a consensus

MEMORY_PREFIX = "memory/"  # Claude's own conclusions — never count as note consensus


def exclude_memory(source_files):
    return [s for s in (source_files or []) if not str(s).startswith(MEMORY_PREFIX)]


def mean_pairwise_cosine(embeddings):
    """Mean cosine similarity over all distinct pairs. Normalizes inputs."""
    e = np.asarray(embeddings, dtype=float)
    if e.ndim != 2 or e.shape[0] < 2:
        return 1.0
    norms = np.linalg.norm(e, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    e = e / norms
    sim = e @ e.T
    n = e.shape[0]
    iu = np.triu_indices(n, k=1)
    return float(sim[iu].mean())


def evaluate(embeddings, threshold=THRESHOLD, min_sources=MIN_SOURCES):
    n = len(embeddings)
    score_val = mean_pairwise_cosine(embeddings) if n >= 2 else 1.0
    is_tight = bool(n >= min_sources and score_val >= threshold)
    return {
        "consensus_score": round(score_val, 4),
        "is_tight": is_tight,
        "threshold": threshold,
        "n_sources": n,
    }


def _dedupe_by_source(embeddings, metadatas):
    """Keep one embedding per distinct source_file. Chunks of the same note
    collapse to a single vote, so one multi-chunk note can't masquerade as
    consensus (n_sources then counts distinct notes, not chunks). Preserves
    first-seen order."""
    seen = set()
    out = []
    for emb, meta in zip(embeddings, metadatas):
        sf = (meta or {}).get("source_file")
        if sf in seen:
            continue
        seen.add(sf)
        out.append(emb)
    return out


def _get_collection(palace_path=None, embedding_function=None):
    import chromadb
    settings = chromadb.config.Settings(anonymized_telemetry=False)
    client = chromadb.PersistentClient(path=str(palace_path or palace_dir()), settings=settings)
    if embedding_function is not None:
        return client.get_or_create_collection("mempalace_drawers", embedding_function=embedding_function)
    return client.get_collection("mempalace_drawers")


def _fetch_embeddings(source_files=None, query=None, palace_path=None, embedding_function=None):
    col = _get_collection(palace_path, embedding_function)
    if source_files:
        res = col.get(where={"$and": [{"source_file": {"$in": list(source_files)}},
                                       {"wing": {"$ne": "memory"}}]},
                      include=["embeddings", "metadatas"])
        embeddings = res.get("embeddings")
        metadatas = res.get("metadatas")
        return _dedupe_by_source(embeddings if embeddings is not None else [],
                                 metadatas if metadatas is not None else [])
    if query:
        res = col.query(query_texts=[query], n_results=10, include=["embeddings", "metadatas"],
                        where={"wing": {"$ne": "memory"}})
        embs = res.get("embeddings")
        metas = res.get("metadatas")
        if embs is None or not len(embs):
            return []
        return _dedupe_by_source(embs[0], metas[0] if metas is not None else [])
    return []


def score(source_files=None, query=None, threshold=THRESHOLD, palace_path=None):
    if source_files is not None:
        source_files = exclude_memory(source_files)
        if not source_files:
            return evaluate([], threshold=threshold)
    embeddings = _fetch_embeddings(source_files=source_files, query=query, palace_path=palace_path)
    return evaluate(embeddings, threshold=threshold)


def main():
    ap = argparse.ArgumentParser(description="FORK consensus gate")
    ap.add_argument("--source-files", nargs="*", default=None)
    ap.add_argument("--query", default=None)
    ap.add_argument("--threshold", type=float, default=THRESHOLD)
    ap.add_argument("--palace", default=None)
    args = ap.parse_args()
    try:
        result = score(source_files=args.source_files,
                        query=args.query,
                        threshold=args.threshold,
                        palace_path=args.palace)
    except Exception as exc:
        palace_path = args.palace or palace_dir()
        print(json.dumps({"error": f"palace not found at {palace_path}; "
                                    f"run /mindgraph-setup first: {exc}"}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
