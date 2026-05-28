# Foreign Job Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix LinkedIn parser, add 4 new foreign job sources (RemoteOK, WWR, Jobicy, HN Hiring), modularize scan_v4.py into a sources/ package, and add ЗАРУБЕЖНАЯ УДАЛЁНКА / РЕЛОКАЦИЯ sections to the digest.

**Architecture:** Extract each fetcher into `sources/<name>.py` with a standard `(NAME, QUERIES, fetch)` contract; wire them via `SOURCE_REGISTRY` in `sources/__init__.py`; refactor `scan_v4.py` main() to iterate the registry; extend `classify_section()` and `build_template_report()` for two new sections.

**Tech Stack:** Python 3.12, requests, BeautifulSoup4, xml.etree.ElementTree, pytest. All proxy/direct calls via `get_session(use_proxy=True/False)`.

**Spec:** `docs/superpowers/specs/2026-05-28-foreign-sources-design.md`

---

## File Map

| File | Action | What it does |
|---|---|---|
| `sources/__init__.py` | CREATE | SOURCE_REGISTRY |
| `sources/base.py` | CREATE | Source dataclass, retry, get_session, title_hash, CLEVEL_PATTERN |
| `sources/hh.py` | CREATE | Moved from scan_v4.py lines 136-201 |
| `sources/linkedin.py` | CREATE | FIXED parser (base-card), 6 queries RU/EU/US |
| `sources/trudvsem.py` | CREATE | Moved from scan_v4.py lines 336-382 |
| `sources/habr.py` | CREATE | Moved from scan_v4.py lines 484-532 |
| `sources/superjob.py` | CREATE | Moved from scan_v4.py lines 534-575 |
| `sources/telegram.py` | CREATE | Moved from scan_v4.py lines 385-461 |
| `sources/flru.py` | CREATE | Moved from scan_v4.py lines 579-619 |
| `sources/freelanceru.py` | CREATE | Moved from scan_v4.py lines 622-662 |
| `sources/remoteok.py` | CREATE | RemoteOK JSON API (no proxy, curl UA) |
| `sources/wwr.py` | CREATE | WWR RSS /remote-jobs.rss (no proxy) |
| `sources/jobicy.py` | CREATE | Jobicy JSON API (no proxy) |
| `sources/hn_hiring.py` | CREATE | HN Who's Hiring via Algolia (with proxy) |
| `scan_v4.py` | MODIFY | main(): use SOURCE_REGISTRY loop; add title_hash dedup; add scoring delta; load_seen/save_seen migration |
| `scan_v4.py` | MODIFY | classify_section(): add foreign_remote/relocation_us/relocation_eu |
| `scan_v4.py` | MODIFY | score_vacancy_foreign_delta(): +15 C-level, +10 visa, -20 US-only |
| `scan_v4.py` | MODIFY | build_template_report(): add ЗАРУБЕЖНАЯ УДАЛЁНКА + РЕЛОКАЦИЯ sections, per-source cap |
| `tests/sources/__init__.py` | CREATE | empty |
| `tests/sources/test_linkedin.py` | CREATE | regression test with fixture |
| `tests/sources/test_remoteok.py` | CREATE | unit test with fixture |
| `tests/sources/test_wwr.py` | CREATE | unit test with fixture |
| `tests/sources/test_jobicy.py` | CREATE | unit test with fixture |
| `tests/sources/test_hn_hiring.py` | CREATE | unit test with fixture |
| `tests/test_categorization.py` | CREATE | classify_section tests |
| `tests/test_scoring_delta.py` | CREATE | foreign delta tests |
| `tests/test_cap.py` | CREATE | per-source cap test |
| `tests/test_registry.py` | CREATE | SOURCE_REGISTRY integrity |
| `career-bot/scanner.py` | MODIFY | _derive_source: add linkedin/remoteok/wwr/jobicy/hn_hiring |
| `tests/fixtures/` | EXISTS | linkedin_response.html, remoteok_response.json, wwr_response.xml, hn_response.json, jobicy_response.json |

---

## Task 1: Scaffold

**Files:**
- Create: `sources/__init__.py` (empty for now)
- Create: `sources/base.py` (placeholder)
- Create: `tests/sources/__init__.py`
- Create: `tests/fixtures/` (already done — fixtures captured)

- [ ] **Step 1: Create source package structure**

```bash
cd ~/workspaces/jobsearch
mkdir -p sources tests/sources
touch sources/__init__.py tests/sources/__init__.py
```

- [ ] **Step 2: Create `sources/base.py`**

```python
# sources/base.py
import functools
import hashlib
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import requests

LINEMAN_PROXY = os.environ.get("LINEMAN_PROXY", "http://127.0.0.1:9090")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

HH_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

CLEVEL_PATTERN = re.compile(
    r"(?i)(CTO|CIO|Chief Technology|Chief Information|VP Engineering|VP of Engineering"
    r"|Head of Engineering|Director of Engineering|Engineering Director)"
)


@dataclass
class Source:
    name: str
    queries: list
    fetch: Callable
    sleep: float = 1.0
    use_proxy: bool = True


def get_session(extra_headers=None, use_proxy=True):
    s = requests.Session()
    s.headers.update(HEADERS)
    if extra_headers:
        s.headers.update(extra_headers)
    if use_proxy:
        s.proxies = {"http": LINEMAN_PROXY, "https": LINEMAN_PROXY}
    else:
        s.trust_env = False
    return s


def retry(max_attempts=3, delay=2.0, backoff=2.0,
          exceptions=(ConnectionError, TimeoutError,
                      requests.ConnectionError, requests.Timeout)):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        wait = delay * (backoff ** (attempt - 1)) + random.uniform(0, 0.5)
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def title_hash(job: dict) -> str:
    name = re.sub(r"[^\w\s]", "", (job.get("name") or "").lower()).strip()
    company = re.sub(r"[^\w\s]", "", ((job.get("employer") or {}).get("name") or "").lower()).strip()
    return hashlib.sha1(f"{name}|{company}".encode()).hexdigest()[:12]
```

- [ ] **Step 3: Write base tests**

```python
# tests/test_base.py
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
```

- [ ] **Step 4: Run tests to verify base is importable**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/test_base.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/ tests/sources/__init__.py tests/test_base.py tests/fixtures/
git commit -m "feat(jobsearch): scaffold sources/ package + base module + test fixtures"
```

---

## Task 2: Fix LinkedIn

**Files:**
- Create: `sources/linkedin.py`
- Create: `tests/sources/test_linkedin.py`

- [ ] **Step 1: Write the failing regression test**

```python
# tests/sources/test_linkedin.py
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


def test_six_cards_in_fixture():
    """Fixture captured 2026-05-28 contains 6 li[data-entity-urn] cards."""
    html = open(FIXTURE, encoding="utf-8").read()
    jobs = _parse_with_fixture(html)
    assert len(jobs) == 6, f"Expected 6, got {len(jobs)}"


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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_linkedin.py -v 2>&1 | head -30
```

Expected: ImportError or AttributeError (sources/linkedin.py does not exist yet)

- [ ] **Step 3: Create `sources/linkedin.py`**

```python
# sources/linkedin.py
import re
from bs4 import BeautifulSoup
from .base import get_session, retry

NAME = "linkedin"

QUERIES = [
    # Russia — remote-only (f_WT=2)
    {"keywords": "CTO", "location": "Russia", "f_E": "5,6", "f_WT": "2"},
    {"keywords": "Head of Engineering", "location": "Russia", "f_E": "5", "f_WT": "2"},
    # EU
    {"keywords": "CTO", "location": "European Union", "f_E": "5,6"},
    {"keywords": "VP Engineering", "location": "European Union", "f_E": "5"},
    # US
    {"keywords": "Chief Technology Officer", "location": "United States", "f_E": "5,6"},
    {"keywords": "Director of Engineering", "location": "United States", "f_E": "5"},
]


