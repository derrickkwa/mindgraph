import importlib
import sys
from scripts.paths import adapters_dir

_BUNDLED = {
    "markdown": ("adapters.markdown", "MarkdownAdapter"),
    "obsidian": ("adapters.obsidian", "ObsidianAdapter"),
    "notion": ("adapters.notion", "NotionAdapter"),
    "apple_notes": ("adapters.apple_notes", "AppleNotesAdapter"),
}


def get_adapter(source_type: str):
    if source_type in _BUNDLED:
        mod_name, cls_name = _BUNDLED[source_type]
        return getattr(importlib.import_module(mod_name), cls_name)()
    # user-generated adapter in the data home
    user_dir = adapters_dir()
    candidate = user_dir / f"{source_type}.py"
    if candidate.exists():
        sys.path.insert(0, str(user_dir))
        mod = importlib.import_module(source_type)
        cls = next(v for k, v in vars(mod).items() if k.endswith("Adapter") and isinstance(v, type))
        return cls()
    raise ValueError(f"unknown source type: {source_type}")
