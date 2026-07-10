from adapters.apple_notes import _parse_export

RAW = (
    "NOTE\x1fWork\x1fMeeting notes\x1f2026-03-01\x1fDiscussed the funnel and churn.\x1e"
    "NOTE\x1fPersonal\x1fJournal\x1f2026-03-02\x1fFelt good about habits today.\x1e"
)


def test_parse_export_builds_records():
    recs = _parse_export(RAW)
    assert len(recs) == 2
    assert recs[0]["source_file"].startswith("apple_notes:")
    assert recs[0]["title"] == "Meeting notes"
    assert recs[0]["filed_at"] == "2026-03-01"
    assert "funnel" in recs[0]["text"]
    assert recs[0]["tags"] == ["Work"]  # folder recorded as a tag
