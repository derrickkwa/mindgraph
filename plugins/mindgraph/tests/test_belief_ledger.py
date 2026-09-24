import datetime as dt
import json
import subprocess
import sys
import os

import pytest
from scripts import belief_ledger as bl

D = dt.date


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(bl, "LEDGER_PATH", str(path))
    monkeypatch.setattr(bl, "VIEW_PATH", str(tmp_path / "ledger.md"))
    return path


# --- unchanged pure logic ---------------------------------------------------

def test_survived_generated_untested_to_leaning():
    assert bl.apply_verdict("untested", "survived", "generated") == "leaning"


def test_survived_generated_leaning_stays_leaning():
    assert bl.apply_verdict("leaning", "survived", "generated") == "leaning"


def test_survived_external_becomes_solid():
    assert bl.apply_verdict("leaning", "survived", "external") == "solid"


def test_weakened_becomes_shaky():
    assert bl.apply_verdict("solid", "weakened", "generated") == "shaky"


def test_flipped_becomes_flipped():
    assert bl.apply_verdict("leaning", "flipped", "external") == "flipped"


def test_cooldown_boundaries():
    today = D(2026, 7, 16)
    assert bl.in_cooldown({"last_tested": "2026-07-01"}, today, days=30) is True
    assert bl.in_cooldown({"last_tested": "2026-05-01"}, today, days=30) is False
    assert bl.in_cooldown({"last_tested": ""}, today, days=30) is False


# --- existing behaviours through the event log ------------------------------

def test_record_test_stores_counter_text(ledger):
    bl.record_test("k", "survived", "generated", "async has hidden coordination cost",
                   belief="async wins", concepts=["k"], today=D(2026, 7, 16))
    e = bl.get("k")
    assert e["confidence"] == "leaning"
    assert e["last_tested"] == "2026-07-16"
    assert any("async has hidden coordination cost" in h for h in e["history"])


def test_log_surfaced_creates_untested_entry(ledger):
    e = bl.log_surfaced("k", "X is best", "Y", belief="X is best", today=D(2026, 7, 14))
    assert e["confidence"] == "untested"
    assert e["first_seen"] == "2026-07-14"
    assert e["history"][0].startswith("2026-07-14 surfaced on pulse")


def test_flipped_test_replaces_belief(ledger):
    bl.record_conclusion("k", "old view", today=D(2026, 7, 1))
    bl.record_test("k", "flipped", "external", "study", source_ref="doi:1",
                   new_belief="new view", today=D(2026, 7, 2))
    e = bl.get("k")
    assert e["belief"] == "new view"
    assert e["confidence"] == "flipped"
    assert e["counter_sources"] == ["doi:1"]


def test_list_by_confidence(ledger):
    bl.record_test("a", "weakened", "generated", "", today=D(2026, 7, 1))
    bl.record_test("b", "survived", "generated", "", today=D(2026, 7, 1))
    assert [e["key"] for e in bl.list_by_confidence("shaky")] == ["a"]


# --- revisions ---------------------------------------------------------------

def test_revision_appends_and_updates_belief(ledger):
    bl.record_conclusion("pricing-model", "flat pricing wins", memory_file="m.md", today=D(2026, 8, 20))
    bl.record_revision("pricing-model", "flat pricing wins", "tiered pricing wins", "trial data",
                       "reversal", memory_file="m.md", today=D(2026, 9, 16))
    e = bl.get("pricing-model")
    assert e["belief"] == "tiered pricing wins"
    assert e["memory_file"] == "m.md"
    assert e["history"][-1] == ("2026-09-16 revised (reversal): flat pricing wins → "
                                "tiered pricing wins | why: trial data")


def test_reversal_sets_flipped(ledger):
    bl.record_conclusion("k", "a", today=D(2026, 1, 1))
    bl.record_revision("k", "a", "b", "why", "reversal", today=D(2026, 1, 2))
    assert bl.get("k")["confidence"] == "flipped"