@retry()
def fetch(params: dict) -> list[dict]:
    try:
        s = get_session(
            extra_headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            use_proxy=True,
        )
        r = s.get(
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
            params={k: v for k, v in params.items()},
            timeout=25,
        )
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.find_all("li", attrs={"data-entity-urn": re.compile(r"jobPosting")})

    jobs = []
    for card in cards:
        urn = card.get("data-entity-urn", "")
        id_match = re.search(r"jobPosting:(\d+)", urn)
        if not id_match:
            continue

        title_el = card.find("span", class_=re.compile("screen-reader-text"))
        if not title_el:
            title_el = card.find("h3")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name:
            continue

        comp_el = card.find(class_=re.compile(r"base-search-card__subtitle"))
        if not comp_el:
            comp_el = card.find(class_=re.compile(r"job-search-card__company-name"))
        company = comp_el.get_text(strip=True) if comp_el else ""

        loc_el = card.find(class_=re.compile(r"job-search-card__location"))
        area = loc_el.get_text(strip=True) if loc_el else ""

        link_el = card.find("a", href=re.compile(r"jobs/view/"))
        url = link_el["href"] if link_el else ""
        if url.startswith("/"):
            url = "https://www.linkedin.com" + url

        jobs.append({
            "id": id_match.group(1),
            "source": NAME,
            "name": name,
            "employer": {"name": company},
            "area": {"name": area},
            "alternate_url": url,
            "remote_flag": params.get("f_WT") == "2",
        })

    return jobs
```

- [ ] **Step 4: Run tests — expect all pass**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_linkedin.py -v
```

Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/linkedin.py tests/sources/test_linkedin.py
git commit -m "feat(jobsearch): fix LinkedIn parser — base-card selector, add EU/US/remote queries"
```

---

## Task 3: RemoteOK source

**Files:**
- Create: `sources/remoteok.py`
- Create: `tests/sources/test_remoteok.py`

Note: RemoteOK requires `User-Agent: curl/7.88.1` + `Accept: application/json` and does NOT work through Lineman proxy (returns HTML). Set `use_proxy=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_remoteok.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/remoteok_response.json")


def _parse_with_fixture():
    from unittest.mock import patch, MagicMock
    import sources.remoteok as rok

    data = json.loads(open(FIXTURE).read())

    mock_resp = MagicMock()
    mock_resp.json.return_value = data
    mock_resp.raise_for_status.return_value = None

    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.remoteok.get_session", return_value=mock_session):
        return rok.fetch(rok.QUERIES[0])


def test_returns_list():
    jobs = _parse_with_fixture()
    assert isinstance(jobs, list)


def test_clevel_filter():
    """Only C-level titles pass through."""
    jobs = _parse_with_fixture()
    import re
    pattern = re.compile(r"(?i)(CTO|CIO|Chief|Head of|VP|Director)")
    for job in jobs:
        assert pattern.search(job["name"]), f"Non-C-level slipped through: {job['name']}"


def test_required_fields():
    jobs = _parse_with_fixture()
    for job in jobs:
        assert job.get("id")
        assert job.get("name")
        assert job.get("source") == "remoteok"
        assert job.get("remote_flag") is True


def test_empty_response():
    from unittest.mock import patch, MagicMock
    import sources.remoteok as rok

    mock_resp = MagicMock()
    mock_resp.json.return_value = [{"legal": "metadata row, no slug"}]
    mock_resp.raise_for_status.return_value = None
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    with patch("sources.remoteok.get_session", return_value=mock_session):
        assert rok.fetch({}) == []


def test_no_proxy_flag():
    """Verify source is registered with use_proxy=False."""
    from sources import SOURCE_REGISTRY
    src = next((s for s in SOURCE_REGISTRY if s.name == "remoteok"), None)
    # will be available after Task 9; skip if not yet registered
    if src is not None:
        assert src.use_proxy is False
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_remoteok.py::test_returns_list -v 2>&1 | head -15
```

Expected: ImportError (sources/remoteok.py does not exist)

- [ ] **Step 3: Create `sources/remoteok.py`**

```python
# sources/remoteok.py
import re
from .base import get_session, retry, CLEVEL_PATTERN

NAME = "remoteok"

QUERIES = [
    {"tag": "exec"},
    {"tag": "management"},
]


@retry()
def fetch(params: dict) -> list[dict]:
    tag = params.get("tag", "exec")
    try:
        s = get_session(
            extra_headers={
                "User-Agent": "curl/7.88.1",
                "Accept": "application/json",
            },
            use_proxy=False,
        )
        r = s.get(f"https://remoteok.com/api?tags={tag}", timeout=25)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    jobs = []
    for item in data:
        if not isinstance(item, dict) or not item.get("slug"):
            continue
        if not CLEVEL_PATTERN.search(item.get("position", "")):
            continue
        jobs.append({
            "id": str(item.get("id") or item["slug"]),
            "source": NAME,
            "name": item.get("position", ""),
            "employer": {"name": item.get("company", "")},
            "area": {"name": item.get("location") or "Remote"},
            "alternate_url": item.get("url", ""),
            "snippet": {"description": (item.get("description") or "")[:500]},
            "remote_flag": True,
        })
    return jobs
```

- [ ] **Step 4: Run tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_remoteok.py -v -k "not test_no_proxy_flag"
```

Expected: 4 PASS (no_proxy_flag skipped until registry is wired in Task 9)

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/remoteok.py tests/sources/test_remoteok.py
git commit -m "feat(jobsearch): add RemoteOK source (exec/management JSON feed)"
```

---

## Task 4: WWR source

**Files:**
- Create: `sources/wwr.py`
- Create: `tests/sources/test_wwr.py`

Note: `/categories/remote-management-jobs.rss` returns 301 forever. Use `/remote-jobs.rss` with `use_proxy=False`.

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_wwr.py
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
    pattern = re.compile(r"(?i)(CTO|CIO|Chief|Head of|VP|Director)")
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_wwr.py::test_returns_list -v 2>&1 | head -10
```

Expected: ImportError

- [ ] **Step 3: Create `sources/wwr.py`**

```python
# sources/wwr.py
import xml.etree.ElementTree as ET
from .base import get_session, retry, CLEVEL_PATTERN

NAME = "wwr"

QUERIES = [{}]  # single full-feed fetch


@retry()
def fetch(params: dict) -> list[dict]:
    try:
        s = get_session(use_proxy=False)
        r = s.get(
            "https://weworkremotely.com/remote-jobs.rss",
            timeout=30,
            allow_redirects=True,
        )
        r.raise_for_status()
    except Exception:
        return []

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError:
        return []

    jobs = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", "")
        if not CLEVEL_PATTERN.search(title):
            continue
        # Title convention: "Company Name: Job Title"
        parts = title.split(": ", 1)
        company = parts[0].strip() if len(parts) == 2 else ""
        position = parts[1].strip() if len(parts) == 2 else title.strip()
        guid = item.findtext("guid", "")
        link = item.findtext("link", "")
        desc = item.findtext("description", "")[:500]
        jobs.append({
            "id": guid or link,
            "source": NAME,
            "name": position,
            "employer": {"name": company},
            "area": {"name": "Remote"},
            "alternate_url": link,
            "snippet": {"description": desc},
            "remote_flag": True,
        })
    return jobs
```

