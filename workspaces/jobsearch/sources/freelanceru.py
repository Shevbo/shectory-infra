# sources/freelanceru.py
import random
import urllib.parse
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
