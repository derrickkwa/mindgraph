#!/usr/bin/env python3
"""
concept_extractor.py — Abstract concept extraction for the MindGraph concept graph.

Accepts a batch of text chunks + existing concept vocabulary from the KG.
Returns per-chunk concept assignments: matched existing concepts and new concepts to create.

LLM providers: Gemini (primary, if GEMINI_API_KEY set) or Claude API (fallback).
Both called via urllib — no SDK dependency required.

Usage:
    python3 concept_extractor.py --chunks-file /tmp/chunks.json --vocabulary-file /tmp/vocab.json
    python3 concept_extractor.py --test
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


def _get_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx


SSL_CTX = _get_ssl_context()


def _load_dotenv():
    search_dir = Path(__file__).resolve().parent
    for _ in range(8):
        env_path = search_dir / ".env"
        if env_path.is_file():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    if key.strip() and key.strip() not in os.environ:
                        os.environ[key.strip()] = value.strip()
            return
        parent = search_dir.parent
        if parent == search_dir:
            break
        search_dir = parent


_load_dotenv()
DEFAULT_BATCH_SIZE = 8


class LLMProvider:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"

    def complete(self, prompt: str, retries: int = 5) -> str:
        url = f"{self.base_url}/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=90, context=SSL_CTX) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code in (429,) or e.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                raise ValueError(f"Gemini API error {e.code}: {e.read().decode()}")
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise ValueError(f"Gemini failed after {retries} retries")


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.anthropic.com/v1"

    def complete(self, prompt: str, retries: int = 5) -> str:
        url = f"{self.base_url}/messages"
        payload = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    return body["content"][0]["text"]
            except urllib.error.HTTPError as e:
                if e.code in (429, 529) or e.code >= 500:
                    time.sleep(2 ** attempt)
                    continue
                raise ValueError(f"Claude API error {e.code}: {e.read().decode()}")
            except Exception:
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise ValueError(f"Claude API failed after {retries} retries")


def get_provider(config: dict) -> LLMProvider:
    mode = config.get("llm_provider", "auto")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "")

    if mode == "gemini":
        if not gemini_key:
            raise ValueError("llm_provider=gemini but GEMINI_API_KEY not set")
        return GeminiProvider(gemini_key)
    if mode == "claude":
        if not claude_key:
            raise ValueError("llm_provider=claude but ANTHROPIC_API_KEY not set")
        return ClaudeProvider(claude_key)
    if gemini_key:
        return GeminiProvider(gemini_key)
    if claude_key:
        return ClaudeProvider(claude_key)
    raise ValueError(
        "No LLM provider configured. Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env"
    )


EXTRACTION_PROMPT = """You are building a personal knowledge graph for a second brain system.

Your task: identify ABSTRACT CONCEPTS expressed in each text chunk.

WHAT IS AN ABSTRACT CONCEPT (extract these):
- Recurring themes, patterns, mental models, principles, cognitive patterns, behaviors
- Things that could appear across multiple domains
- Examples: "time-pressure", "activation-friction", "urgency-framing", "pattern-recognition",
  "decision-under-constraint", "systems-thinking", "feedback-loops", "expectation-misalignment"

WHAT IS NOT A CONCEPT (skip these):
- Specific named entities: people names, company names, tool names
- One-off facts that don't generalize
- Overly broad concepts ("communication", "work")

DEDUPLICATION RULE: Before creating a NEW concept, check if an existing vocabulary entry covers it.
Prefer MATCHING existing concepts. Only create new concepts when genuinely not covered.

EXISTING CONCEPT VOCABULARY:
{vocabulary_json}

CHUNKS TO PROCESS:
{chunks_json}

For each chunk return:
- "matched": list of objects for existing concepts this chunk expresses (0-4 per chunk)
- "new": list of genuinely new concepts (0-2 per chunk)

Each concept object must include:
- "concept": lowercase, hyphenated name (e.g. "time-pressure")
- "confidence": float 0.0-1.0