- [ ] **Step 4: Run tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_wwr.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/wwr.py tests/sources/test_wwr.py
git commit -m "feat(jobsearch): add We Work Remotely source (RSS, no proxy)"
```

---

## Task 5: Jobicy source

**Files:**
- Create: `sources/jobicy.py`
- Create: `tests/sources/test_jobicy.py`

Jobicy replaces Remotive (Remotive returns 403 from this server). Free JSON API, no auth, no proxy needed.

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_jobicy.py
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
    import re
    pattern = re.compile(r"(?i)(CTO|CIO|Chief|Head of|VP|Director)")
    for job in _parse_with_fixture():
        assert pattern.search(job["name"]), f"Non-C-level: {job['name']}"


def test_required_fields():
    for job in _parse_with_fixture():
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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_jobicy.py::test_returns_list -v 2>&1 | head -10
```

Expected: ImportError

- [ ] **Step 3: Create `sources/jobicy.py`**

```python
# sources/jobicy.py
from .base import get_session, retry, CLEVEL_PATTERN

NAME = "jobicy"

QUERIES = [
    {"tag": "cto"},
    {"tag": "vp-engineering"},
]


@retry()
def fetch(params: dict) -> list[dict]:
    tag = params.get("tag", "cto")
    try:
        s = get_session(use_proxy=False)
        r = s.get(
            f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={tag}",
            timeout=25,
        )
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    jobs = []
    for j in data.get("jobs", []):
        if not CLEVEL_PATTERN.search(j.get("jobTitle", "")):
            continue
        jobs.append({
            "id": str(j.get("id") or j.get("jobSlug", "")),
            "source": NAME,
            "name": j.get("jobTitle", ""),
            "employer": {"name": j.get("companyName", "")},
            "area": {"name": j.get("jobGeo") or "Remote"},
            "alternate_url": j.get("url", ""),
            "snippet": {"description": (j.get("jobExcerpt") or "")[:500]},
            "remote_flag": True,
        })
    return jobs
```

- [ ] **Step 4: Run tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_jobicy.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/jobicy.py tests/sources/test_jobicy.py
git commit -m "feat(jobsearch): add Jobicy source (remote JSON API, replaces blocked Remotive)"
```

---

## Task 6: HN Who's Hiring source

**Files:**
- Create: `sources/hn_hiring.py`
- Create: `tests/sources/test_hn_hiring.py`

Two-step: (1) fetch latest "Ask HN: Who is hiring?" thread ID, (2) search comments of that thread. Thread ID is cached in-process. Works through Lineman proxy.

- [ ] **Step 1: Write the failing test**

```python
# tests/sources/test_hn_hiring.py
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

FIXTURE = os.path.join(os.path.dirname(__file__), "../fixtures/hn_response.json")


def _parse_with_fixture():
    """Inject fixture as the comment search response; mock thread fetch."""
    from unittest.mock import patch, MagicMock, call
    import sources.hn_hiring as hn

    # Reset thread cache between tests
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


def test_clevel_filter():
    import re
    pattern = re.compile(r"(?i)(CTO|CIO|Chief|Head of|VP|Director)")
    for job in _parse_with_fixture():
        assert pattern.search(job["name"] + " " + job.get("snippet", {}).get("description", "")), \
            f"Non-C-level: {job['name']}"


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
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_hn_hiring.py::test_returns_list -v 2>&1 | head -10
```

Expected: ImportError

- [ ] **Step 3: Create `sources/hn_hiring.py`**

```python
# sources/hn_hiring.py
import html as _html
import re
from .base import get_session, retry, CLEVEL_PATTERN

NAME = "hn_hiring"

QUERIES = [
    {"query": "CTO"},
    {"query": "Head of Engineering"},
    {"query": "VP Engineering"},
    {"query": "Director of Engineering"},
]

_thread_id_cache: dict = {}


def _get_thread_id(session) -> str | None:
    if "id" in _thread_id_cache:
        return _thread_id_cache["id"]
    try:
        r = session.get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": "story,author_whoishiring"},
            timeout=15,
        )
        tid = r.json()["hits"][0]["objectID"]
        _thread_id_cache["id"] = tid
        return tid
    except Exception:
        return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", _html.unescape(text or ""))


def _parse_location(text: str) -> str:
    m = re.search(r"\|\s*(REMOTE|Remote|[A-Z][a-zA-Z\s]+(?:,\s*[A-Z]{2})?)\b", text)
    return m.group(1).strip() if m else "Remote"


def _parse_company(text: str) -> str:
    m = re.search(
        r"^([A-Za-z0-9][\w\s&.\-,]+?)\s+(?:is\s+hiring|is\s+looking|seeks?|wants?)",
        text,
    )
    return m.group(1).strip() if m else ""


@retry()
def fetch(params: dict) -> list[dict]:
    query = params.get("query", "CTO")
    try:
        s = get_session(use_proxy=True)
        thread_id = _get_thread_id(s)
        if not thread_id:
            return []
        r = s.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "tags": f"comment,story_{thread_id}",
                "query": query,
                "hitsPerPage": 50,
            },
            timeout=20,
        )
        data = r.json()
    except Exception:
        return []

    jobs = []
    for hit in data.get("hits", []):
        text = _strip_html(hit.get("comment_text", ""))
        if not text:
            continue
        if not CLEVEL_PATTERN.search(text[:300]):
            continue
        jobs.append({
            "id": hit["objectID"],
            "source": NAME,
            "name": text[:80].strip(),
            "employer": {"name": _parse_company(text)},
            "area": {"name": _parse_location(text)},
            "alternate_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
            "snippet": {"description": text[:500]},
        })
    return jobs
```

- [ ] **Step 4: Run tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/sources/test_hn_hiring.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/hn_hiring.py tests/sources/test_hn_hiring.py
git commit -m "feat(jobsearch): add HN Who's Hiring source (Algolia API)"
```

---

## Task 7: Migrate existing sources + wire SOURCE_REGISTRY

**Files:**
- Create: `sources/hh.py`, `sources/trudvsem.py`, `sources/habr.py`, `sources/superjob.py`, `sources/telegram.py`, `sources/flru.py`, `sources/freelanceru.py`
- Modify: `sources/__init__.py`

This is mechanical extraction — copy each fetcher + queries + constants from scan_v4.py into its module, import `get_session`, `retry`, `HH_UAS` from base. No logic changes.

- [ ] **Step 1: Create `sources/hh.py`**

Copy `HH_SEARCH_QUERIES`, `parse_hh_salary`, `clean_hh_url`, `fetch_hh_web` from scan_v4.py lines 136-201 + 96-104 + 204-234. Add imports from base.

