# sources/superjob.py
import random
import urllib.parse
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
