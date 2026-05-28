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
