import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources.base import title_hash, Source, get_session, CLEVEL_PATTERN


def test_title_hash_stable():
    job = {"name": "CTO", "employer": {"name": "Acme"}}
    assert title_hash(job) == title_hash(job)


def test_title_hash_normalizes():
    a = {"name": "  CTO!! ", "employer": {"name": "Acme Corp."}}
    b = {"name": "cto", "employer": {"name": "acme corp"}}
    assert title_hash(a) == title_hash(b)


def test_title_hash_different_jobs():
    a = {"name": "CTO", "employer": {"name": "Acme"}}
    b = {"name": "VP Engineering", "employer": {"name": "Beta"}}
    assert title_hash(a) != title_hash(b)


def test_clevel_pattern_matches():
    for title in ["CTO", "Chief Technology Officer", "VP Engineering", "Head of Engineering"]:
        assert CLEVEL_PATTERN.search(title), f"Should match: {title}"


def test_clevel_pattern_no_match():
    assert not CLEVEL_PATTERN.search("Sales Manager")
    assert not CLEVEL_PATTERN.search("Director of Marketing")


def test_source_dataclass():
    src = Source(name="test", queries=[{}], fetch=lambda p: [])
    assert src.name == "test"
    assert src.sleep == 1.0
    assert src.use_proxy is True
