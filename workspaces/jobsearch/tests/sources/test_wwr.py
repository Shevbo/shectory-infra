import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/wwr_response.xml")


def _parse_with_fixture():
    from unittest.mock import patch, MagicMock
    import sources.wwr as wwr

    xml_text = open(FIXTURE, encoding="utf-8").read()

    mock_resp = MagicMock()
    mock_resp.text = xml_text
    mock_resp.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.wwr.get_session", return_value=mock_session):
        return wwr.fetch({})


def test_returns_list():
    assert isinstance(_parse_with_fixture(), list)


def test_clevel_filter():
    import re
    pattern = re.compile(r"(?i)\b(CTO|CIO|Chief Technology|Chief Information|VP Engineering|VP of Engineering|Head of Engineering|Director of Engineering|Engineering Director)\b")
    for job in _parse_with_fixture():
        assert pattern.search(job["name"]), f"Non-C-level: {job['name']}"


def test_required_fields():
    for job in _parse_with_fixture():
        assert job.get("id")
        assert job.get("name")
        assert job.get("source") == "wwr"
        assert job.get("remote_flag") is True


def test_empty_xml():
    from unittest.mock import patch, MagicMock
    import sources.wwr as wwr

    mock_resp = MagicMock()
    mock_resp.text = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    mock_resp.raise_for_status.return_value = None
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.wwr.get_session", return_value=mock_session):
        assert wwr.fetch({}) == []


def test_network_error():
    from unittest.mock import patch, MagicMock
    import sources.wwr as wwr

    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("timeout")

    with patch("sources.wwr.get_session", return_value=mock_session):
        assert wwr.fetch({}) == []
