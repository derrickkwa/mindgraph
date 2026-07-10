from scripts.wing_deriver import assign, propose_tree

WINGS = [
    {"name": "growth", "rooms": [
        {"name": "acquisition", "concepts": ["funnel-design", "activation-friction"]},
        {"name": "retention", "concepts": ["churn", "retention"]},
    ]},
    {"name": "personal", "rooms": [
        {"name": "general", "concepts": ["habit-formation"]},
    ]},
]


def test_assigns_to_max_overlap_wing_and_room():
    notes = {"notion:a": ["funnel-design", "activation-friction"], "notion:b": ["churn"]}
    out = assign(notes, WINGS)
    assert out["notion:a"] == {"wing": "growth", "room": "acquisition"}
    assert out["notion:b"] == {"wing": "growth", "room": "retention"}


def test_no_room_overlap_falls_back_to_general():
    # matches wing 'growth' via a wing-level concept but no specific room? construct a wing with general
    wings = [{"name": "growth", "rooms": [
        {"name": "general", "concepts": []},
        {"name": "acquisition", "concepts": ["funnel-design"]},
    ]}]
    notes = {"notion:c": ["some-unknown-but-still-growth"]}
    # no overlap anywhere → default inbox/general
    assert assign(notes, wings)["notion:c"] == {"wing": "inbox", "room": "general"}


def test_tie_breaks_to_first_wing():
    wings = [
        {"name": "a", "rooms": [{"name": "general", "concepts": ["x"]}]},
        {"name": "b", "rooms": [{"name": "general", "concepts": ["x"]}]},
    ]
    assert assign({"n:1": ["x"]}, wings)["n:1"]["wing"] == "a"


def test_propose_tree_parses_nested_json():
    class Stub:
        def complete(self, prompt):
            return ('[{"name":"growth","rooms":[{"name":"acquisition",'
                    '"concepts":["funnel-design"]}]}]')
    tree = propose_tree({"n:1": ["funnel-design"]}, Stub())
    assert tree[0]["name"] == "growth"
    assert tree[0]["rooms"][0]["concepts"] == ["funnel-design"]
