#!/usr/bin/env python3
"""Belief ledger for the FORK dissent layer and memory conclusions.

Append-only event log at <data home>/beliefs/ledger.jsonl. Every change is a
new JSON line; nothing is edited or deleted. Current state is a fold over the
events, ordered by effective date (ties keep write order). Claude supplies
verdicts; this module records and folds them. Never generates prose, never
calls an LLM.

For memory-file keys (file stems), a file may carry several conclusions;
`--history` is the source of truth and `belief`/`confidence` reflect only the
latest event. Prefer sub-keys `<stem>--<claim-slug>` for new multi-verdict
files. Shell-quote CLI text with single quotes — `$` amounts are otherwise
lost.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.paths import data_home

VALID_STATES = ("untested", "leaning", "solid", "shaky", "flipped")
EVENT_TYPES = ("concluded", "surfaced", "tested", "revised")
REVISION_KINDS = ("reversal", "refinement")
COOLDOWN_DAYS = 30

LEDGER_PATH = None  # override (tests); default resolves under the data home
VIEW_PATH = None


def ledger_path():
    return LEDGER_PATH or str(data_home() / "beliefs" / "ledger.jsonl")


def view_path():
    return VIEW_PATH or str(data_home() / "beliefs" / "ledger.md")


_VIEW_HEADER = ("<!-- GENERATED from ledger.jsonl by belief_ledger.py --render. "
                "Do not edit. -->\n")


@contextlib.contextmanager
def _lock():
    path = ledger_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".lock", "w") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)


def apply_verdict(current, verdict, counter_kind):
    if verdict == "survived":
        if counter_kind == "external":
            return "solid"
        return "leaning" if current in (None, "untested") else current
    if verdict == "weakened":
        return "shaky"
    if verdict == "flipped":
        return "flipped"
    raise ValueError(f"unknown verdict: {verdict}")


def in_cooldown(entry, today, days=COOLDOWN_DAYS):
    last = (entry or {}).get("last_tested", "")
    if not last:
        return False
    return (today - dt.date.fromisoformat(last)).days < days


# --- storage -----------------------------------------------------------------

def load_events():
    path = ledger_path()
    if not os.path.exists(path):
        return []
    events = []
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            if not raw.strip():
                continue
            try:
                ev = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{n}: malformed ledger line") from exc
            if ev.get("type") not in EVENT_TYPES or not ev.get("key") or not ev.get("date"):
                raise ValueError(f"{path}:{n}: invalid event {raw.strip()[:80]}")
            events.append(ev)
    return events


def _append(event):
    line = json.dumps(event, ensure_ascii=False, sort_keys=True)
    with _lock():
        with open(ledger_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())


def _event(type_, concept, today, **fields):
    if not concept or not isinstance(concept, str):
        raise ValueError("concept is required")
    d = today or dt.date.today()
    if d > dt.date.today():
        raise ValueError(f"effective date {d.isoformat()} is in the future")
    ev = {"type": type_, "key": concept, "date": d.isoformat(),
          "recorded": dt.datetime.now().isoformat(timespec="seconds")}
    ev.update({k: v for k, v in fields.items() if v not in (None, "", [])})
    return ev


# --- fold --------------------------------------------------------------------

def _new_entry(key, date):
    return {"key": key, "belief": "", "concepts": [], "confidence": "untested",
            "first_seen": date, "last_tested": "", "counter_sources": [],
            "memory_file": "", "history": []}


def _ordered(events):
    return [ev for _, ev in sorted(enumerate(events), key=lambda p: (p[1]["date"], p[0]))]


def fold(events):
    entries = {}
    for ev in _ordered(events):
        d = ev["date"]
        e = entries.setdefault(ev["key"], _new_entry(ev["key"], d))
        if ev.get("concepts"):
            e["concepts"] = list(ev["concepts"])
        if ev.get("memory_file"):
            e["memory_file"] = ev["memory_file"]
        t = ev["type"]
        if t == "concluded":
            e["belief"] = ev["belief"]
            e["history"].append(f"{d} concluded: {ev['belief']}")
        elif t == "surfaced":
            if ev.get("belief") and not e["belief"]:
                e["belief"] = ev["belief"]
            e["history"].append(f"{d} surfaced on pulse (stance: {ev.get('stance', '')}; "
                                f"counter: {ev.get('counter', '')}) [{e['confidence']}]")
        elif t == "tested":
            if ev.get("belief") and not e["belief"]:
                e["belief"] = ev["belief"]
            old = e["confidence"]
            e["confidence"] = apply_verdict(old, ev["verdict"], ev["counter_kind"])
            e["last_tested"] = d
            src = ev.get("source_ref")
            if ev["counter_kind"] == "external" and src and src not in e["counter_sources"]:
                e["counter_sources"].append(src)
            if ev["verdict"] == "flipped" and ev.get("new_belief"):
                e["belief"] = ev["new_belief"]
            counter = ev.get("counter", "")
            txt = f": {counter}" if counter else ""
            e["history"].append(f"{d} tested — {ev['verdict']} {ev['counter_kind']} "
                                f"counter{txt} ({old} -> {e['confidence']})")
        elif t == "revised":
            e["belief"] = ev["new"]
            if ev["revision_kind"] == "reversal":
                e["confidence"] = "flipped"
            e["history"].append(f"{d} revised ({ev['revision_kind']}): {ev['old']} → "
                                f"{ev['new']} | why: {ev['why']}")
    return entries


def load():
    return fold(load_events())


def get(concept):
    return load().get(concept)


# --- writers -----------------------------------------------------------------

def log_surfaced(concept, stance, counter, belief=None, concepts=None, today=None):
    _append(_event("surfaced", concept, today, stance=stance, counter=counter,
                   belief=belief, concepts=concepts))
    return get(concept)


def record_test(concept, verdict, counter_kind, counter, source_ref=None,
                belief=None, concepts=None, new_belief=None, today=None):
    if counter_kind not in ("generated", "external"):
        raise ValueError(f"counter_kind must be one of ('generated', 'external'), got {counter_kind!r}")
    apply_verdict("untested", verdict, counter_kind)  # validate before writing
    _append(_event("tested", concept, today, verdict=verdict, counter_kind=counter_kind,
                   counter=counter, source_ref=source_ref, belief=belief,
                   concepts=concepts, new_belief=new_belief))
    return get(concept)


def record_conclusion(concept, belief, memory_file=None, concepts=None,
                      source_ref=None, today=None):
    if not belief:
        raise ValueError("belief is required")
    _append(_event("concluded", concept, today, belief=belief, memory_file=memory_file,
                   concepts=concepts, source_ref=source_ref))
    return get(concept)


def record_revision(concept, old, new, why, revision_kind, memory_file=None, today=None):
    if revision_kind not in REVISION_KINDS:
        raise ValueError(f"revision_kind must be one of {REVISION_KINDS}")
    if not (old and new and why):
        raise ValueError("old, new and why are required")
    d = today or dt.date.today()
    latest = None
    for ev in load_events():
        if ev["key"] == concept and ev["type"] in ("concluded", "revised"):
            if latest is None or ev["date"] > latest:
                latest = ev["date"]
    if latest is not None and latest > d.isoformat():
        raise ValueError(f"a revision must be dated on or after the conclusion it replaces (latest: {latest})")
    _append(_event("revised", concept, today, old=old, new=new, why=why,
                   revision_kind=revision_kind, memory_file=memory_file))
    return get(concept)


# --- readers -----------------------------------------------------------------

def history(concept):
    return [ev for ev in _ordered(load_events()) if ev["key"] == concept]


def find_by_memory_file(memory_file):
    target = os.path.basename(memory_file)
    return [e for e in load().values() if e.get("memory_file") == target]


def list_by_confidence(state):
    return [e for e in load().values() if e.get("confidence") == state]


def render(path=None):
    path = path or view_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entries = load()
    out = [_VIEW_HEADER]
    for key in sorted(entries):
        e = entries[key]
        out.append(f"## {key}")
        for field in ("belief", "confidence", "first_seen", "last_tested", "memory_file"):
            out.append(f"{field}: {e.get(field, '')}")
        out.append(f"concepts: {', '.join(e['concepts'])}")
        out.append(f"counter_sources: {', '.join(e['counter_sources'])}")
        out.append("history:")
        out.extend(f"  - {h}" for h in e["history"])
        out.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")
    return path


def _split_csv(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def main():
    ap = argparse.ArgumentParser(description="FORK belief ledger")
    ap.add_argument("--get")
    ap.add_argument("--log-surfaced", action="store_true")
    ap.add_argument("--record-test", action="store_true")
    ap.add_argument("--record-conclusion", action="store_true")
    ap.add_argument("--record-revision", action="store_true")
    ap.add_argument("--list", choices=VALID_STATES)
    ap.add_argument("--history")
    ap.add_argument("--by-memory-file")
    ap.add_argument("--render", action="store_true")
    ap.add_argument("--concept")
    ap.add_argument("--stance", default="")
    ap.add_argument("--counter", default="")
    ap.add_argument("--verdict")
    ap.add_argument("--counter-kind", default="generated")
    ap.add_argument("--source-ref")
    ap.add_argument("--belief")
    ap.add_argument("--concepts")  # comma-separated
    ap.add_argument("--new-belief")
    ap.add_argument("--old")
    ap.add_argument("--new")
    ap.add_argument("--why")
    ap.add_argument("--revision-kind", choices=REVISION_KINDS)
    ap.add_argument("--memory-file")
    ap.add_argument("--effective-date")
    args = ap.parse_args()

    concepts = _split_csv(args.concepts) if args.concepts else None
    when = dt.date.fromisoformat(args.effective_date) if args.effective_date else None

    if args.get:
        entry = get(args.get)
        print(json.dumps({"entry": entry,
                          "in_cooldown": in_cooldown(entry, dt.date.today()) if entry else False}))
    elif args.log_surfaced:
        if not args.concept:
            ap.error("--log-surfaced requires --concept")
        print(json.dumps(log_surfaced(args.concept, args.stance, args.counter,
                                      belief=args.belief, concepts=concepts, today=when)))
    elif args.record_test:
        if not args.concept:
            ap.error("--record-test requires --concept")
        print(json.dumps(record_test(args.concept, args.verdict, args.counter_kind,
                                     args.counter, source_ref=args.source_ref,
                                     belief=args.belief, concepts=concepts,
                                     new_belief=args.new_belief, today=when)))
    elif args.record_conclusion:
        if not args.concept:
            ap.error("--record-conclusion requires --concept")
        print(json.dumps(record_conclusion(args.concept, args.belief,
                                           memory_file=args.memory_file, concepts=concepts,
                                           source_ref=args.source_ref, today=when)))
    elif args.record_revision:
        if not args.concept:
            ap.error("--record-revision requires --concept")
        print(json.dumps(record_revision(args.concept, args.old, args.new, args.why,
                                         args.revision_kind, memory_file=args.memory_file,
                                         today=when)))
    elif args.list:
        print(json.dumps(list_by_confidence(args.list)))
    elif args.history:
        print(json.dumps(history(args.history)))
    elif args.by_memory_file:
        print(json.dumps(find_by_memory_file(args.by_memory_file)))
    elif args.render:
        print(json.dumps({"rendered": render()}))
    else:
        ap.error("no action given")


if __name__ == "__main__":
    main()