```python
# sources/hh.py
import random, re, urllib.parse
from bs4 import BeautifulSoup
from .base import get_session, retry, HH_UAS

NAME = "hh"

QUERIES = [
    "директор по ИТ", "технический директор", "CTO", "CIO",
    "head of IT", "директор по цифровой трансформации",
    "CDTO", "AI Architect", "IT директор",
]


def clean_hh_url(url: str) -> str:
    if not url:
        return url
    m = re.search(r"/vacancy/(\d+)", url)
    if m:
        return f"https://hh.ru/vacancy/{m.group(1)}"
    return url


def parse_hh_salary(text):
    text = text.replace(" ", " ").replace("\xa0", " ").replace("–", "-")
    currency = "RUR"
    if "₽" in text or "руб" in text:
        currency = "RUR"
    elif "$" in text:
        currency = "USD"
    elif "€" in text:
        currency = "EUR"
    m = re.search(r"от\s*([\d\s]+)\s*(?:до\s*([\d\s]+))?\s*(?:₽|руб|\$|€)", text, re.IGNORECASE)
    if m:
        salary = {"currency": currency}
        frm = int(m.group(1).replace(" ", "")) if m.group(1) else None
        to = int(m.group(2).replace(" ", "")) if m.group(2) else None
        if frm and frm > 1000:
            salary["from"] = frm
        if to and to > 1000:
            salary["to"] = to
        if salary.get("from") or salary.get("to"):
            return salary
    m = re.search(r"до\s*([\d\s]+)\s*(?:₽|руб|\$|€)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(" ", ""))
        if val > 1000:
            return {"to": val, "currency": currency}
    m = re.search(r"([\d\s]+)\s*[-–]\s*([\d\s]+)\s*(?:₽|руб|\$|€)", text)
    if m:
        frm = int(m.group(1).replace(" ", ""))
        to = int(m.group(2).replace(" ", ""))
        if frm > 1000 and to > 1000:
            return {"from": frm, "to": to, "currency": currency}
    return None


@retry()
def fetch(query: dict | str) -> list[dict]:
    q = query if isinstance(query, str) else query.get("q", "")
    try:
        import time
        s = get_session(
            extra_headers={
                "User-Agent": random.choice(HH_UAS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Referer": "https://hh.ru/",
            }
        )
        s.get("https://hh.ru/", timeout=15)
        import time as _t; _t.sleep(random.uniform(1.0, 2.5))
        params = {"text": q, "area": 1, "items_on_page": 20, "order_by": "publication_time"}
        r = s.get("https://hh.ru/search/vacancy", params=params, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for block in soup.select('[data-qa*="vacancy-serp__vacancy"]'):
        job = {"source": NAME}
        title_el = block.select_one('[data-qa="serp-item__title"]')
        if not title_el:
            continue
        job["name"] = title_el.get_text(strip=True)
        raw_url = title_el.get("href", "")
        job["alternate_url"] = clean_hh_url(raw_url)
        if not job["name"]:
            continue
        id_match = re.search(r"/vacancy/(\d+)", job["alternate_url"])
        job["id"] = id_match.group(1) if id_match else f"hh-{abs(hash(q + job['name'])) % 10**8}"
        employer_el = block.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
        if employer_el:
            job["employer"] = {"name": employer_el.get_text(strip=True)}
        salary = parse_hh_salary(block.get_text())
        if salary:
            job["salary"] = salary
        loc_el = block.select_one('[data-qa="vacancy-serp__vacancy-address"]')
        if loc_el:
            job["area"] = {"name": loc_el.get_text(strip=True).split(",")[0].strip()}
        snippet_el = block.select_one('[data-qa*="vacancy-serp__vacancy_snippet"]')
        if snippet_el:
            job["snippet"] = {"requirement": snippet_el.get_text(strip=True)}
        jobs.append(job)
    return jobs
```

- [ ] **Step 2: Create `sources/trudvsem.py`**

```python
# sources/trudvsem.py
import urllib.parse
from .base import get_session, retry

NAME = "trudvsem"

QUERIES = [
    {"text": "технический директор"},
    {"text": "директор по информационным технологиям"},
    {"text": "CTO"},
    {"text": "IT директор"},
]


@retry()
def fetch(params: dict) -> list[dict]:
    text = params.get("text", "")
    url = f"http://opendata.trudvsem.ru/api/v1/vacancies?text={urllib.parse.quote(text)}&offset=0&limit=50"
    try:
        s = get_session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []
    vacancies = data.get("results", {}).get("vacancies", [])
    jobs = []
    for item in vacancies:
        v = item.get("vacancy", {})
        job = {
            "id": v.get("id", ""),
            "name": v.get("job-name", ""),
            "employer": {"name": v.get("company", {}).get("short_name", "") or v.get("company", {}).get("name", "")},
            "area": {"name": v.get("region", {}).get("name", "")},
            "alternate_url": f"https://trudvsem.ru/vacancy/view/{v.get('id', '')}",
            "source": NAME,
            "description": v.get("duty", ""),
        }
        salary: dict = {}
        if v.get("salary_min"):
            salary["from"] = int(float(v["salary_min"]))
        if v.get("salary_max"):
            salary["to"] = int(float(v["salary_max"]))
        salary["currency"] = "RUR"
        job["salary"] = salary if salary.get("from") or salary.get("to") else None
        if job["name"]:
            jobs.append(job)
    return jobs
```

- [ ] **Step 2b: Create `sources/habr.py`**

```python
# sources/habr.py
import random, re, urllib.parse
from bs4 import BeautifulSoup
from .base import get_session, retry, HH_UAS
from .hh import parse_hh_salary

NAME = "habr"

QUERIES = ["CTO", "IT-директор", "технический директор", "Team Lead"]


@retry()
def fetch(params: dict) -> list[dict]:
    query = params.get("q", "") if isinstance(params, dict) else str(params)
    url = f"https://career.habr.com/vacancies?q={urllib.parse.quote(query)}&type=all"
    try:
        s = get_session(extra_headers={"User-Agent": random.choice(HH_UAS), "Accept-Language": "ru-RU,ru;q=0.9"})
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []
    jobs = []
    for card in soup.select(".vacancy-card"):
        job = {"source": NAME}
        title_el = card.select_one(".vacancy-card__title")
        if not title_el:
            continue
        job["name"] = title_el.get_text(strip=True)
        link_el = title_el.find("a")
        if link_el and link_el.get("href"):
            href = link_el["href"]
            job["alternate_url"] = "https://career.habr.com" + href if href.startswith("/") else href
        meta_el = card.select_one(".vacancy-card__meta")
        if meta_el:
            job["employer"] = {"name": meta_el.get_text(strip=True)}
        salary_el = card.select_one(".vacancy-card__salary")
        if salary_el:
            sal = parse_hh_salary(salary_el.get_text(strip=True))
            if sal:
                job["salary"] = sal
        job["id"] = f"habr-{abs(hash(query + job.get('name', ''))) % 10**8}"
        jobs.append(job)
    return jobs
```

- [ ] **Step 2c: Create `sources/superjob.py`**

```python
# sources/superjob.py
import random, urllib.parse
from bs4 import BeautifulSoup
from .base import get_session, retry, HH_UAS

NAME = "superjob"

QUERIES = ["технический директор", "CTO", "IT директор"]


@retry()
def fetch(params: dict) -> list[dict]:
    query = params.get("q", "") if isinstance(params, dict) else str(params)
    url = f"https://russia.superjob.ru/vacancy/search/?keywords={urllib.parse.quote(query)}"
    try:
        s = get_session(extra_headers={"User-Agent": random.choice(HH_UAS), "Accept-Language": "ru-RU,ru;q=0.9"})
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []
    jobs = []
    for card in soup.select('[class*="_vacancy"]'):
        job = {"source": NAME}
        title_el = card.select_one('[class*="_title"]')
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name or len(name) < 5:
            continue
        job["name"] = name
        link_el = title_el.find("a") if hasattr(title_el, "find") else None
        if link_el and link_el.get("href"):
            href = link_el["href"]
            job["alternate_url"] = "https://russia.superjob.ru" + href if href.startswith("/") else href
        job["id"] = f"sj-{abs(hash(query + name)) % 10**8}"
        jobs.append(job)
    return jobs
```

- [ ] **Step 2d: Create `sources/telegram.py`**

