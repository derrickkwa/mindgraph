import importlib
import scripts.paths as paths


def _mod(monkeypatch, tmp_path):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path))
    importlib.reload(paths)
    import scripts.write_config as wc
    return importlib.reload(wc)


def test_set_sources_then_wings_roundtrip(tmp_path, monkeypatch):
    wc = _mod(monkeypatch, tmp_path)
    wc.set_sources([{"type": "notion"}])
    wc.set_wings([{"name": "growth", "rooms": [{"name": "acq", "concepts": ["funnel-design"]}]}])
    cfg = wc.read()
    assert cfg["sources"] == [{"type": "notion"}]
    assert cfg["wings"][0]["rooms"][0]["concepts"] == ["funnel-design"]
    assert cfg["defaults"] == {"wing": "inbox", "room": "general"}
