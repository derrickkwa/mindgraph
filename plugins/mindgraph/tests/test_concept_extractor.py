import json
import pytest
from unittest.mock import MagicMock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "skills/brain-ingest/scripts"))
from concept_extractor import (
    get_provider,
    GeminiProvider,
    ClaudeProvider,
    extract_concepts,
    extract_concepts_batched,
)

SAMPLE_CHUNKS = [
    {
        "id": "work_projects_abc123",
        "text": "Activation rate dropped because users don't see value before hitting the paywall.",
        "source_file": "work/projects/q2.md",
        "wing": "work",
        "room": "projects",
    }
]

SAMPLE_VOCAB = ["activation-rate", "time-to-value"]

MOCK_LLM_RESPONSE = json.dumps([
    {
        "chunk_id": "work_projects_abc123",
        "matched": [{"concept": "activation-rate", "confidence": 0.92}],
        "new": [{"concept": "paywall-friction", "confidence": 0.78}],
    }
])


def test_get_provider_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    provider = get_provider({"llm_provider": "auto"})
    assert isinstance(provider, GeminiProvider)


def test_get_provider_claude_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = get_provider({"llm_provider": "auto"})
    assert isinstance(provider, ClaudeProvider)


def test_get_provider_no_keys_raises(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="No LLM provider"):
        get_provider({"llm_provider": "auto"})


def test_extract_concepts_returns_results():
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MOCK_LLM_RESPONSE

    results = extract_concepts(SAMPLE_CHUNKS, SAMPLE_VOCAB, provider=mock_provider)
    assert len(results) == 1
    assert "activation-rate" in results[0]["matched_concepts"]
    assert "paywall-friction" in results[0]["new_concepts"]


def test_extract_concepts_handles_parse_error():
    mock_provider = MagicMock()
    mock_provider.complete.return_value = "not valid json {"

    results = extract_concepts(SAMPLE_CHUNKS, SAMPLE_VOCAB, provider=mock_provider)
    assert len(results) == 1
    assert results[0]["matched_concepts"] == []
    assert results[0].get("error") == "parse_failed"


def test_extract_concepts_batched_updates_vocab():
    mock_provider = MagicMock()
    mock_provider.complete.return_value = MOCK_LLM_RESPONSE

    results, final_vocab = extract_concepts_batched(
        SAMPLE_CHUNKS, SAMPLE_VOCAB, provider=mock_provider, batch_size=10
    )
    assert "paywall-friction" in final_vocab