```python
# sources/telegram.py
import html, re
from .base import get_session, retry

NAME = "telegram"

CHANNELS = ["forchiefs", "jobfortm", "geekjobs", "cto_ru", "remote_ru"]

_CLEVEL_KW = [
    "директор", "cto", "cio", "cdto", "head of it", "head of engineering",
    "vp engineering", "vp of", "chief", "технический директор",
    "it director", "руководитель", "ai architect", "вакансия",
    "ищем", "требуется", "открыта", "в команду",
]

_TITLE_PATTERNS = [
    r'(?:ищем|требуется|вакансия|открыта\s+вакансия|открыта\s+позиция|нанимаем|в\s+поиск)\s+[«""]?([A-ZА-Я][A-Za-zА-Яа-я/\s]{2,60}?)[»""]?(?:\s*[\(—\-–]|\s+с\s+зарплатой|\s+в\s+команду|$)',
    r'(?:ищем|нужен|нужна|нужно)\s+([A-ZА-Я][A-Za-zА-Яа-я\s/]{2,60}?)(?:\s*[\(—\-–]|\s*с\s+зарплатой|\s+в\s+команду|$)',
    r'\b(CTO|CIO|CDTO|VP\s+of\s+[A-Z][a-z]+|Head\s+of\s+[A-Z][a-z]+|Chief\s+[A-Z][a-z]+\s+[A-Z][a-z]+|AI\s+Architect|IT\s+Director|Technical\s+Director)\b',
    r'(Технический\s+директор|IT[\s-]*директор|Директор\s+по\s+ИТ|Руководитель\s+отдела\s+разработки)',
]


def _extract_title(text: str) -> str:
    for pat in _TITLE_PATTERNS:
        m = re.search(pat, text[:400], re.IGNORECASE)
        if m:
            t = m.group(1).strip().rstrip(".,;:!?")
            if 3 < len(t) < 80:
                return t[:80]
    return ""


@retry()
def fetch(params: dict) -> list[dict]:
    channel = params.get("channel", "")
    url = f"https://t.me/s/{channel}"
    try:
        s = get_session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        html_content = r.text
    except Exception:
        return []

    messages = re.findall(
        r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>.*?<div class="tgme_widget_message[^"]*"[^>]*>.*?</div>\s*</div>',
        html_content, re.DOTALL,
    )
    jobs, seen = [], set()
    for msg in messages:
        text_match = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', msg, re.DOTALL)
        if not text_match:
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", text_match.group(1))).strip()
        if not any(k in text.lower() for k in _CLEVEL_KW):
            continue
        key = text[:100]
        if key in seen:
            continue
        seen.add(key)
        link_m = re.search(r'<a[^>]*href="([^"]+)"[^>]*class="tgme_widget_message_date"[^>]*>', msg, re.DOTALL)
        msg_url = link_m.group(1) if link_m else ""
        date_m = re.search(r'datetime="([^"]+)"', msg)
        pub_date = date_m.group(1)[:10] if date_m else ""
        jobs.append({
            "id": f"tg-{channel}-{abs(hash(text[:100])) % 10**8}",
            "name": _extract_title(text) or "Вакансия из Telegram",
            "employer": {"name": f"@{channel}"},
            "snippet": {"requirement": text[:300]},
            "alternate_url": msg_url,
            "source": NAME,
            "published_at": pub_date,
        })
    return jobs
```

- [ ] **Step 2e: Create `sources/flru.py`**

```python
# sources/flru.py
import random, re, urllib.parse
from bs4 import BeautifulSoup
from .base import get_session, retry, HH_UAS

NAME = "fl_ru"

QUERIES = ["CTO", "технический директор", "IT директор", "AI"]


@retry()
def fetch(params: dict) -> list[dict]:
    query = params.get("q", "") if isinstance(params, dict) else str(params)
    url = f"https://www.fl.ru/projects/?keywords={urllib.parse.quote(query)}"
    try:
        s = get_session(extra_headers={"User-Agent": random.choice(HH_UAS), "Accept-Language": "ru-RU,ru;q=0.9"})
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []
    jobs = []
    for item in soup.select('[class*="project"]'):
        title_el = item.select_one("a") if hasattr(item, "select_one") else None
        if not title_el:
            continue
        name = title_el.get_text(strip=True) if hasattr(title_el, "get_text") else ""
        if not name or len(name) < 5:
            continue
        href = title_el.get("href", "") if hasattr(title_el, "get") else ""
        jobs.append({
            "id": f"fl-{abs(hash(query + name)) % 10**8}",
            "name": name,
            "source": NAME,
            "alternate_url": "https://www.fl.ru" + href if href.startswith("/") else href,
            "_work_format": "project",
        })
    return jobs
```

- [ ] **Step 2f: Create `sources/freelanceru.py`**

```python
# sources/freelanceru.py
import random, urllib.parse
from bs4 import BeautifulSoup
from .base import get_session, retry, HH_UAS

NAME = "freelance_ru"

QUERIES = ["CTO", "IT", "разработка"]


@retry()
def fetch(params: dict) -> list[dict]:
    query = params.get("q", "") if isinstance(params, dict) else str(params)
    url = f"https://freelance.ru/projects/?q={urllib.parse.quote(query)}"
    try:
        s = get_session(extra_headers={"User-Agent": random.choice(HH_UAS), "Accept-Language": "ru-RU,ru;q=0.9"})
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []
    jobs = []
    for item in soup.select('[class*="project"]'):
        title_el = item.select_one("a")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name or len(name) < 5:
            continue
        href = title_el.get("href", "")
        jobs.append({
            "id": f"fr-{abs(hash(query + name)) % 10**8}",
            "name": name,
            "source": NAME,
            "alternate_url": "https://freelance.ru" + href if href.startswith("/") else href,
            "_work_format": "project",
        })
    return jobs
```

Each `fetch(params)` unpacks its needed key from `params` (e.g., `q = params.get("q", "")` for text queries, `channel = params.get("channel", "")` for telegram).

- [ ] **Step 3: Wire `sources/__init__.py`**

```python
# sources/__init__.py
from .base import Source
from . import (
    hh, linkedin, trudvsem, habr, superjob, telegram,
    flru, freelanceru, remoteok, wwr, jobicy, hn_hiring,
)

SOURCE_REGISTRY: list[Source] = [
    Source(name=hh.NAME,           queries=[{"q": q} for q in hh.QUERIES],         fetch=hh.fetch,          sleep=2.0,  use_proxy=True),
    Source(name=linkedin.NAME,     queries=linkedin.QUERIES,                        fetch=linkedin.fetch,    sleep=2.0,  use_proxy=True),
    Source(name=trudvsem.NAME,     queries=trudvsem.QUERIES,                        fetch=trudvsem.fetch,    sleep=0.3,  use_proxy=True),
    Source(name=habr.NAME,         queries=habr.QUERIES,                            fetch=habr.fetch,        sleep=1.0,  use_proxy=True),
    Source(name=superjob.NAME,     queries=superjob.QUERIES,                        fetch=superjob.fetch,    sleep=1.0,  use_proxy=True),
    Source(name=telegram.NAME,     queries=[{"channel": c} for c in telegram.CHANNELS], fetch=telegram.fetch, sleep=1.5, use_proxy=True),
    Source(name=flru.NAME,         queries=[{"q": q} for q in flru.QUERIES],        fetch=flru.fetch,        sleep=1.0,  use_proxy=True),
    Source(name=freelanceru.NAME,  queries=[{"q": q} for q in freelanceru.QUERIES], fetch=freelanceru.fetch, sleep=1.0,  use_proxy=True),
    Source(name=remoteok.NAME,     queries=remoteok.QUERIES,                        fetch=remoteok.fetch,    sleep=1.5,  use_proxy=False),
    Source(name=wwr.NAME,          queries=wwr.QUERIES,                             fetch=wwr.fetch,         sleep=2.0,  use_proxy=False),
    Source(name=jobicy.NAME,       queries=jobicy.QUERIES,                          fetch=jobicy.fetch,      sleep=1.0,  use_proxy=False),
    Source(name=hn_hiring.NAME,    queries=hn_hiring.QUERIES,                       fetch=hn_hiring.fetch,   sleep=0.5,  use_proxy=True),
]
```

