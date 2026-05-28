import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/jobicy_response.json")


def _parse_with_fixture():
    from unittest.mock import patch, MagicMock
    import sources.jobicy as jc

    data = json.loads(open(FIXTURE).read())

    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    mock_resp.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.jobicy.get_session", return_value=mock_session):
        return jc.fetch(jc.QUERIES[0])


def test_returns_list():
    assert isinstance(_parse_with_fixture(), list)


def test_clevel_filter():
    jobs = _parse_with_fixture()
    import re
    pattern = re.compile(r"(?i)(CTO|CIO|Chief|Head of|VP|Director)")
    for job in jobs:
        assert pattern.search(job["name"]), f"Non-C-level: {job['name']}"


def test_required_fields():
    jobs = _parse_with_fixture()
    for job in jobs:
        assert job.get("id")
        assert job.get("name")
        assert job.get("source") == "jobicy"
        assert job.get("remote_flag") is True


def test_empty_response():
    from unittest.mock import patch, MagicMock
    import sources.jobicy as jc

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"jobs": []}
    mock_resp.raise_for_status.return_value = None
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.jobicy.get_session", return_value=mock_session):
        assert jc.fetch({}) == []