Return ONLY valid JSON — no markdown, no explanation:
[
  {{"chunk_id": "ID", "matched": [{{"concept": "x", "confidence": 0.9}}], "new": [{{"concept": "y", "confidence": 0.75}}]}},
  ...
]"""


def extract_concepts(
    chunks: list[dict],
    vocabulary: list[str],
    provider: LLMProvider | None = None,
    config: dict | None = None,
) -> list[dict]:
    if not chunks:
        return []
    if provider is None:
        provider = get_provider(config or {})

    vocab_display = sorted(vocabulary) if vocabulary else ["(none yet)"]
    chunks_display = [{"chunk_id": c["id"], "text": c["text"][:400]} for c in chunks]
    prompt = EXTRACTION_PROMPT.format(
        vocabulary_json=json.dumps(vocab_display, indent=2),
        chunks_json=json.dumps(chunks_display, indent=2),
    )

    raw = provider.complete(prompt)

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        llm_results = json.loads(clean.strip())
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse LLM response: {e}", file=sys.stderr)
        return [
            {
                "chunk_id": c["id"],
                "source_file": c.get("source_file", ""),
                "wing": c.get("wing", ""),
                "room": c.get("room", ""),
                "matched_concepts": [],
                "new_concepts": [],
                "concept_confidences": {},
                "error": "parse_failed",
            }
            for c in chunks
        ]

    llm_by_id = {r["chunk_id"]: r for r in llm_results}
    results = []
    for chunk in chunks:
        llm = llm_by_id.get(chunk["id"], {})

        def _parse(items):
            out = []
            for item in items:
                if isinstance(item, dict):
                    out.append({"concept": item.get("concept", ""), "confidence": float(item.get("confidence", 0.9))})
                elif isinstance(item, str):
                    out.append({"concept": item, "confidence": 0.9})
            return [p for p in out if p["concept"]]

        matched = _parse(llm.get("matched", []))
        new = _parse(llm.get("new", []))
        results.append({
            "chunk_id": chunk["id"],
            "source_file": chunk.get("source_file", ""),
            "wing": chunk.get("wing", ""),
            "room": chunk.get("room", ""),
            "matched_concepts": [c["concept"] for c in matched],
            "new_concepts": [c["concept"] for c in new],
            "concept_confidences": {c["concept"]: c["confidence"] for c in matched + new},
        })
    return results


def extract_concepts_batched(
    chunks: list[dict],
    vocabulary: list[str],
    provider: LLMProvider | None = None,
    config: dict | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> tuple[list[dict], list[str]]:
    if provider is None:
        provider = get_provider(config or {})

    all_results = []
    current_vocab = list(vocabulary)
    total = len(chunks)

    for i in range(0, total, batch_size):
        batch = chunks[i: i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size
        print(f"[INFO] Batch {batch_num}/{total_batches} ({len(batch)} chunks, vocab: {len(current_vocab)})", file=sys.stderr)

        try:
            results = extract_concepts(batch, current_vocab, provider=provider)
        except Exception as e:
            print(f"[WARN] Batch {batch_num} failed ({e}), skipping", file=sys.stderr)
            results = [
                {"chunk_id": c["id"], "source_file": c.get("source_file", ""),
                 "wing": c.get("wing", ""), "room": c.get("room", ""),
                 "matched_concepts": [], "new_concepts": [], "concept_confidences": {}, "error": "batch_failed"}
                for c in batch
            ]

        all_results.extend(results)
        for r in results:
            for c in r.get("new_concepts", []):
                if c not in current_vocab:
                    current_vocab.append(c)

        if i + batch_size < total:
            time.sleep(0.5)

    return all_results, current_vocab


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks-file")
    parser.add_argument("--vocabulary-file")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        from unittest.mock import MagicMock
        test_chunks = [{"id": "test-001", "text": "Users churn before hitting the activation moment.", "source_file": "test", "wing": "work", "room": "projects"}]
        test_vocab = ["activation-rate"]
        mock = MagicMock()
        mock.complete.return_value = json.dumps([{"chunk_id": "test-001", "matched": [{"concept": "activation-rate", "confidence": 0.9}], "new": []}])
        results, vocab = extract_concepts_batched(test_chunks, test_vocab, provider=mock)
        print(json.dumps({"results": results, "vocab": vocab}, indent=2))
        return

    chunks = []
    if args.chunks_file:
        with open(args.chunks_file) as f:
            chunks = json.load(f)
    else:
        raw = sys.stdin.read().strip()
        chunks = json.loads(raw)

    vocabulary = []
    if args.vocabulary_file:
        with open(args.vocabulary_file) as f:
            vocabulary = json.load(f)

    results, final_vocab = extract_concepts_batched(chunks, vocabulary, batch_size=args.batch_size)
    print(json.dumps({"results": results, "stats": {"chunks": len(results), "vocab_size": len(final_vocab)}}, indent=2))


if __name__ == "__main__":
    main()
