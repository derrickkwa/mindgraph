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
        if prop.get("type") == "title" or isinstance(prop.get("title"), list):
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
