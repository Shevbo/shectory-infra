"""Tests for censor_watchdog — metrics computation and threshold detection."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from censor_watchdog import compute_metrics, check_thresholds, is_recent, load_active

SAMPLE_ROWS = [
    {"source_host": "smain", "source_agent": "main", "retry_score": 1.0, "error": None, "tokens_in": 18000, "session_tokens_in": 18000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 1.0, "error": None, "tokens_in": 18000, "session_tokens_in": 36000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 0.95, "error": None, "tokens_in": 18000, "session_tokens_in": 54000},
    {"source_host": "smain", "source_agent": "main", "retry_score": 0.0, "error": "timeout", "tokens_in": 500, "session_tokens_in": 54500},
    {"source_host": "sdev", "source_agent": "coder", "retry_score": 0.0, "error": None, "tokens_in": 5000, "session_tokens_in": 5000},
]


def test_compute_metrics_retry_rate():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["smain:main"]
    # 3 out of 4 have retry_score >= 0.85
    assert m["retry_rate"] == 0.75


def test_compute_metrics_error_rate():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["smain:main"]
    assert m["error_rate"] == 0.25


def test_compute_metrics_tokens_in():
    metrics = compute_metrics(SAMPLE_ROWS)
    assert metrics["smain:main"]["tokens_in"] == 18000 * 3 + 500


def test_compute_metrics_clean_agent():
    metrics = compute_metrics(SAMPLE_ROWS)
    m = metrics["sdev:coder"]
    assert m["retry_rate"] == 0.0
    assert m["error_rate"] == 0.0


def test_check_thresholds_retry_triggers():
    metrics = {"smain:main": {"retry_rate": 0.76, "error_rate": 0.0, "tokens_in": 100, "max_session_tokens": 0}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_tokens_triggers():
    metrics = {"smain:main": {"retry_rate": 0.0, "error_rate": 0.0, "tokens_in": 900_000, "max_session_tokens": 0}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_session_triggers():
    metrics = {"smain:main": {"retry_rate": 0.0, "error_rate": 0.0, "tokens_in": 100, "max_session_tokens": 250_000}}
    assert "smain:main" in check_thresholds(metrics)


def test_check_thresholds_clean_passes():
    metrics = {"sdev:coder": {"retry_rate": 0.1, "error_rate": 0.0, "tokens_in": 5000, "max_session_tokens": 10000}}
    assert check_thresholds(metrics) == []


def test_is_recent_fresh():
    ts = datetime.now(timezone.utc).isoformat()
    assert is_recent(ts, minutes=30) is True


def test_is_recent_stale():
    ts = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
    assert is_recent(ts, minutes=30) is False


def test_load_active_missing(tmp_path, monkeypatch):
    import censor_watchdog
    monkeypatch.setattr(censor_watchdog, "ACTIVE_INVESTIGATIONS", tmp_path / "active.json")
    assert load_active() == {}
