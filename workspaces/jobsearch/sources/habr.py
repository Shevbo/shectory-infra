# sources/habr.py
import random
import urllib.parse
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