- [ ] **Step 4: Write registry test**

```python
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
```

- [ ] **Step 5: Run all source tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/test_registry.py tests/sources/ tests/test_base.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd ~/workspaces/jobsearch
git add sources/ tests/test_registry.py
git commit -m "feat(jobsearch): migrate all sources to sources/ package + wire SOURCE_REGISTRY"
```

---

## Task 8: Refactor scan_v4.py main()

**Files:**
- Modify: `scan_v4.py` (main function + load_seen/save_seen + imports)

Replace the 8 hand-coded source blocks (lines 974-1124) with a SOURCE_REGISTRY loop. Add title_hash dedup. Migrate seen-jobs.json schema to include `title_hashes`. Apply `score_vacancy_foreign_delta` (will be added in Task 9).

- [ ] **Step 1: Update `load_seen()` at line 107 to handle title_hashes migration**

Replace:
```python
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {"last_scan": None, "seen": []}
```

With:
```python
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}
        if "title_hashes" not in data:
            data["title_hashes"] = []
        return data
    return {"last_scan": None, "seen": [], "title_hashes": []}
```

- [ ] **Step 2: Add import of SOURCE_REGISTRY at top of scan_v4.py**

After existing imports add:
```python
from sources import SOURCE_REGISTRY
from sources.base import title_hash as _title_hash
from sources.hh import clean_hh_url as _clean_hh_url
```

- [ ] **Step 3: Replace lines 974-1124 (the 8 source blocks) with the registry loop**

Replace the entire block from `# --- 1. HH.ru ---` through `print(f"  → Итого: +{fr_count}")` with:

```python
    # ── Source loop ──────────────────────────────────────────────────
    title_hashes: set[str] = set(seen_data.get("title_hashes", []))

    for src in SOURCE_REGISTRY:
        print(f"\n[{src.name}]")
        src_count = 0
        for params in src.queries:
            label = str(params)[:40]
            print(f"  → {label}...", end=" ", flush=True)
            items = src.fetch(params)
            added = 0
            for job in items:
                jid = f"{src.name}-{job.get('id', '')}"
                th = _title_hash(job)
                if jid in all_jobs or th in title_hashes:
                    continue
                all_jobs[jid] = job
                title_hashes.add(th)
                src_count += 1
                added += 1
            stats["queries"] += 1
            print(f"+{added}")
            time.sleep(src.sleep)
        if src_count > 0:
            stats["active_sources"] += 1
        print(f"  → Итого: +{src_count}")
```

- [ ] **Step 4: Update seen_data save at line ~1152 to persist title_hashes**

Replace:
```python
        new_ids = [jid for jid, _ in new_jobs]
        seen_data["seen"] = list(seen_ids | set(new_ids))
        seen_data["last_scan"] = today
        save_seen(seen_data)
```

With:
```python
        new_ids = [jid for jid, _ in new_jobs]
        seen_data["seen"] = list(seen_ids | set(new_ids))
        seen_data["last_scan"] = today
        # Persist title_hashes (keep newest 5000)
        seen_data["title_hashes"] = list(title_hashes)[-5000:]
        save_seen(seen_data)
```

- [ ] **Step 5: Smoke test that scan still runs (dry-run)**

```bash
cd ~/workspaces/jobsearch
python3 scan_v4.py --dry-run 2>&1 | head -50
```

Expected: `[hh]`, `[linkedin]`, ... sources listed, no ImportError, exits cleanly.

- [ ] **Step 6: Commit**

```bash
cd ~/workspaces/jobsearch
git add scan_v4.py
git commit -m "refactor(jobsearch): replace hand-coded source blocks with SOURCE_REGISTRY loop"
```

---

## Task 9: Categorization, scoring delta, report sections

**Files:**
- Modify: `scan_v4.py` (classify_section, score_vacancy_foreign_delta, build_template_report, apply_source_cap)

- [ ] **Step 1: Add constants near the EXEC_ROLES block (after line 694)**

```python
# Foreign source routing constants
FOREIGN_REMOTE_SOURCES = {"remoteok", "wwr", "jobicy", "hn_hiring"}
EU_KEYWORDS = {"germany", "netherlands", "france", "portugal", "spain", "poland",
               "czech", "austria", "sweden", "denmark", "finland", "norway",
               "europe", "eu", "european"}
US_KEYWORDS = {"united states", "usa", "u.s.", "new york", "san francisco", "seattle",
               "austin", "boston", "chicago", "los angeles", "california"}
RU_KEYWORDS = {"russia", "москва", "moscow", "санкт", "спб", "казан", "новосибир",
               "россия", "екатеринб"}
```

- [ ] **Step 2: Add `score_vacancy_foreign_delta()` after the existing `score_vacancy()` function (after line 768)**

```python
_VISA_RE = re.compile(r"(?i)(visa spon|relocation|h1b|blue card|work permit|visa support)")
_CLEVEL_EXACT_RE = re.compile(
    r"(?i)(CTO|Chief Technology Officer|VP Engineering|VP of Engineering|Head of Engineering)"
)
_DISQUALIFY_RE = re.compile(
    r"(?i)(us citizen|security clearance|must be authorized|only authorized to work)"
)

FOREIGN_SCORED_SOURCES = {"remoteok", "wwr", "jobicy", "hn_hiring", "linkedin"}


def score_vacancy_foreign_delta(job: dict) -> int:
    if job.get("source") not in FOREIGN_SCORED_SOURCES:
        return 0
    delta = 0
    name = (job.get("name") or "").lower()
    desc = ((job.get("snippet") or {}).get("description") or "").lower()
    full = name + " " + desc
    if _CLEVEL_EXACT_RE.search(full):
        delta += 15
    if _VISA_RE.search(full):
        delta += 10
    if _DISQUALIFY_RE.search(full):
        delta -= 20
    return delta
```

- [ ] **Step 3: Extend `classify_section()` (replace function body at line 847)**

```python
def classify_section(job):
    source = job.get("source", "")

    if source in FOREIGN_REMOTE_SOURCES:
        return "foreign_remote"

    if source == "linkedin":
        area = (job.get("area") or {}).get("name", "").lower()
        if any(k in area for k in RU_KEYWORDS):
            if job.get("remote_flag") or any(w in area for w in ["remote", "удален"]):
                return "remote"
            return "office"
        if any(k in area for k in US_KEYWORDS):
            return "relocation_us"
        return "relocation_eu"

    if job.get("_work_format") == "project":
        return "project"
    name = (job.get("name") or "").lower()
    snippet = (job.get("snippet") or {}).get("requirement", "").lower()
    text = name + " " + snippet
    remote_words = ["remote", "удален", "дистанц", "online", "полностью удал"]
    if any(w in text for w in remote_words):
        return "remote"
    hybrid_words = ["гибрид", "hybrid", "частично удал", "смешан"]
    if any(w in text for w in hybrid_words):
        return "hybrid"
    area_name = (job.get("area") or {}).get("name", "").lower()
    if any(w in area_name for w in ["remote", "удален", "дистанц"]):
        return "remote"
    return "office"
```

- [ ] **Step 4: Add `apply_source_cap()` helper before `build_template_report()`**

