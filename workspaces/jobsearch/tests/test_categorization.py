"""Tests for classify_section() function."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scan_v4 import classify_section


def test_remoteok_is_foreign_remote():
    assert classify_section({"source": "remoteok"}) == "foreign_remote"


def test_wwr_is_foreign_remote():
    assert classify_section({"source": "wwr"}) == "foreign_remote"


def test_jobicy_is_foreign_remote():
    assert classify_section({"source": "jobicy"}) == "foreign_remote"


def test_hn_hiring_is_foreign_remote():
    assert classify_section({"source": "hn_hiring"}) == "foreign_remote"


def test_linkedin_us_is_relocation_us():
    job = {"source": "linkedin", "area": {"name": "United States"}}
    assert classify_section(job) == "relocation_us"


def test_linkedin_california_is_relocation_us():
    job = {"source": "linkedin", "area": {"name": "San Francisco, California"}}
    assert classify_section(job) == "relocation_us"


def test_linkedin_eu_is_relocation_eu():
    job = {"source": "linkedin", "area": {"name": "Germany"}}
    assert classify_section(job) == "relocation_eu"


def test_linkedin_netherlands_is_relocation_eu():
    job = {"source": "linkedin", "area": {"name": "Amsterdam, Netherlands"}}
    assert classify_section(job) == "relocation_eu"


def test_linkedin_russia_remote_flag():
    job = {
        "source": "linkedin",
        "area": {"name": "Moscow, Russia"},
        "remote_flag": True
    }
    assert classify_section(job) == "remote"


def test_linkedin_moscow_no_remote_flag():
    job = {
        "source": "linkedin",
        "area": {"name": "Москва"},
        "remote_flag": False
    }
    assert classify_section(job) == "office"


def test_hh_remote_text():
    job = {"source": "hh", "name": "CTO удален"}
    assert classify_section(job) == "remote"


def test_hh_hybrid():
    job = {"source": "hh", "name": "CTO гибрид"}
    assert classify_section(job) == "hybrid"


def test_fl_ru_project():
    job = {"source": "fl_ru", "_work_format": "project"}
    assert classify_section(job) == "project"


def test_hh_office_default():
    job = {"source": "hh", "name": "CTO", "area": {"name": "Москва"}}
    assert classify_section(job) == "office"


def test_unknown_source_defaults_to_office():
    job = {"source": "unknown_source", "name": "Some Role"}
    assert classify_section(job) == "office"


def test_linkedin_russia_lowercase():
    job = {"source": "linkedin", "area": {"name": "москва"}}
    assert classify_section(job) == "office"


def test_classification_ignores_case_in_area():
    job = {"source": "linkedin", "area": {"name": "MOSCOW"}}
    assert classify_section(job) == "office"


def test_remote_snippet_in_requirement():
    job = {
        "source": "hh",
        "name": "CTO",
        "snippet": {"requirement": "Полностью удал работа"}
    }
    assert classify_section(job) == "remote"


def test_project_format_takes_precedence():
    job = {
        "source": "hh",
        "_work_format": "project",
        "name": "Some role",
        "area": {"name": "Moscow"}
    }
    assert classify_section(job) == "project"