def test_refinement_keeps_confidence(ledger):
    bl.record_test("k", "survived", "external", "", source_ref="s", today=D(2026, 1, 1))
    bl.record_revision("k", "a", "a, sharper", "why", "refinement", today=D(2026, 1, 2))
    assert bl.get("k")["confidence"] == "solid"


def test_revision_does_not_touch_last_tested(ledger):
    bl.record_test("k", "survived", "generated", "", today=D(2026, 1, 1))
    bl.record_revision("k", "a", "b", "why", "refinement", today=D(2026, 3, 1))
    assert bl.get("k")["last_tested"] == "2026-01-01"


def test_invalid_revision_kind_rejected_and_nothing_written(ledger):
    with pytest.raises(ValueError):
        bl.record_revision("k", "a", "b", "why", "sideways", today=D(2026, 1, 1))
    assert not ledger.exists() or ledger.read_text() == ""


def test_history_ordered_by_effective_date_not_write_order(ledger):
    bl.record_revision("k", "b", "c", "later", "refinement", today=D(2026, 9, 1))
    bl.record_conclusion("k", "b", today=D(2026, 5, 1))  # backdated, written second
    events = bl.history("k")
    assert [ev["date"] for ev in events] == ["2026-05-01", "2026-09-01"]
    assert bl.get("k")["belief"] == "c"
    assert bl.get("k")["first_seen"] == "2026-05-01"


def test_find_by_memory_file(ledger):
    bl.record_conclusion("a", "x", memory_file="one.md", today=D(2026, 1, 1))
    bl.record_conclusion("b", "y", memory_file="two.md", today=D(2026, 1, 1))
    assert [e["key"] for e in bl.find_by_memory_file("one.md")] == ["a"]


def test_find_by_memory_file_normalises_path_to_basename(ledger):
    bl.record_conclusion("a", "x", memory_file="one.md", today=D(2026, 1, 1))
    assert [e["key"] for e in bl.find_by_memory_file("memory/one.md")] == ["a"]
    assert [e["key"] for e in bl.find_by_memory_file("/abs/path/memory/one.md")] == ["a"]


# --- F6: future-date rejection -----------------------------------------------

def test_future_effective_date_rejected_and_nothing_written(ledger):
    tomorrow = dt.date.today() + dt.timedelta(days=1)
    with pytest.raises(ValueError):
        bl.record_conclusion("k", "v", today=tomorrow)
    assert not ledger.exists() or ledger.read_text() == ""


def test_today_effective_date_is_allowed(ledger):
    bl.record_conclusion("k", "v", today=dt.date.today())
    assert bl.get("k")["belief"] == "v"


# --- storage guarantees ------------------------------------------------------

def test_file_is_append_only(ledger):
    bl.record_conclusion("k", "a", today=D(2026, 1, 1))
    first = ledger.read_text()
    bl.record_revision("k", "a", "b", "why", "reversal", today=D(2026, 1, 2))
    second = ledger.read_text()
    assert second.startswith(first)
    assert len(second.splitlines()) == 2
    assert all(json.loads(line)["key"] == "k" for line in second.splitlines())


def test_malformed_line_raises(ledger):
    ledger.write_text('{"type": "concluded", "key": "k", "date": "2026-01-01", "belief": "a"}\n'
                      'not json\n')
    with pytest.raises(ValueError, match=":2:"):
        bl.load()


def test_render_writes_generated_view(ledger, tmp_path):
    bl.record_conclusion("k", "a", today=D(2026, 1, 1))
    path = bl.render()
    text = open(path).read()
    assert "GENERATED" in text
    assert "## k" in text
    assert "belief: a" in text


def test_cli_get_output_shape(ledger):
    bl.record_conclusion("k", "a", today=D(2026, 1, 1))
    env = dict(os.environ)
    plugin_root = os.path.abspath(
        os.path.join(os.path.dirname(bl.__file__), ".."))
    code = (f"from scripts import belief_ledger as bl; bl.LEDGER_PATH={str(ledger)!r}; "
            "import sys; sys.argv=['x','--get','k']; bl.main()")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         cwd=plugin_root, env=env, check=True).stdout
    data = json.loads(out)
    assert set(data) == {"entry", "in_cooldown"}
    assert data["entry"]["belief"] == "a"


