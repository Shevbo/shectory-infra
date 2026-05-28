import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/hn_response.json")


def _parse_with_fixture():
    """Inject fixture as comment search response; mock thread fetch."""
    from unittest.mock import patch, MagicMock
    import sources.hn_hiring as hn

    hn._thread_id_cache.clear()

    fixture_data = json.loads(open(FIXTURE).read())

    thread_resp = MagicMock()
    thread_resp.json.return_value = {"hits": [{"objectID": "42000000"}]}

    comments_resp = MagicMock()
    comments_resp.json.return_value = fixture_data

    mock_session = MagicMock()
    mock_session.get.side_effect = [thread_resp, comments_resp]

    with patch("sources.hn_hiring.get_session", return_value=mock_session):
        return hn.fetch({"query": "CTO"})


def test_returns_list():
    assert isinstance(_parse_with_fixture(), list)


def test_required_fields():
    for job in _parse_with_fixture():
        assert job.get("id")
        assert job.get("name")
        assert job.get("source") == "hn_hiring"
        assert "ycombinator.com" in job.get("alternate_url", "")


def test_clevel_filter_excludes_non_clevel():
    """fetch() should drop hits that have no C-level keyword in the full text."""
    from unittest.mock import patch, MagicMock
    import sources.hn_hiring as hn

    hn._thread_id_cache.clear()
    thread_resp = MagicMock()
    thread_resp.json.return_value = {"hits": [{"objectID": "42000000"}]}
    comments_resp = MagicMock()
    comments_resp.json.return_value = {
        "hits": [
            {"objectID": "1", "comment_text": "We are hiring backend developers, 2 years exp required."},
            {"objectID": "2", "comment_text": "Looking for a Chief Technology Officer to lead our platform."},
        ]
    }
    mock_session = MagicMock()
    mock_session.get.side_effect = [thread_resp, comments_resp]

    with patch("sources.hn_hiring.get_session", return_value=mock_session):
        jobs = hn.fetch({"query": "CTO"})

    assert len(jobs) == 1
    assert jobs[0]["id"] == "2"


def test_no_thread_graceful():
    from unittest.mock import patch, MagicMock
    import sources.hn_hiring as hn
    hn._thread_id_cache.clear()

    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("network error")

    with patch("sources.hn_hiring.get_session", return_value=mock_session):
        assert hn.fetch({"query": "CTO"}) == []


def test_empty_hits():
    from unittest.mock import patch, MagicMock
    import sources.hn_hiring as hn
    hn._thread_id_cache.clear()

    thread_resp = MagicMock()
    thread_resp.json.return_value = {"hits": [{"objectID": "42000000"}]}
    comments_resp = MagicMock()
    comments_resp.json.return_value = {"hits": []}

    mock_session = MagicMock()
    mock_session.get.side_effect = [thread_resp, comments_resp]

    with patch("sources.hn_hiring.get_session", return_value=mock_session):
        assert hn.fetch({"query": "CTO"}) == []
