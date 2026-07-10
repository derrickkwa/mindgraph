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
        parts = chunk.split(FIELD)
        # Records are folder, title, date, body — but a leading record-type
        # marker (e.g. "NOTE") may precede them, so keep only the last 4
        # fields when more than 4 are present; pad on the right otherwise.
        if len(parts) > 4:
            parts = parts[-4:]
        else:
            parts = parts + [""] * (4 - len(parts))
        folder, title, date, body = parts
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