```python
def apply_source_cap(jobs_scored: list, cap: int = 5) -> list:
    from collections import defaultdict
    counts: dict = defaultdict(int)
    result = []
    for score, job in sorted(jobs_scored, key=lambda x: -x[0]):
        src = job.get("source", "")
        if counts[src] < cap:
            result.append((score, job))
            counts[src] += 1
    return result
```

- [ ] **Step 5: Update `build_template_report()` to use capped sections + new section headers**

In `build_template_report()` (line 865):

Replace the `sections` dict initialisation:
```python
    sections = {"remote": [], "hybrid": [], "office": [], "project": []}
```

With:
```python
    sections = {
        "remote": [], "hybrid": [], "office": [], "project": [],
        "foreign_remote": [], "relocation_us": [], "relocation_eu": [],
    }
```

After the per-section sort block (after line 876), add relocation merge:
```python
    # Merge US + EU into combined relocation section (with region flag)
    sections["relocation"] = (
        [(s, dict(job, _region_flag="🇺🇸")) for s, job in sections.pop("relocation_us", [])]
        + [(s, dict(job, _region_flag="🇪🇺")) for s, job in sections.pop("relocation_eu", [])]
    )
    sections["relocation"].sort(key=lambda x: -x[0])
```

Replace `section_config` (line 890):
```python
    section_config = [
        ("remote",         "🖥  **УДАЛЁНКА**"),
        ("hybrid",         "🏙  **ГИБРИД**"),
        ("office",         "🏢  **ОФИС**"),
        ("foreign_remote", "🌐  **ЗАРУБЕЖНАЯ УДАЛЁНКА**"),
        ("relocation",     "✈️  **РЕЛОКАЦИЯ**"),
        ("project",        "⚡  **ПРОЕКТЫ / ФРИЛАНС**"),
    ]
```

Replace the inner render loop (lines 903-941) to use `apply_source_cap` and increase cap to 8 per section + add region flag:

```python
        capped = apply_source_cap(sec_jobs, cap=5)
        count = 0
        for score, job in capped[:8]:
            count += 1
            region_flag = job.get("_region_flag", "")
            icon = "🔥" if score > 60 else "📌"
            emp = (job.get("employer") or {}).get("name", "N/A")
            name = job.get("name", "")
            url = job.get("alternate_url") or ""
            area = (job.get("area") or {}).get("name", "")
            salary = format_salary(job)
            req = (job.get("snippet") or {}).get(
                "requirement", (job.get("snippet") or {}).get("description", "")
            )[:120]
            req = re.sub(r"<[^>]+>", "", req).strip()
            source = job.get("source", "web")
            emp_type = "проект" if sec_key == "project" else "постоянная"
            loc_icon = "🌍 Remote" if sec_key in ("remote", "foreign_remote") else f"📍 {area}" if area else "📍 —"

            lines.append(f"{icon} **{name}** · {score}/100 · {emp_type}")
            lines.append(f"🏢 {region_flag} {emp}".strip() if region_flag else f"🏢 {emp}")
            lines.append(f"💰 {salary} · {loc_icon}")
            lines.append(f"📋 {req[:100]}" if req else "")
            lines.append(f"🔗 {url}")
            lines.append("")
```

- [ ] **Step 6: Apply scoring delta in main() scoring step**

Find the scoring line in main() (~line 1134 after refactor):
```python
    scored = [(score_vacancy(job), job) for _, job in new_jobs]
```

Replace with:
```python
    scored = [
        (min(100, max(0, score_vacancy(job) + score_vacancy_foreign_delta(job))), job)
        for _, job in new_jobs
    ]
```

- [ ] **Step 7: Smoke test new sections**

```bash
cd ~/workspaces/jobsearch
python3 scan_v4.py --dry-run 2>&1 | grep -E "ЗАРУБЕЖНАЯ|РЕЛОКАЦИЯ|УДАЛЁНКА|ГИБРИД|ОФИС"
```

Expected: all 6 section headers printed (even if some are empty in dry-run)

- [ ] **Step 8: Commit**

```bash
cd ~/workspaces/jobsearch
git add scan_v4.py
git commit -m "feat(jobsearch): add ЗАРУБЕЖНАЯ УДАЛЁНКА + РЕЛОКАЦИЯ sections, scoring delta, source cap"
```

---

## Task 10: Tests for categorization, scoring delta, and cap

**Files:**
- Create: `tests/test_categorization.py`
- Create: `tests/test_scoring_delta.py`
- Create: `tests/test_cap.py`

- [ ] **Step 1: Write `tests/test_categorization.py`**

```python
# tests/test_categorization.py
import sys, os
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


def test_linkedin_eu_is_relocation_eu():
    job = {"source": "linkedin", "area": {"name": "Germany"}}
    assert classify_section(job) == "relocation_eu"


def test_linkedin_russia_remote_flag():
    job = {"source": "linkedin", "area": {"name": "Moscow, Russia"}, "remote_flag": True}
    assert classify_section(job) == "remote"


def test_linkedin_russia_no_remote_flag():
    job = {"source": "linkedin", "area": {"name": "Москва"}, "remote_flag": False}
    assert classify_section(job) == "office"


def test_hh_remote_text():
    job = {"source": "hh", "name": "CTO удалённо"}
    assert classify_section(job) == "remote"


def test_hh_hybrid():
    job = {"source": "hh", "name": "CTO гибрид"}
    assert classify_section(job) == "hybrid"


def test_fl_ru_project():
    job = {"source": "fl_ru", "_work_format": "project"}
    assert classify_section(job) == "project"
```

- [ ] **Step 2: Write `tests/test_scoring_delta.py`**

```python
# tests/test_scoring_delta.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scan_v4 import score_vacancy_foreign_delta


def test_clevel_title_gives_plus15():
    job = {"source": "remoteok", "name": "Chief Technology Officer"}
    assert score_vacancy_foreign_delta(job) == 15


def test_vp_engineering_gives_plus15():
    job = {"source": "linkedin", "name": "VP Engineering", "area": {"name": "Germany"}}
    assert score_vacancy_foreign_delta(job) == 15


def test_visa_sponsor_in_desc_gives_plus10():
    job = {
        "source": "jobicy",
        "name": "Senior Director of Engineering",
        "snippet": {"description": "We offer visa sponsorship for qualified candidates."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta >= 10


def test_us_citizen_required_gives_minus20():
    job = {
        "source": "wwr",
        "name": "Head of Engineering",
        "snippet": {"description": "Must be US citizen or permanent resident."},
    }
    delta = score_vacancy_foreign_delta(job)
    assert delta <= -5


def test_russian_source_no_delta():
    job = {"source": "hh", "name": "CTO"}
    assert score_vacancy_foreign_delta(job) == 0


def test_telegram_source_no_delta():
    job = {"source": "telegram", "name": "Chief Technology Officer"}
    assert score_vacancy_foreign_delta(job) == 0
```

- [ ] **Step 3: Write `tests/test_cap.py`**

```python
# tests/test_cap.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scan_v4 import apply_source_cap


def _make_jobs(source, count, base_score=50):
    return [(base_score - i, {"source": source, "name": f"Job {i}"}) for i in range(count)]


def test_cap_limits_per_source():
    jobs = _make_jobs("remoteok", 8)
    result = apply_source_cap(jobs, cap=5)
    remoteok_count = sum(1 for _, j in result if j["source"] == "remoteok")
    assert remoteok_count == 5


def test_cap_keeps_highest_score():
    jobs = [(10, {"source": "remoteok", "name": "Low"}),
            (90, {"source": "remoteok", "name": "High"}),
            (50, {"source": "remoteok", "name": "Mid"})]
    result = apply_source_cap(jobs, cap=2)
    names = [j["name"] for _, j in result]
    assert "High" in names
    assert "Mid" in names
    assert "Low" not in names


def test_cap_does_not_affect_different_sources():
    jobs = _make_jobs("remoteok", 3) + _make_jobs("linkedin", 3)
    result = apply_source_cap(jobs, cap=5)
    assert len(result) == 6  # all through, none exceed cap


def test_cap_empty_input():
    assert apply_source_cap([], cap=5) == []
```

