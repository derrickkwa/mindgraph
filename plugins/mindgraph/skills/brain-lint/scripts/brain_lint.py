#!/usr/bin/env python3
"""
brain_lint.py — Concept graph health check

Scans the KG for:
1. Noise concepts: fewer than MIN_LINKS links (likely over-extracted, low signal)
2. Duplicate candidates: concept names with high string similarity (potential merges)
3. Synthesis gaps: high-link concepts with no wiki page
4. Orphaned wiki pages: wiki pages with no matching concept in KG

Output: JSON report to stdout.

Usage:
    python3 brain_lint.py [--min-links N] [--wiki-dir PATH] [--top-gaps N]
"""

import sqlite3
import os
import json
import argparse
import re
from pathlib import Path
from difflib import SequenceMatcher


KG_PATH = os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3")
DEFAULT_WIKI_DIR = "_wiki"
DEFAULT_MIN_LINKS = 3
DEFAULT_TOP_GAPS = 20


def get_all_concepts(conn):
    """Return all concept nodes with link counts."""
    rows = conn.execute("""
        SELECT e.name, COUNT(t.id) as link_count
        FROM entities e
        LEFT JOIN triples t
            ON t.object = e.name
            AND t.predicate = 'expresses'
            AND t.valid_to IS NULL
        WHERE e.type = 'concept'
        GROUP BY e.name
        ORDER BY link_count DESC
    """).fetchall()
    return [{"name": r["name"], "link_count": r["link_count"]} for r in rows]


def find_noise_concepts(concepts, min_links):
    """Concepts with fewer than min_links links."""
    return [c for c in concepts if c["link_count"] < min_links]


def find_duplicate_candidates(concepts, threshold=0.85, max_candidates=50):
    """
    Find concept name pairs with high string similarity.
    Only checks concepts with >= 3 links to avoid noise-noise comparisons.
    """
    viable = [c for c in concepts if c["link_count"] >= 3]
    candidates = []

    for i, a in enumerate(viable):
        for b in viable[i + 1:]:
            ratio = SequenceMatcher(None, a["name"], b["name"]).ratio()
            if ratio >= threshold:
                candidates.append({
                    "concept_a": a["name"],
                    "links_a": a["link_count"],
                    "concept_b": b["name"],
                    "links_b": b["link_count"],
                    "similarity": round(ratio, 3),
                })
            if len(candidates) >= max_candidates:
                break
        if len(candidates) >= max_candidates:
            break

    return sorted(candidates, key=lambda x: -x["similarity"])


def find_wiki_pages(wiki_dir):
    """Recursively find all .md wiki pages (excluding index.md and log.md)."""
    wiki_path = Path(wiki_dir)
    pages = []
    for p in wiki_path.rglob("*.md"):
        name = p.name
        if name in ("index.md", "log.md", "cross-domain.md"):
            continue
        # Derive concept name from filename (strip .md, already hyphenated)
        concept_name = p.stem  # e.g. "performance-measurement"
        rel_path = str(p.relative_to(wiki_path))
        pages.append({
            "path": rel_path,
            "concept_name": concept_name,
            "abs_path": str(p),
        })
    return pages


def find_synthesis_gaps(concepts, wiki_pages, top_n, min_links_for_gap=20):
    """
    High-link concepts with no wiki page.
    Only flags concepts with >= min_links_for_gap links.
    """
    wiki_concept_names = {p["concept_name"] for p in wiki_pages}
    gaps = []
    for c in concepts:
        if c["link_count"] < min_links_for_gap:
            break  # concepts are sorted desc by link_count
        if c["name"] not in wiki_concept_names:
            gaps.append({
                "concept": c["name"],
                "link_count": c["link_count"],
            })
        if len(gaps) >= top_n:
            break
    return gaps


def find_orphaned_wiki_pages(concepts, wiki_pages):
    """Wiki pages whose concept name doesn't match any KG concept."""
    kg_concept_names = {c["name"] for c in concepts}
    orphaned = []
    for p in wiki_pages:
        if p["concept_name"] not in kg_concept_names:
            orphaned.append({
                "path": p["path"],
                "concept_name": p["concept_name"],
            })
    return orphaned


