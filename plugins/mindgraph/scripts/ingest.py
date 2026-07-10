#!/usr/bin/env python3
"""
ingest.py — MindGraph ingest entry point.

Reads config.yml, runs the markdown adapter, pipes chunks into the batch ingest pipeline.

Usage:
    python scripts/ingest.py                        # uses config.yml notes_folder
    python scripts/ingest.py --source ./my-notes    # overrides config.yml notes_folder
    python scripts/ingest.py --dry-run              # no writes
    python scripts/ingest.py --status               # show checkpoint + KG stats
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.config import load_config
from adapters.markdown import MarkdownAdapter


def main():
    parser = argparse.ArgumentParser(description="Ingest notes into MindGraph")
    parser.add_argument("--source", help="Override notes_folder from config.yml")
    parser.add_argument("--config", default="config.yml")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.source:
        config["notes_folder"] = str(Path(args.source).expanduser())

    if args.status:
        subprocess.run([
            sys.executable,
            str(ROOT / "skills/brain-ingest/scripts/batch_ingest.py"),
            "--status", "--config", args.config,
        ], check=True)
        return

    print(f"[INFO] Reading notes from: {config['notes_folder']}")
    adapter = MarkdownAdapter()
    chunks = adapter.fetch_and_validate(config)
    print(f"[INFO] {len(chunks)} chunks ready for ingest")

    if not chunks:
        print("[WARN] No chunks found. Check notes_folder and wing mappings in config.yml.")
        return

    cmd = [
        sys.executable,
        str(ROOT / "skills/brain-ingest/scripts/batch_ingest.py"),
        "--config", args.config,
    ]
    if args.dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, input=json.dumps(chunks).encode(), check=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
