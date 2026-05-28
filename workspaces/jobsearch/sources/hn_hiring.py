"""
HN Who's Hiring source — Algolia API two-step:
1. Fetch latest "Ask HN: Who is hiring?" thread ID.
2. Search comments of that thread by keyword.
"""
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
    r = session.get(
        "https://hn.algolia.com/api/v1/search",
        params={"tags": "story,author_whoishiring"},
        timeout=15,
    )
    tid = r.json()["hits"][0]["objectID"]
    _thread_id_cache["id"] = tid
    return tid


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
        # Filter to C-level relevant posts only (search full text)
        if not CLEVEL_PATTERN.search(text):
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