def find_low_confidence_concepts(conn, threshold=0.6, min_links=3) -> list[dict]:
    """
    Concepts where the average triple confidence is below threshold.
    Only checks viable concepts (>= min_links) to exclude noise.
    Low-confidence concepts that aren't corroborated by high-confidence links
    are pruning candidates.
    """
    rows = conn.execute("""
        SELECT
            t.object as concept,
            COUNT(t.id) as link_count,
            AVG(t.confidence) as avg_confidence,
            SUM(CASE WHEN t.confidence >= 0.8 THEN 1 ELSE 0 END) as high_conf_count,
            SUM(CASE WHEN t.confidence < 0.6 THEN 1 ELSE 0 END) as low_conf_count
        FROM triples t
        WHERE t.predicate = 'expresses'
            AND t.valid_to IS NULL
            AND t.confidence IS NOT NULL
            AND t.confidence < 1.0
        GROUP BY t.object
        HAVING link_count >= ? AND avg_confidence < ?
        ORDER BY avg_confidence ASC
        LIMIT 30
    """, (min_links, threshold)).fetchall()
    return [
        {
            "concept": r["concept"],
            "link_count": r["link_count"],
            "avg_confidence": round(r["avg_confidence"], 3),
            "high_conf_count": r["high_conf_count"],
            "low_conf_count": r["low_conf_count"],
        }
        for r in rows
    ]


def get_confidence_distribution(conn) -> dict:
    """Distribution of triple confidence values."""
    rows = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN confidence >= 0.9 THEN 1 ELSE 0 END) as high,
            SUM(CASE WHEN confidence >= 0.7 AND confidence < 0.9 THEN 1 ELSE 0 END) as medium,
            SUM(CASE WHEN confidence < 0.7 THEN 1 ELSE 0 END) as low,
            SUM(CASE WHEN confidence = 1.0 OR confidence IS NULL THEN 1 ELSE 0 END) as legacy
        FROM triples
        WHERE predicate = 'expresses' AND valid_to IS NULL
    """).fetchone()
    if not rows or not rows["total"]:
        return {}
    return {
        "total": rows["total"],
        "high_confidence": rows["high"],
        "medium_confidence": rows["medium"],
        "low_confidence": rows["low"],
        "legacy_no_confidence": rows["legacy"],
    }


def wing_spread(conn, concept_name):
    """Return wing distribution for a concept."""
    rows = conn.execute("""
        SELECT source_closet as wing, COUNT(*) as n
        FROM triples
        WHERE object = ? AND predicate = 'expresses' AND valid_to IS NULL
        GROUP BY source_closet
        ORDER BY n DESC
    """, (concept_name,)).fetchall()
    return {r["wing"]: r["n"] for r in rows}


def main():
    parser = argparse.ArgumentParser(description="Concept graph health check")
    parser.add_argument("--min-links", type=int, default=DEFAULT_MIN_LINKS,
                        help=f"Noise threshold (default: {DEFAULT_MIN_LINKS})")
    parser.add_argument("--wiki-dir", default=DEFAULT_WIKI_DIR,
                        help="Path to _wiki/ directory")
    parser.add_argument("--top-gaps", type=int, default=DEFAULT_TOP_GAPS,
                        help=f"How many synthesis gaps to surface (default: {DEFAULT_TOP_GAPS})")
    parser.add_argument("--similarity-threshold", type=float, default=0.85,
                        help="String similarity threshold for duplicate detection (default: 0.85)")
    args = parser.parse_args()

    conn = sqlite3.connect(KG_PATH)
    conn.row_factory = sqlite3.Row

    concepts = get_all_concepts(conn)
    wiki_pages = find_wiki_pages(args.wiki_dir)

    noise = find_noise_concepts(concepts, args.min_links)
    duplicates = find_duplicate_candidates(concepts, threshold=args.similarity_threshold)
    gaps = find_synthesis_gaps(concepts, wiki_pages, args.top_gaps)
    orphaned = find_orphaned_wiki_pages(concepts, wiki_pages)
    low_confidence = find_low_confidence_concepts(conn)
    confidence_dist = get_confidence_distribution(conn)

    # Summary stats
    total_concepts = len(concepts)
    noise_count = len(noise)
    viable_count = total_concepts - noise_count
    wiki_count = len(wiki_pages)

    report = {
        "summary": {
            "total_concepts": total_concepts,
            "viable_concepts": viable_count,
            "noise_concepts": noise_count,
            "wiki_pages": wiki_count,
            "synthesis_gaps_found": len(gaps),
            "duplicate_candidates_found": len(duplicates),
            "orphaned_wiki_pages": len(orphaned),
            "low_confidence_concepts": len(low_confidence),
        },
        "confidence_distribution": confidence_dist,
        "synthesis_gaps": gaps,
        "duplicate_candidates": duplicates[:15],  # top 15
        "orphaned_wiki_pages": orphaned,
        "low_confidence_concepts": low_confidence,
        "noise_sample": [c["name"] for c in noise[:20]],  # sample only
        "noise_full_count": noise_count,
    }

    conn.close()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
