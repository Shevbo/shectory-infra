# Jobsearch — Foreign Sources (Phase 1) Design

**Date:** 2026-05-28
**Author:** Claude (Executive Advisor) + Boris
**Project:** `~/workspaces/jobsearch`
**Status:** Approved for implementation

## Problem

`jobsearch` scanner currently pulls from 5 sources: HH, TrudVsem, Habr, SuperJob, Telegram channels. LinkedIn is wired in `scan_v4.py` but silently returns 0 — the parser regex `job-result-card` matches a deprecated CSS class; the current LinkedIn Guest API response uses `base-card`/`base-search-card`/`job-search-card`. No other foreign sources exist. Boris (CTO) needs:

- Remote-friendly positions for residents of RU
- C-level + Director positions with visa sponsorship in EU/UK/US

## Scope

**Phase 1 (this spec):**
1. Refactor monolithic `scan_v4.py` (1100+ lines) into a `sources/` package with one module per source.
2. Fix LinkedIn parser (selector + add EU/US locations + remote-flag).
3. Add 4 new foreign sources (RemoteOK, Remotive, We Work Remotely, HN Who's Hiring).
4. Introduce two new digest categories: «ЗАРУБЕЖНАЯ УДАЛЁНКА» and «РЕЛОКАЦИЯ EU/US».
5. Scoring boost/penalty for C-level markers, visa sponsorship, US-citizen-only.
6. Per-source cap in digest (≤5 entries per source per category).
7. Title+company dedup across sources.
8. Tests (unit + categorization + scoring + regression for LinkedIn layout).

**Phase 2 (separate spec, later):** Indeed (HTML, high CAPTCHA risk).

**Out of scope:** Wellfound, Otta, Glassdoor, Indeed.

## Architecture

### Directory layout

```
~/workspaces/jobsearch/
  scan_v4.py              # Orchestrator: iterates SOURCE_REGISTRY, dedups, categorizes, writes report
  sources/
    __init__.py           # SOURCE_REGISTRY list of Source dataclasses
    base.py               # Source dataclass, retry decorator, get_session(), common types
    hh.py                 # Existing fetch_hh_web + HH_QUERIES, moved out of scan_v4.py
    linkedin.py           # FIXED parser, expanded queries (RU/EU/US × remote-flag)
    trudvsem.py           # Existing, moved
    habr.py               # Existing, moved
    superjob.py           # Existing, moved
    telegram.py           # Existing, moved
    remoteok.py           # NEW — JSON API
    remotive.py           # NEW — JSON API
    wwr.py                # NEW — RSS
    hn_hiring.py          # NEW — Algolia API
  reports/                # Unchanged
  seen-jobs.json          # Schema extended with title_hashes
  run_scan.sh             # Unchanged
  tests/
    test_scanner.py       # Existing
    sources/
      test_linkedin.py    # NEW
      test_remoteok.py    # NEW
      test_remotive.py    # NEW
      test_wwr.py         # NEW
      test_hn_hiring.py   # NEW
    fixtures/
      linkedin_response.html   # Real captured response (~6KB)
      remoteok_response.json
      remotive_response.json
      wwr_response.xml
      hn_response.json
    test_categorization.py    # NEW
    test_scoring.py           # NEW
  docs/superpowers/specs/
    2026-05-28-foreign-sources-design.md   # this file
```

### Source contract

Each `sources/<name>.py` exports:

```python
NAME: str                 # short identifier, used in dedup key and category routing
QUERIES: list[dict]       # parameter dicts passed to fetch()
def fetch(params: dict) -> list[dict]:
    """Return list of job dicts. Must not raise — catch all and return []."""
```

Job dict shape (lowest-common-denominator):
```python
{
    "id": str,                    # source-local id
    "source": str,                # NAME
    "name": str,                  # title
    "employer": {"name": str},
    "area": {"name": str},
    "alternate_url": str,
    "snippet": {"description": str},  # optional, used by scoring
    "remote_flag": bool,          # optional, true if source guarantees remote
}
```

### Orchestrator (`scan_v4.py`)

```python
from sources import SOURCE_REGISTRY
all_jobs: dict[str, dict] = {}     # key = f"{NAME}-{id}"
title_hashes: set[str] = set()      # cross-source title+company dedup

for src in SOURCE_REGISTRY:
    src_count = 0
    for params in src.QUERIES:
        items = src.fetch(params)
        for job in items:
            key = f"{src.NAME}-{job['id']}"
            th = title_hash(job)
            if key in all_jobs or th in title_hashes:
                continue
            all_jobs[key] = job
            title_hashes.add(th)
            src_count += 1
        stats["queries"] += 1
        time.sleep(src.SLEEP)
    if src_count > 0:
        stats["active_sources"] += 1

# Categorize, score, cap-per-source, render report (existing logic, parameterized)
```

## Source details (Phase 1)

### LinkedIn (FIX)

- **File:** `sources/linkedin.py`
- **Endpoint:** `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`
- **Parser change:** find `<li>` blocks containing `data-entity-urn="urn:li:jobPosting:<id>"`. Drop reliance on `job-result-card` class. Within each `<li>`, extract:
  - id: `data-entity-urn` regex
  - title: `<span class="*screen-reader-text*">...</span>` or `<h3>` fallback
  - company: `class="*base-search-card__subtitle*"` (current class) with fallback to `job-search-card__company-name`
  - location: `class="*job-search-card__location*"`
  - url: `href="...job/view/<id>..."`
- **Queries:**
  ```python
  QUERIES = [
      # Russia, remote
      {"keywords": "CTO", "location": "Russia", "f_E": "5,6", "f_WT": "2"},
      {"keywords": "Head of Engineering", "location": "Russia", "f_E": "5", "f_WT": "2"},
      # EU
      {"keywords": "CTO", "location": "European Union", "f_E": "5,6"},
      {"keywords": "VP Engineering", "location": "European Union", "f_E": "5"},
      # US
      {"keywords": "Chief Technology Officer", "location": "United States", "f_E": "5,6"},
      {"keywords": "Director of Engineering", "location": "United States", "f_E": "5"},
  ]
  ```
- **Sleep:** 2.0s between queries.
- **All via `get_session()` (Lineman proxy).**

### RemoteOK

- **File:** `sources/remoteok.py`
- **Endpoint:** `https://remoteok.com/api?tags=<tag>` returns JSON array; first element is metadata, rest are jobs.
- **Queries:** `[{"tags": "exec"}, {"tags": "management"}]`
- **Filter:** keep job only if `position` matches regex `(?i)(CTO|CIO|Chief|Head of|VP|Director)`.
- **Mapping:**
  ```python
  {
      "id": str(j["id"]),
      "source": "remoteok",
      "name": j["position"],
      "employer": {"name": j["company"]},
      "area": {"name": j.get("location") or "Remote"},
      "alternate_url": j["url"],
      "snippet": {"description": j.get("description", "")[:500]},
      "remote_flag": True,
  }
  ```
- **Sleep:** 1.0s.

### Remotive

- **File:** `sources/remotive.py`
- **Endpoint:** `https://remotive.com/api/remote-jobs?category=software-dev&search=<term>` returns `{"jobs": [...]}`.
- **Queries:** `[{"search": "CTO"}, {"search": "Head of Engineering"}, {"search": "VP Engineering"}, {"search": "Director of Engineering"}]`
- **Mapping:** `id=str(j["id"])`, `name=j["title"]`, `employer.name=j["company_name"]`, `area.name=j["candidate_required_location"]`, `url=j["url"]`, `description=j.get("description","")[:500]`, `remote_flag=True`.
- **Sleep:** 1.0s.

### We Work Remotely (WWR)

- **File:** `sources/wwr.py`
- **Endpoint:** `https://weworkremotely.com/categories/remote-management-jobs.rss` — single XML feed.
- **Queries:** `[{}]` (one fetch).
- **Parse:** `xml.etree.ElementTree`, iterate `channel/item`, extract `guid`, `title`, `description`, `link`. Split title by `: ` → `company, position`.
- **Filter:** keep only if position matches the same C-level regex as RemoteOK.
- **Sleep:** N/A (single fetch).

### HN Who's Hiring

- **File:** `sources/hn_hiring.py`
- **Endpoint 1:** `https://hn.algolia.com/api/v1/search?tags=story,author_whoishiring` → take newest `objectID` as `thread_id`.
- **Endpoint 2:** `https://hn.algolia.com/api/v1/search?tags=comment,story_<thread_id>&query=<keyword>&hitsPerPage=50` per keyword.
- **Queries:** `[{"query": "CTO"}, {"query": "Head of Engineering"}, {"query": "VP Engineering"}, {"query": "Director of Engineering"}]`
- **Mapping per comment:**
  ```python
  text = strip_html(hit["comment_text"])
  {
      "id": hit["objectID"],
      "source": "hn_hiring",
      "name": text[:80].strip(),
      "employer": {"name": parse_company(text)},   # heuristic: first | -split token before "is hiring"
      "area": {"name": parse_location(text)},      # regex (REMOTE|Remote|<City>)
      "alternate_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
      "snippet": {"description": text[:500]},
  }
  ```
- **Sleep:** 0.5s.

## Categorization

Routing table (applied after fetch, before scoring):

| Condition | Category |
|---|---|
| `source == "hh"`, `area` matches RU and remote tag | УДАЛЁНКА |
| `source == "hh"`, hybrid | ГИБРИД |
| `source == "hh"`, office | ОФИС |
| `source == "habr"` | same as HH by area |
| `source == "superjob"` | same as HH by area |
| `source == "trudvsem"` | ОФИС by default |
| `source == "telegram"` | УДАЛЁНКА (existing default) |
| `source == "linkedin"`, `area` contains "Russia/Moscow/Россия" | RU bucket (УДАЛЁНКА if `f_WT=2`, else ОФИС) |
| `source == "linkedin"`, `area` contains "United States/USA/US" | РЕЛОКАЦИЯ (subregion=US) |
| `source == "linkedin"`, `area` other foreign | РЕЛОКАЦИЯ (subregion=EU) |
| `source in {remoteok, remotive, wwr, hn_hiring}` | ЗАРУБЕЖНАЯ УДАЛЁНКА |

Two new sections in the rendered report: «ЗАРУБЕЖНАЯ УДАЛЁНКА» and a single «РЕЛОКАЦИЯ» section that combines US and EU entries; each item is prefixed with `🇺🇸` or `🇪🇺` based on `subregion`. Internally `subregion` is a per-job field, not a separate category.

## Scoring deltas (additive to existing score)

| Trigger (case-insensitive substring in `name + description`) | Delta |
|---|---|
| `CTO` or `Chief Technology Officer` or `VP Engineering` or `Head of Engineering` | +15 |
| `visa sponsor`, `relocation`, `H1B`, `Blue Card` | +10 |
| `US citizen`, `Security Clearance`, `Must be authorized to work in the US` | -20 |
| `Onsite <city> only` where remote_flag is False | -15 |

Applied only to foreign sources (LinkedIn + remote-API quartet). Russian-source scoring unchanged.

## Per-source cap & cross-source dedup

- **Cap:** after categorization+scoring, when rendering each report section, keep at most 5 entries per `source` per section. Sort by score desc, then by recency.
- **Dedup:** `title_hash(job) = sha1(normalize(name) + "|" + normalize(employer.name))[:12]`, where `normalize = lower + strip whitespace + remove punctuation`. Maintained in `seen-jobs.json` under new key `title_hashes` (list, capped at 5000 most-recent entries — FIFO).

## seen-jobs.json schema change

Current: `{"<source>-<id>": {...metadata}}`
New: `{"jobs": {<existing>}, "title_hashes": [...]}` — wrap existing dict for backward compat, migrate on first read if old shape detected.

## Testing strategy

### Unit per source (5 files under `tests/sources/`)

For each: load fixture, call `fetch()` against monkey-patched HTTP layer, assert ≥1 job, assert required fields present, assert empty-response handled.

### Regression

`test_linkedin.py::test_new_layout_returns_six_jobs` — fixture is the 6339-byte response captured 2026-05-28 from `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=CTO&location=Russia&start=0`. Parser must return 6 jobs.

### Categorization

`tests/test_categorization.py`:
- LinkedIn + `area="United States"` → "РЕЛОКАЦИЯ US"
- LinkedIn + `area="Москва"` + `remote_flag=True` → "УДАЛЁНКА"
- RemoteOK any → "ЗАРУБЕЖНАЯ УДАЛЁНКА"
- HH + remote → "УДАЛЁНКА" (existing behavior preserved)

### Scoring

`tests/test_scoring.py`:
- name `"Chief Technology Officer"` source=remoteok → +15
- description contains `"visa sponsorship offered"` → +10
- description contains `"US citizen required"` → -20
- Russian HH job → no foreign deltas

### Registry

`tests/test_registry.py`:
- `len(SOURCE_REGISTRY) == 10`
- Each entry has `NAME`, `QUERIES`, callable `fetch`

### Cap

`tests/test_cap.py`: feed 8 jobs from same source same category → render keeps top-5 by score.

## Manual smoke procedure

```bash
cd ~/workspaces/jobsearch
# 1. Per-source isolation
python3 -c "from sources import linkedin; print(len(linkedin.fetch(linkedin.QUERIES[0])))"
python3 -c "from sources import remoteok; print(len(remoteok.fetch(remoteok.QUERIES[0])))"
python3 -c "from sources import remotive; print(len(remotive.fetch(remotive.QUERIES[0])))"
python3 -c "from sources import wwr; print(len(wwr.fetch(wwr.QUERIES[0])))"
python3 -c "from sources import hn_hiring; print(len(hn_hiring.fetch(hn_hiring.QUERIES[0])))"
# Each must print >0.

# 2. Full scan
bash run_scan.sh 2>&1 | tee /tmp/scan_test.log
grep -E "^\[" /tmp/scan_test.log
grep "LinkedIn" /tmp/scan_test.log    # expect +N>0
ls -t reports/ | head -1

# 3. Inspect new sections
grep -E "ЗАРУБЕЖНАЯ|РЕЛОКАЦИЯ" reports/$(date +%Y-%m-%d).md
```

## Career-bot compatibility

`career-bot/scanner.py::parse_report_text` parses the markdown digest. New section headers must not break it. Verify after scan:

```bash
cd ~/workspaces/career-bot
python3 -c "import scanner; r = scanner.parse_report_text(open('../jobsearch/reports/$(date +%Y-%m-%d).md').read()); print(len(r), 'jobs parsed')"
```

If parser is brittle on new headers, patch `career-bot/scanner.py` to whitelist new section names. This is part of Phase 1 scope.

## Rollout

1. Branch `feat/jobsearch-foreign-sources` from `~` (repo root is `/home/shectory`).
2. Implement modular split.
3. Implement fixes + new sources.
4. Implement categorization + scoring + cap + dedup.
5. Write tests, pytest green.
6. Manual smoke (above).
7. Inspect today's report visually.
8. Verify career-bot parser still works.
9. Commit, merge to master, push.
10. Cron `Job Scan Morning` (0 6 * * *) / `Evening` (0 17 * * *) picks up automatically — no service restart needed.

## Rollback

`git revert <merge-commit>`. The monolithic `scan_v4.py` predates this change and works (as evidenced by 2026-05-28 report with 4 working sources). No DB migrations.

## Out-of-scope notes

- Indeed (Phase 2): higher complexity, CAPTCHA risk, may need playwright. Separate spec.
- Wellfound: login wall.
- Otta/Welcome to the Jungle: account required.
- Glassdoor: closed API.
- StackOverflow Jobs: shut down 2024.

## Open questions

None at spec-approval time.
