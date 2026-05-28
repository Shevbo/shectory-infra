"""Tests for score_vacancy_foreign_delta() function."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scan_v4 import score_vacancy_foreign_delta


def test_remoteok_clevel_gives_plus15():
    job = {"source": "remoteok", "name": "Chief Technology Officer"}
    assert score_vacancy_foreign_delta(job) == 15


def test_wwr_vp_engineering_gives_plus15():
    job = {"source": "wwr", "name": "VP Engineering"}
    assert score_vacancy_foreign_delta(job) == 15


def test_jobicy_head_of_engineering_gives_plus15():
    job = {"source": "jobicy", "name": "Head of Engineering"}
    assert score_vacancy_foreign_delta(job) == 15


def test_linkedin_cto_gives_plus15():
    job = {"source": "linkedin", "name": "CTO"}
    assert score_vacancy_foreign_delta(job) == 15


def test_visa_sponsor_in_desc_gives_plus10():
    job = {
        "source": "jobicy",
        "name": "Senior Director of Engineering",
        "snippet": {"description": "We offer visa sponsorship for qualified candidates."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == 10


def test_clevel_plus_visa_gives_plus25():
    job = {
        "source": "remoteok",
        "name": "CTO",
        "snippet": {"description": "Full relocation package including visa support."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == 25


def test_us_citizen_required_gives_minus20():
    job = {
        "source": "wwr",
        "name": "Senior Engineer",
        "snippet": {"description": "Must be US citizen or permanent resident."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == -20


def test_security_clearance_disqualifies():
    job = {
        "source": "hn_hiring",
        "name": "Security Engineer",
        "snippet": {"description": "Requires US security clearance."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == -20


def test_russian_hh_source_no_delta():
    job = {"source": "hh", "name": "CTO"}
    assert score_vacancy_foreign_delta(job) == 0


def test_telegram_source_no_delta():
    job = {"source": "telegram", "name": "Chief Technology Officer"}
    assert score_vacancy_foreign_delta(job) == 0


def test_unknown_source_no_delta():
    job = {"source": "unknown", "name": "CTO"}
    assert score_vacancy_foreign_delta(job) == 0


def test_delta_clevel_exact_case_insensitive():
    job = {"source": "linkedin", "name": "chief technology officer"}
    assert score_vacancy_foreign_delta(job) == 15


def test_delta_multiple_clevel_keywords():
    job = {
        "source": "remoteok",
        "name": "VP of Engineering Manager",
        "snippet": {"description": ""}
    }
    # Only one bonus per category
    delta = score_vacancy_foreign_delta(job)
    assert delta == 15


def test_delta_visa_relocation_both_keywords():
    job = {
        "source": "linkedin",
        "name": "CTO",
        "snippet": {"description": "We provide relocation package and visa sponsorship"}
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == 25


def test_delta_authorized_to_work_disqualifies():
    job = {
        "source": "jobicy",
        "name": "Engineer",
        "snippet": {"description": "Only authorized to work in US"}
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == -20


def test_delta_no_extra_keywords_zero():
    job = {
        "source": "wwr",
        "name": "Software Engineer",
        "snippet": {"description": "Looking for experienced engineer"}
    }
    assert score_vacancy_foreign_delta(job) == 0


def test_delta_with_none_snippet():
    job = {
        "source": "remoteok",
        "name": "CTO",
        "snippet": None
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == 15


def test_delta_with_missing_name():
    job = {
        "source": "linkedin",
        "snippet": {"description": "Looking for visa sponsorship"}
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == 10


def test_delta_case_insensitive_disqualify():
    job = {
        "source": "remoteok",
        "name": "Engineer",
        "snippet": {"description": "ONLY AUTHORIZED TO WORK in US"}
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta == -20
