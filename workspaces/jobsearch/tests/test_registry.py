# tests/test_registry.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sources import SOURCE_REGISTRY

EXPECTED_NAMES = {
    "hh", "linkedin", "trudvsem", "habr", "superjob", "telegram",
    "fl_ru", "freelance_ru", "remoteok", "wwr", "jobicy", "hn_hiring",
}


def test_registry_size():
    assert len(SOURCE_REGISTRY) == 12


def test_registry_names():
    names = {s.name for s in SOURCE_REGISTRY}
    assert names == EXPECTED_NAMES


def test_each_source_has_callable_fetch():
    for src in SOURCE_REGISTRY:
        assert callable(src.fetch), f"{src.name}.fetch is not callable"


def test_each_source_has_queries():
    for src in SOURCE_REGISTRY:
        assert len(src.queries) >= 1, f"{src.name} has no queries"


def test_no_proxy_sources():
    no_proxy = {s.name for s in SOURCE_REGISTRY if not s.use_proxy}
    assert "remoteok" in no_proxy
    assert "wwr" in no_proxy
    assert "jobicy" in no_proxy


def test_proxy_sources():
    proxy = {s.name for s in SOURCE_REGISTRY if s.use_proxy}
    assert "linkedin" in proxy
    assert "hn_hiring" in proxy
    assert "hh" in proxy
