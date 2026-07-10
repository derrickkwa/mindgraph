#!/usr/bin/env python3
"""
setup.py — MindGraph first-run setup.

Installs mempalace, initialises the palace, and walks through config.yml creation.
Run once after cloning the repo.

Usage:
    python scripts/setup.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=capture, text=True)


def check_mempalace() -> bool:
    result = run(["python3", "-c", "import mempalace"], check=False, capture=True)
    return result.returncode == 0


def install_mempalace():
    print("\n[1/5] Installing mempalace...")
    if shutil.which("uv"):
        run(["uv", "tool", "install", "mempalace"])
    else:
        run([sys.executable, "-m", "pip", "install", "mempalace"])
    print("     ✓ mempalace installed")


def init_mempalace():
    print("\n[2/5] Initializing palace...")
    palace_path = Path.home() / ".mempalace"
    if palace_path.exists():
        print("     ✓ palace already initialized")
        return
    try:
        run(["mempalace", "init"])
        print("     ✓ palace initialized at ~/.mempalace")
    except Exception:
        print("     ✓ palace path created")
        palace_path.mkdir(parents=True, exist_ok=True)


def validate_env():
    print("\n[3/5] Checking API keys...")
    env_file = ROOT / ".env"
    if not env_file.exists():
        example = ROOT / ".env.example"
        if example.exists():
            shutil.copy(example, env_file)
            print("     Created .env from .env.example")

    gemini = os.environ.get("GEMINI_API_KEY", "")
    claude = os.environ.get("ANTHROPIC_API_KEY", "")
    if gemini:
        print("     ✓ GEMINI_API_KEY found (will use Gemini for concept extraction)")
    elif claude:
        print("     ✓ ANTHROPIC_API_KEY found (will use Claude API for concept extraction)")
    else:
        print("     ⚠ No LLM API key found.")
        print("       Set GEMINI_API_KEY or ANTHROPIC_API_KEY in .env before running ingest.")


def create_config():
    print("\n[4/5] Configuring wings and rooms...")
    config_path = ROOT / "config.yml"
    if config_path.exists():
        print("     config.yml already exists — skipping (delete it to reconfigure)")
        return

    print("\n  What is the path to your notes folder?")
    print("  (A folder of .md files — e.g. your Obsidian vault)")
    notes_folder = input("  Notes folder [~/Documents/my-notes]: ").strip()
    if not notes_folder:
        notes_folder = "~/Documents/my-notes"

    print("\n  Define your wings (top-level categories mapped to folder prefixes).")
    print("  Press Enter with no input when done.\n")

    wings = []
    while True:
        wing_name = input(f"  Wing {len(wings)+1} name (e.g. 'work') or Enter to finish: ").strip()
        if not wing_name:
            break
        folder = input(f"    Folder prefix for '{wing_name}' [{wing_name}/]: ").strip()
        if not folder:
            folder = f"{wing_name}/"
        wings.append({"name": wing_name, "folder": folder})

    lines = [
        f"notes_folder: {notes_folder}",
        "",
        "llm_provider: auto  # auto | gemini | claude",
        "",
        "wings:",
    ]
    for w in wings:
        lines.append(f"  - name: {w['name']}")
        lines.append(f"    rooms:")
        lines.append(f"      notes: [{w['folder']}]")
    if not wings:
        lines.append("  []")
    lines += ["", "defaults:", "  wing: misc", "  room: general"]

    config_path.write_text("\n".join(lines) + "\n")
    print(f"\n     ✓ config.yml created. Edit it to refine wing/room mappings.")


def print_next_steps():
    print("\n[5/5] Setup complete!\n")
    print("  Next steps:")
    print("  1. Review config.yml and adjust wing/room mappings")
    print("  2. Ensure .env has GEMINI_API_KEY or ANTHROPIC_API_KEY")
    print("  3. Run your first ingest:")
    print("       python scripts/ingest.py")
    print("")
    print("  Then open Claude Code in this folder and ask:")
    print("    'What do my notes say about [any topic]?'")
    print("")


def main():
    print("=" * 50)
    print("  MindGraph Setup")
    print("=" * 50)

    if not check_mempalace():
        install_mempalace()
    else:
        print("\n[1/5] mempalace already installed ✓")

    init_mempalace()
    validate_env()
    create_config()
    print_next_steps()


if __name__ == "__main__":
    main()
