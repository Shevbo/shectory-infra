# sources/hh.py
import random
import re
import time
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
    text = text.replace(" ", " ").replace("\xa0", " ").replace("–", "-")
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
def fetch(params) -> list[dict]:
    q = params.get("q", "") if isinstance(params, dict) else str(params)
    try:
        s = get_session(
            extra_headers={
                "User-Agent": random.choice(HH_UAS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9",
                "Referer": "https://hh.ru/",
            }
        )
        s.get("https://hh.ru/", timeout=15)
        time.sleep(random.uniform(1.0, 2.5))
        p = {"text": q, "area": 1, "items_on_page": 20, "order_by": "publication_time"}
        r = s.get("https://hh.ru/search/vacancy", params=p, timeout=20)
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