# --- belief seed logic -------------------------------------------------------

def test_surfaced_belief_does_not_overwrite_concluded_belief(ledger):
    bl.record_conclusion("k", "canonical", today=D(2026, 1, 1))
    bl.log_surfaced("k", "s", "c", belief="paraphrase", today=D(2026, 1, 2))
    assert bl.get("k")["belief"] == "canonical"


def test_nonflip_test_belief_does_not_overwrite(ledger):
    bl.record_conclusion("k", "canonical", today=D(2026, 1, 1))
    bl.record_test("k", "survived", "generated", "", belief="paraphrase", today=D(2026, 1, 2))
    assert bl.get("k")["belief"] == "canonical"


def test_surfaced_belief_seeds_empty_entry(ledger):
    bl.log_surfaced("k", "s", "c", belief="first", today=D(2026, 1, 1))
    assert bl.get("k")["belief"] == "first"


# --- data-home defaults -------------------------------------------------------

def test_default_paths_follow_mindgraph_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(bl, "LEDGER_PATH", None)
    monkeypatch.setattr(bl, "VIEW_PATH", None)
    assert bl.ledger_path() == str(tmp_path / "home" / "beliefs" / "ledger.jsonl")
    assert bl.view_path() == str(tmp_path / "home" / "beliefs" / "ledger.md")


def test_fresh_home_get_and_render(tmp_path, monkeypatch):
    monkeypatch.setenv("MINDGRAPH_HOME", str(tmp_path / "fresh"))
    monkeypatch.setattr(bl, "LEDGER_PATH", None)
    monkeypatch.setattr(bl, "VIEW_PATH", None)
    assert bl.get("k") is None
    path = bl.render()
    assert path.endswith("beliefs/ledger.md")
    assert "GENERATED" in open(path).read()


# --- I2: one bad CLI call must not be able to break the ledger --------------

def test_log_surfaced_none_concept_raises_and_writes_nothing(ledger):
    with pytest.raises(ValueError):
        bl.log_surfaced(None, "s", "c", today=D(2026, 1, 1))
    assert not ledger.exists() or ledger.read_text() == ""


def test_log_surfaced_non_string_concept_raises_and_writes_nothing(ledger):
    with pytest.raises(ValueError):
        bl.log_surfaced(123, "s", "c", today=D(2026, 1, 1))
    assert not ledger.exists() or ledger.read_text() == ""


def test_record_test_bogus_counter_kind_raises_and_writes_nothing(ledger):
    with pytest.raises(ValueError):
        bl.record_test("k", "survived", "bogus", "counter", today=D(2026, 1, 1))
    assert not ledger.exists() or ledger.read_text() == ""


def test_cli_log_surfaced_without_concept_exits_nonzero_and_writes_nothing(ledger):
    env = dict(os.environ)
    plugin_root = os.path.abspath(os.path.join(os.path.dirname(bl.__file__), ".."))
    code = (f"from scripts import belief_ledger as bl; bl.LEDGER_PATH={str(ledger)!r}; "
            "import sys; sys.argv=['x','--log-surfaced','--stance','s','--counter','c']; bl.main()")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            cwd=plugin_root, env=env)
    assert result.returncode != 0
    assert not ledger.exists() or ledger.read_text() == ""


# --- I3: backdated revisions must not silently produce a stale belief -------

def test_backdated_revision_before_conclusion_raises(ledger):
    bl.record_conclusion("k", "old belief", today=D(2026, 8, 1))
    with pytest.raises(ValueError, match="on or after"):
        bl.record_revision("k", "old belief", "new belief", "why", "refinement",
                           today=D(2026, 7, 1))


def test_backdated_revision_before_prior_revision_raises(ledger):
    bl.record_conclusion("k", "a", today=D(2026, 1, 1))
    bl.record_revision("k", "a", "b", "why", "refinement", today=D(2026, 6, 1))
    with pytest.raises(ValueError, match="on or after"):
        bl.record_revision("k", "b", "c", "why2", "refinement", today=D(2026, 3, 1))
