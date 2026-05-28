# sources/flru.py
import random
import urllib.parse
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
