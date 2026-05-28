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
