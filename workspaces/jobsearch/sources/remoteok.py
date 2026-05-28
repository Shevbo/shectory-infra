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
