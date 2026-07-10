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
