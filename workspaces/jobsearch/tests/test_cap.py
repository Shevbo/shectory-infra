"""Tests for apply_source_cap() function."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scan_v4 import apply_source_cap


def _make_jobs(source, count, base_score=50):
    """Helper to create test jobs with descending scores."""
    return [(base_score - i, {"source": source, "name": f"Job {i}"}) for i in range(count)]


def test_cap_limits_per_source():
    jobs = _make_jobs("remoteok", 8)
    result = apply_source_cap(jobs, cap=5)
    remoteok_count = sum(1 for _, j in result if j["source"] == "remoteok")
    assert remoteok_count == 5


def test_cap_keeps_highest_score():
    jobs = [
        (10, {"source": "remoteok", "name": "Low"}),
        (90, {"source": "remoteok", "name": "High"}),
        (50, {"source": "remoteok", "name": "Mid"})
    ]
    result = apply_source_cap(jobs, cap=2)
    names = [j["name"] for _, j in result]
    assert "High" in names
    assert "Mid" in names
    assert "Low" not in names


def test_cap_does_not_affect_different_sources():
    jobs = _make_jobs("remoteok", 3) + _make_jobs("linkedin", 3)
    result = apply_source_cap(jobs, cap=5)
    assert len(result) == 6


def test_cap_empty_input():
    assert apply_source_cap([], cap=5) == []


def test_cap_default_is_5():
    jobs = _make_jobs("remoteok", 10)
    result = apply_source_cap(jobs)
    assert len(result) == 5


def test_cap_1_returns_one_per_source():
    jobs = _make_jobs("remoteok", 5) + _make_jobs("linkedin", 5)
    result = apply_source_cap(jobs, cap=1)
    assert len(result) == 2
    sources = {j["source"] for _, j in result}
    assert sources == {"remoteok", "linkedin"}


def test_cap_multiple_sources_respects_individual_caps():
    jobs = _make_jobs("remoteok", 7) + _make_jobs("linkedin", 4) + _make_jobs("hh", 6)
    result = apply_source_cap(jobs, cap=3)
    remoteok_count = sum(1 for _, j in result if j["source"] == "remoteok")
    linkedin_count = sum(1 for _, j in result if j["source"] == "linkedin")
    hh_count = sum(1 for _, j in result if j["source"] == "hh")
    assert remoteok_count == 3
    assert linkedin_count == 3
    assert hh_count == 3


def test_cap_sorting_by_score_descending():
    jobs = [
        (30, {"source": "remoteok", "name": "Low"}),
        (90, {"source": "remoteok", "name": "High"}),
        (60, {"source": "remoteok", "name": "Mid"}),
        (70, {"source": "remoteok", "name": "Higher"})
    ]
    result = apply_source_cap(jobs, cap=2)
    assert len(result) == 2
    scores = [s for s, _ in result]
    assert scores == [90, 70]


def test_cap_zero_returns_empty():
    jobs = _make_jobs("remoteok", 5)
    result = apply_source_cap(jobs, cap=0)
    assert len(result) == 0


def test_cap_large_number_keeps_all():
    jobs = _make_jobs("remoteok", 5) + _make_jobs("linkedin", 3)
    result = apply_source_cap(jobs, cap=100)
    assert len(result) == 8


def test_cap_preserves_job_data():
    job_data = {
        "source": "remoteok",
        "name": "Test Job",
        "id": "123",
        "employer": {"name": "Test Corp"}
    }
    jobs = [(50, job_data)]
    result = apply_source_cap(jobs, cap=5)
    assert len(result) == 1
    _, returned_job = result[0]
    assert returned_job["id"] == "123"
    assert returned_job["employer"]["name"] == "Test Corp"


def test_cap_mixed_scores_all_sources():
    jobs = [
        (100, {"source": "a", "name": "A1"}),
        (50, {"source": "b", "name": "B1"}),
        (90, {"source": "a", "name": "A2"}),
        (80, {"source": "c", "name": "C1"}),
        (70, {"source": "b", "name": "B2"}),
    ]
    result = apply_source_cap(jobs, cap=2)
    a_jobs = [j for _, j in result if j["source"] == "a"]
    b_jobs = [j for _, j in result if j["source"] == "b"]
    c_jobs = [j for _, j in result if j["source"] == "c"]
    assert len(a_jobs) == 2
    assert len(b_jobs) == 2
    assert len(c_jobs) == 1
    # Check ordering
    a_scores = [s for s, j in result if j["source"] == "a"]
    assert a_scores == [100, 90]


def test_cap_single_source():
    jobs = _make_jobs("remoteok", 10)
    result = apply_source_cap(jobs, cap=3)
    assert len(result) == 3
    assert all(j["source"] == "remoteok" for _, j in result)