- [ ] **Step 4: Run all new tests**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/test_categorization.py tests/test_scoring_delta.py tests/test_cap.py -v
```

Expected: all PASS

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
cd ~/workspaces/jobsearch
python3 -m pytest tests/ -v --ignore=tests/sources 2>&1 | tail -20
```

Expected: all PASS (existing test_scanner.py tests still import from old `scan` module — unaffected)

- [ ] **Step 6: Commit**

```bash
cd ~/workspaces/jobsearch
git add tests/test_categorization.py tests/test_scoring_delta.py tests/test_cap.py
git commit -m "test(jobsearch): categorization, scoring delta, source cap tests"
```

---

## Task 11: Update career-bot scanner

**Files:**
- Modify: `~/workspaces/career-bot/scanner.py` (`_derive_source`)

`parse_report_text()` splits by `(?:🔥|📌)\s+\*\*` — unaffected by new section headers. But `_derive_source()` currently returns `"other"` for foreign sources. Add URL and source patterns.

- [ ] **Step 1: Update `_derive_source` in career-bot/scanner.py**

Replace (lines 9-22):
```python
def _derive_source(url: str, company: str) -> str:
    if "hh.ru" in url:
        return "hh"
    if "habr" in url:
        return "habr"
    if "getmatch" in url:
        return "getmatch"
    if "superjob" in url:
        return "superjob"
    if company.startswith("@"):
        return "telegram"
    if "@" in company:
        return "email"
    return "other"
```

With:
```python
def _derive_source(url: str, company: str) -> str:
    if "hh.ru" in url:
        return "hh"
    if "habr" in url:
        return "habr"
    if "getmatch" in url:
        return "getmatch"
    if "superjob" in url:
        return "superjob"
    if "linkedin.com" in url:
        return "linkedin"
    if "remoteok.com" in url:
        return "remoteok"
    if "weworkremotely.com" in url:
        return "wwr"
    if "jobicy.com" in url:
        return "jobicy"
    if "ycombinator.com" in url:
        return "hn_hiring"
    if company.startswith("@"):
        return "telegram"
    if "@" in company:
        return "email"
    return "other"
```

- [ ] **Step 2: Verify career-bot parser handles new section headers**

```bash
cd ~/workspaces/career-bot
python3 -c "
import scanner
# simulate a report with new sections
report = '''📊 **JOB DIGEST** · 2026-05-28
━━━━━━━━━━━━━━━━━━━━━━
Источников: 7 · Новых: 50 · В отчёте: 12
━━━━━━━━━━━━━━━━━━━━━━

🌐  **ЗАРУБЕЖНАЯ УДАЛЁНКА**

🔥 **VP Engineering** · 75/100 · постоянная
🏢 RemoteCorp
💰 не указана · 🌍 Remote
🔗 https://remoteok.com/jobs/123

✈️  **РЕЛОКАЦИЯ**

📌 **CTO** · 60/100 · постоянная
🏢 🇩🇪 GmbH Berlin
💰 не указана · 📍 Germany
🔗 https://linkedin.com/jobs/view/456
'''
jobs = scanner.parse_report_text(report)
print(f'Parsed {len(jobs)} jobs from report with new sections')
assert len(jobs) == 2, f'Expected 2, got {len(jobs)}'
print('career-bot parser: OK')
"
```

Expected: `Parsed 2 jobs from report with new sections` + `career-bot parser: OK`

- [ ] **Step 3: Commit**

```bash
cd ~/workspaces/career-bot
git add scanner.py
git commit -m "feat(career-bot): recognize foreign job source URLs in _derive_source"
```

---

## Task 12: E2E smoke

- [ ] **Step 1: Per-source isolation smoke**

```bash
cd ~/workspaces/jobsearch
python3 -c "from sources import linkedin; from sources.base import get_session; print(len(linkedin.fetch(linkedin.QUERIES[0])))"
```

Expected: integer >= 0 (network-dependent; 0 if proxy down, not a crash)

```bash
python3 -c "from sources import remoteok; print(len(remoteok.fetch(remoteok.QUERIES[0])))"
```

Expected: integer, no crash

```bash
python3 -c "from sources import wwr; print(len(wwr.fetch({})))"
```

Expected: integer, no crash

```bash
python3 -c "from sources import jobicy; print(len(jobicy.fetch(jobicy.QUERIES[0])))"
```

Expected: integer >= 1

```bash
python3 -c "from sources import hn_hiring; hn_hiring._thread_id_cache.clear(); print(len(hn_hiring.fetch({'query':'CTO'})))"
```

Expected: integer >= 1

- [ ] **Step 2: Full scan dry-run**

```bash
cd ~/workspaces/jobsearch
bash run_scan.sh --dry-run 2>&1 | tee /tmp/scan_dryrun.log
grep -E "^\[" /tmp/scan_dryrun.log
```

Expected: 12 source names printed, no Python tracebacks

- [ ] **Step 3: Full scan real run**

```bash
cd ~/workspaces/jobsearch
bash run_scan.sh 2>&1 | tee /tmp/scan_full.log
grep -E "LinkedIn|remoteok|wwr|jobicy|hn_hiring" /tmp/scan_full.log
ls -t reports/ | head -1
```

Expected: LinkedIn shows `+N>0`, new sources show results, fresh report written.

- [ ] **Step 4: Verify new sections in report**

```bash
grep -E "ЗАРУБЕЖНАЯ|РЕЛОКАЦИЯ" reports/$(date +%Y-%m-%d).md
```

Expected: at least one of the new section headers present in today's report.

- [ ] **Step 5: Verify career-bot can parse the new report**

```bash
cd ~/workspaces/career-bot
python3 -c "
import scanner
count = scanner.import_latest_report()
print(f'Imported {count} new jobs from latest report')
"
```

Expected: integer >= 0, no crash.

- [ ] **Step 6: Final commit and cleanup**

```bash
cd ~/workspaces/jobsearch
# Remove stale hand-coded fetchers from scan_v4.py only if SOURCE_REGISTRY is fully working
# (keep scan_v4.py fetch functions as dead code for now — safe fallback, not exported)
git add -A
git status
```

Verify only expected files changed (no accidental stray files). Then:

```bash
git commit -m "feat(jobsearch): foreign sources Phase 1 complete — LinkedIn fix + RemoteOK + WWR + Jobicy + HN"
```

---

## Notes

**Remotive is blocked (403) from this server** — replaced by Jobicy. If Remotive access improves, add `sources/remotive.py` using endpoint `https://remotive.com/api/remote-jobs?category=software-dev&search=CTO` with the same pattern as jobicy.py.

**WWR `/categories/remote-management-jobs.rss` returns 301 forever** — use `/remote-jobs.rss` (full feed, filter by title).

**RemoteOK blocks browser UA through Lineman** — use `User-Agent: curl/7.88.1` + `Accept: application/json` + `use_proxy=False`.

**test_scanner.py still imports from `scan` (v3)** — untouched, these tests remain green.

**seen-jobs.json migration** — backward-compatible: `title_hashes` key added on first load if missing. No data loss.
