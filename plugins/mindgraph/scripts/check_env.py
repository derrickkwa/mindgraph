#!/usr/bin/env python3
import importlib.util
import json
import sys
from scripts.paths import env_path


def _env_keys() -> dict:
    keys = {"gemini": False, "claude": False}
    p = env_path()
    if p.is_file():
        text = p.read_text()
        keys["gemini"] = "GEMINI_API_KEY=" in text and not _blank(text, "GEMINI_API_KEY")
        keys["claude"] = "ANTHROPIC_API_KEY=" in text and not _blank(text, "ANTHROPIC_API_KEY")
    return keys


def _blank(text: str, key: str) -> bool:
    for line in text.splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip() == ""
    return True


def check() -> dict:
    python_ok = sys.version_info >= (3, 11)
    mempalace = importlib.util.find_spec("mempalace") is not None
    keys = _env_keys()
    return {
        "python_ok": python_ok,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}",
        "mempalace": mempalace,
        "keys": keys,
        "ready": python_ok and mempalace and (keys["gemini"] or keys["claude"]),
    }


if __name__ == "__main__":
    print(json.dumps(check(), indent=2))
