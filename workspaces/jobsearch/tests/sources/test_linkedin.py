import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/linkedin_response.html")


def _parse_with_fixture(html_text):
    """Call fetch() with a mocked HTTP layer returning the fixture."""
    from unittest.mock import patch, MagicMock
    import sources.linkedin as ln

    mock_resp = MagicMock()
    mock_resp.text = html_text
    mock_resp.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.linkedin.get_session", return_value=mock_session):
        return ln.fetch(ln.QUERIES[0])


def test_new_layout_returns_jobs():
    html = open(FIXTURE, encoding="utf-8").read()
    jobs = _parse_with_fixture(html)
    assert len(jobs) >= 1, f"Expected >=1 job, got {len(jobs)}"


def test_cards_in_fixture():
    """Fixture captured 2026-05-28 contains 2 li > div[data-entity-urn] cards."""
    html = open(FIXTURE, encoding="utf-8").read()
    jobs = _parse_with_fixture(html)
    assert len(jobs) == 2, f"Expected 2, got {len(jobs)}"


def test_required_fields():
    html = open(FIXTURE, encoding="utf-8").read()
    jobs = _parse_with_fixture(html)
    for job in jobs:
        assert job.get("id"), f"Missing id: {job}"
        assert job.get("name"), f"Missing name: {job}"
        assert job.get("source") == "linkedin", f"Wrong source: {job}"


def test_empty_response():
    jobs = _parse_with_fixture("<html><body></body></html>")
    assert jobs == []


def test_queries_cover_three_geos():
    from sources.linkedin import QUERIES
    locs = [q.get("location", "") for q in QUERIES]
    assert any("Russia" in l for l in locs)
    assert any("United States" in l or "European" in l for l in locs)


def test_remote_flag_set_for_f_wt_queries():
    from sources.linkedin import QUERIES
    remote_queries = [q for q in QUERIES if q.get("f_WT") == "2"]
    assert len(remote_queries) >= 1
