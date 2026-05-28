#!/usr/bin/env python3
"""
JobScanner v4 — поиск C-level вакансий для Бориса Шевелева

Изменения относительно v3:
  🔧 Все внешние HTTP-запросы — через Lineman (http://127.0.0.1:9090)
  🔧 Удалены жёстко зашитые прокси-учётные данные (PROXY_MAIN, PROXY_BRD)
  🔧 Добавлены ретраи при сетевых ошибках
  🔧 Починен LinkedIn (BrightData Residential через Lineman)
  🔧 Починен Telegram: uncomment @cto_ru, @remote_ru; улучшен extract_job_title
  🔧 Добавлены новые парсеры: Habr Career, SuperJob, FL.ru, Freelance.ru
  🔧 Улучшен скоринг: фильтр низовых ролей (директор магазина и т.п.)
  🔧 Отчёт по шаблону: 4 секции (Удалёнка/Гибрид/Офис/Проекты)
  🔧 Очистка ссылок hh.ru (удаление рекламных параметров)
  🔧 Gemini AI-фильтр для сомнительных вакансий
  🔧 Создание favorites.md для избранного

Запуск: python3 scan_v4.py [--dry-run] [--gemini]
"""

import json
import os
import sys
import datetime
import urllib.parse
import urllib.request
import re
import time
import random
import html
import functools
from typing import Optional

import requests
from bs4 import BeautifulSoup
from sources import SOURCE_REGISTRY
from sources.base import title_hash as _title_hash

# ────────────────────────────────────────────────────────────────────
# ПРОКСИ — все внешние запросы через Lineman
# В соответствии с протоколом федерации Shectory
# ────────────────────────────────────────────────────────────────────
LINEMAN_PROXY = os.environ.get("LINEMAN_PROXY", "http://127.0.0.1:9090")
os.environ.setdefault("http_proxy", LINEMAN_PROXY)
os.environ.setdefault("https_proxy", LINEMAN_PROXY)

# Чтение Gemini-ключа из окружения (не хардкодим!)
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"  # дешёвая модель для фильтрации

WORKSPACE = os.path.expanduser("~/workspaces/jobsearch")
SEEN_FILE = os.path.join(WORKSPACE, "seen-jobs.json")
REPORTS_DIR = os.path.join(WORKSPACE, "reports")
FAVORITES_FILE = os.path.join(WORKSPACE, "favorites.md")

# ────────────────────────────────────────────────────────────────────
# РЕТРАИ — повтор при сетевых ошибках
# ────────────────────────────────────────────────────────────────────

def retry(max_attempts=3, delay=2.0, backoff=2.0, exceptions=(ConnectionError, TimeoutError, requests.ConnectionError, requests.Timeout)):
    """Декоратор для повторных попыток при сетевых ошибках."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        wait = delay * (backoff ** (attempt - 1)) + random.uniform(0, 0.5)
                        print(f"    ⚠️  {type(e).__name__}: {e} — ретрай {attempt}/{max_attempts} через {wait:.1f}с")
                        time.sleep(wait)
                    else:
                        print(f"    ❌ {type(e).__name__}: {e} — исчерпаны попытки")
            raise last_exc
        return wrapper
    return decorator


# ────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ
# ────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
}

HH_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def clean_hh_url(url: str) -> str:
    """Очищает рекламные ссылки hh.ru → чистые /vacancy/N ссылки."""
    if not url:
        return url
    # adsrv.hh.ru/click?... → извлекаем реальный URL
    m = re.search(r'/vacancy/(\d+)', url)
    if m:
        return f"https://hh.ru/vacancy/{m.group(1)}"
    return url


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            try:
                data = json.load(f)
            except Exception:
                data = {}
        if "title_hashes" not in data:
            data["title_hashes"] = []
        return data
    return {"last_scan": None, "seen": [], "title_hashes": []}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_session(extra_headers=None):
    """Сессия requests с Lineman-прокси. Не использует хардкод-прокси."""
    s = requests.Session()
    s.headers.update(HEADERS)
    if extra_headers:
        s.headers.update(extra_headers)
    # Lineman прокси устанавливается через os.environ
    # (http_proxy/https_proxy), requests подхватывает автоматически
    return s


# ────────────────────────────────────────────────────────────────────
# ПАРСЕРЫ ИСТОЧНИКОВ
# ────────────────────────────────────────────────────────────────────

# --- 1. HH.ru (web-scraping) ---

HH_SEARCH_QUERIES = [
    "директор по ИТ",
    "технический директор",
    "CTO",
    "CIO",
    "head of IT",
    "директор по цифровой трансформации",
    "CDTO",
    "AI Architect",
    "IT директор",
]


@retry()
def fetch_hh_web(query):
    """HH.ru через web-scraping. Все запросы через Lineman."""
    try:
        s = get_session({
            "User-Agent": random.choice(HH_UAS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://hh.ru/",
        })
        s.get("https://hh.ru/", timeout=15)
        time.sleep(random.uniform(1.0, 2.5))
        params = {
            "text": query,
            "area": 1,
            "items_on_page": 20,
            "order_by": "publication_time",
        }
        r = s.get("https://hh.ru/search/vacancy", params=params, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for block in soup.select('[data-qa*="vacancy-serp__vacancy"]'):
        job = {"source": "hh.ru"}
        title_el = block.select_one('[data-qa="serp-item__title"]')
        if not title_el:
            continue
        job["name"] = title_el.get_text(strip=True)
        raw_url = title_el.get("href", "")
        job["alternate_url"] = clean_hh_url(raw_url)
        if not job["name"]:
            continue
        id_match = re.search(r'/vacancy/(\d+)', job["alternate_url"])
        job["id"] = id_match.group(1) if id_match else f"hh-{abs(hash(query + job['name'])) % 10**8}"
        employer_el = block.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
        if employer_el:
            job["employer"] = {"name": employer_el.get_text(strip=True)}
        salary_text = block.get_text()
        salary = parse_hh_salary(salary_text)
        if salary:
            job["salary"] = salary
        loc_el = block.select_one('[data-qa="vacancy-serp__vacancy-address"]')
        if loc_el:
            loc_raw = loc_el.get_text(strip=True)
            job["area"] = {"name": loc_raw.split(",")[0].strip()}
        snippet_el = block.select_one('[data-qa*="vacancy-serp__vacancy_snippet"]')
        if snippet_el:
            job["snippet"] = {"requirement": snippet_el.get_text(strip=True)}
        jobs.append(job)
    return jobs


def parse_hh_salary(text):
    text = text.replace('\u202f', ' ').replace('\xa0', ' ').replace('–', '-')
    currency = "RUR"
    if "₽" in text or "руб" in text:
        currency = "RUR"
    elif "$" in text:
        currency = "USD"
    elif "€" in text:
        currency = "EUR"
    m = re.search(r'от\s*([\d\s]+)\s*(?:до\s*([\d\s]+))?\s*(?:₽|руб|\$|€)', text, re.IGNORECASE)
    if m:
        salary = {"currency": currency}
        frm = int(m.group(1).replace(' ', '')) if m.group(1) else None
        to = int(m.group(2).replace(' ', '')) if m.group(2) else None
        if frm and frm > 1000:
            salary["from"] = frm
        if to and to > 1000:
            salary["to"] = to
        if salary.get("from") or salary.get("to"):
            return salary
    m = re.search(r'до\s*([\d\s]+)\s*(?:₽|руб|\$|€)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(' ', ''))
        if val > 1000:
            return {"to": val, "currency": currency}
    m = re.search(r'([\d\s]+)\s*[-–]\s*([\d\s]+)\s*(?:₽|руб|\$|€)', text)
    if m:
        frm = int(m.group(1).replace(' ', ''))
        to = int(m.group(2).replace(' ', ''))
        if frm > 1000 and to > 1000:
            return {"from": frm, "to": to, "currency": currency}
    m = re.search(r'от\s*([\d\s]+)\s*(?:₽|руб)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(' ', ''))
        if val > 1000:
            return {"from": val, "currency": currency}
    return None


# --- 2. LinkedIn Guest API ---

LINKEDIN_QUERIES = [
    {"keywords": "CTO", "location": "Russia", "f_E": "5,6"},
    {"keywords": "CIO", "location": "Russia", "f_E": "5,6"},
    {"keywords": "Chief Technology Officer", "location": "Russia"},
    {"keywords": "IT Director", "location": "Moscow, Russia"},
]


@retry()
def fetch_linkedin(params):
    """LinkedIn Guest API. Все запросы через Lineman."""
    url_params = {
        "keywords": params.get("keywords", "CTO"),
        "location": params.get("location", "Russia"),
        "start": params.get("start", 0),
    }
    if params.get("f_E"):
        url_params["f_E"] = params["f_E"]
    if params.get("f_WT"):
        url_params["f_WT"] = params["f_WT"]

    try:
        s = get_session({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        })
        r = s.get(
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
            params=url_params,
            timeout=25,
        )
        r.raise_for_status()
        html_content = r.text
    except Exception:
        return []

    # Парсим HTML-карточки
    jobs = []
    cards = re.findall(
        r'<li[^>]*class="[^"]*job-result-card[^"]*"[^>]*>.*?</li>',
        html_content, re.DOTALL
    )

    for card in cards:
        job = {"source": "linkedin"}
        id_match = re.search(r'data-entity-urn="[^:]*:(\d+)"', card)
        if id_match:
            job["id"] = id_match.group(1)
        title_match = re.search(
            r'<span[^>]*class="[^"]*screen-reader-text[^"]*"[^>]*>(.*?)</span>',
            card, re.DOTALL
        )
        if title_match:
            job["name"] = html.unescape(title_match.group(1).strip())
        else:
            title_match = re.search(r'aria-label="[^"]*"', card)
            if title_match:
                aria = title_match.group(0)
                aria = aria.replace('aria-label="', '').rstrip('"')
                job["name"] = html.unescape(aria)
        if not job.get("name") or job["name"] == "":
            h3_match = re.search(r'<h3[^>]*>(.*?)</h3>', card, re.DOTALL)
            if h3_match:
                job["name"] = html.unescape(re.sub(r'<[^>]+>', '', h3_match.group(1)).strip())
            else:
                continue
        comp_match = re.search(
            r'class="[^"]*job-search-card__company-name[^"]*"[^>]*>\s*(.*?)\s*<',
            card, re.DOTALL
        )
        if comp_match:
            job["employer"] = {"name": html.unescape(comp_match.group(1).strip())}
        loc_match = re.search(
            r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*(.*?)\s*<',
            card, re.DOTALL
        )
        if loc_match:
            job["area"] = {"name": html.unescape(loc_match.group(1).strip())}
        link_match = re.search(r'href="([^"]+job/view/\d+[^"]*)"', card)
        if link_match:
            href = link_match.group(1)
            if href.startswith("/"):
                href = "https://www.linkedin.com" + href
            job["alternate_url"] = href
        jobs.append(job)
    return jobs


# --- 3. TrudVsem (Работа России) ---

TRUDVSEM_QUERIES = [
    {"text": "технический директор"},
    {"text": "директор по информационным технологиям"},
    {"text": "CTO"},
    {"text": "IT директор"},
]


@retry()
def fetch_trudvsem(params):
    """Работа России — open data API. Через Lineman."""
    text = params.get("text", "")
    url = f"http://opendata.trudvsem.ru/api/v1/vacancies?text={urllib.parse.quote(text)}&offset=0&limit=50"
    try:
        s = get_session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception:
        return []

    vacancies = data.get("results", {}).get("vacancies", [])
    jobs = []
    for item in vacancies:
        v = item.get("vacancy", {})
        job = {
            "id": v.get("id", ""),
            "name": v.get("job-name", ""),
            "employer": {
                "name": v.get("company", {}).get("short_name", "")
                         or v.get("company", {}).get("name", "")
            },
            "area": {"name": v.get("region", {}).get("name", "")},
            "alternate_url": f"https://trudvsem.ru/vacancy/view/{v.get('id', '')}",
            "source": "trudvsem",
            "description": v.get("duty", ""),
        }
        salary = {}
        if v.get("salary_min"):
            salary["from"] = int(float(v["salary_min"]))
        if v.get("salary_max"):
            salary["to"] = int(float(v["salary_max"]))
        salary["currency"] = "RUR"
        job["salary"] = salary if salary.get("from") or salary.get("to") else None
        if job["name"]:
            jobs.append(job)
    return jobs


# --- 4. Telegram ---

TELEGRAM_CHANNELS = [
    "forchiefs",
    "jobfortm",
    "geekjobs",
    "cto_ru",
    "remote_ru",     # может быть приватным, но попробуем
]

# Ключевые слова для C-level фильтрации Telegram
CLEVEL_KW = [
    "директор", "cto", "cio", "cdto", "head of it", "head of engineering",
    "vp engineering", "vp of", "chief", "технический директор",
    "it director", "руководитель", "ai architect", "вакансия",
    "ищем", "требуется", "открыта", "в команду",
]


@retry()
def fetch_telegram_channel(channel_name):
    """Парсинг публичной ленты Telegram-канала через t.me/s/"""
    url = f"https://t.me/s/{channel_name}"
    try:
        s = get_session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        html_content = r.text
    except Exception:
        return []

    messages = re.findall(
        r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>.*?<div class="tgme_widget_message[^"]*"[^>]*>.*?</div>\s*</div>',
        html_content, re.DOTALL
    )

    jobs = []
    seen_texts = set()

    for msg in messages:
        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            msg, re.DOTALL
        )
        if not text_match:
            continue
        text = html.unescape(re.sub(r'<[^>]+>', ' ', text_match.group(1))).strip()
        text_lower = text.lower()
        if not any(k in text_lower for k in CLEVEL_KW):
            continue
        text_key = text[:100]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)
        link_match = re.search(
            r'<a[^>]*href="([^"]+)"[^>]*class="tgme_widget_message_date"[^>]*>',
            msg, re.DOTALL
        )
        msg_url = link_match.group(1) if link_match else ""
        date_match = re.search(r'datetime="([^"]+)"', msg)
        pub_date = date_match.group(1)[:10] if date_match else ""
        title = extract_job_title_v4(text)
        job = {
            "id": f"tg-{channel_name}-{abs(hash(text[:100])) % 10**8}",
            "name": title or "Вакансия из Telegram",
            "employer": {"name": f"@{channel_name}"},
            "snippet": {"requirement": text[:300]},
            "alternate_url": msg_url,
            "source": "telegram",
            "published_at": pub_date,
            "channel": channel_name,
        }
        jobs.append(job)
    return jobs


def extract_job_title_v4(text):
    """Улучшенный extract_job_title — больше паттернов, меньше шума."""
    text_clean = text[:400]
    patterns = [
        # Прямые паттерны "ищем CTO", "вакансия Технический директор"
        r'(?:ищем|требуется|вакансия|открыта\s+вакансия|открыта\s+позиция|нанимаем|в\s+поиск)\s+[«"“]?([A-ZА-Я][A-Za-zА-Яа-я/\s]{2,60}?)[»"”]?(?:\s*[\(—\-–]|\s+с\s+зарплатой|\s+в\s+команду|$)',
        r'(?:ищем|нужен|нужна|нужно)\s+([A-ZА-Я][A-Za-zА-Яа-я\s/]{2,60}?)(?:\s*[\(—\-–]|\s*с\s+зарплатой|\s+в\s+команду|$)',
        # CTO/CIO/VP/Head of — прямое указание роли
        r'\b(CTO|CIO|CDTO|VP\s+of\s+[A-Z][a-z]+|Head\s+of\s+[A-Z][a-z]+|Head\s+of\s+[A-Z]{2,}|Chief\s+[A-Z][a-z]+\s+[A-Z][a-z]+|AI\s+Architect|IT\s+Director|Technical\s+Director|Tech\s+Lead|Engineering\s+Manager)\b',
        # Кириллические роли
        r'(Технический\s+директор|IT[\s-]*директор|Директор\s+по\s+ИТ|Руководитель\s+отдела\s+разработки|Руководитель\s+IT|Архитектор\s+AI|Director\s+of\s+Engineering)',
        # Generic fallback
        r'([A-ZА-Я][A-Za-zА-Яа-я/\s]{2,40}?)\s*(?:\(|—|-|–|\||с зарплатой|с зп|опыт|удален)',
    ]
    for pat in patterns:
        m = re.search(pat, text_clean, re.IGNORECASE)
        if m:
            title = m.group(1).strip().rstrip(".,;:!?")
            if len(title) > 3 and len(title) < 80:
                return title[:80]
    return ""


# --- 5. Habr Career ---

HABR_QUERIES = [
    "CTO",
    "IT-директор",
    "технический директор",
    "Team Lead",
]


@retry()
def fetch_habr_career(query):
    """Habr Career — парсинг страницы вакансий."""
    url = f"https://career.habr.com/vacancies?q={urllib.parse.quote(query)}&type=all"
    try:
        s = get_session({
            "User-Agent": random.choice(HH_UAS),
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for card in soup.select(".vacancy-card"):
        job = {"source": "habr_career"}
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
            sal_text = salary_el.get_text(strip=True)
            sal = parse_hh_salary(sal_text)
            if sal:
                job["salary"] = sal
        job["id"] = f"habr-{abs(hash(query + job.get('name', ''))) % 10**8}"
        jobs.append(job)
    return jobs


# --- 6. SuperJob ---

SJ_QUERIES = [
    "технический директор",
    "CTO",
    "IT директор",
]


@retry()
def fetch_superjob(query):
    """SuperJob — парсинг результатов поиска."""
    url = f"https://russia.superjob.ru/vacancy/search/?keywords={urllib.parse.quote(query)}"
    try:
        s = get_session({
            "User-Agent": random.choice(HH_UAS),
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for card in soup.select('[class*="_vacancy"]'):
        job = {"source": "superjob"}
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


# --- 7. FL.ru (фриланс-проекты) ---

FL_QUERIES = [
    "CTO",
    "технический директор",
    "IT директор",
    "AI",
]


@retry()
def fetch_fl_ru(query):
    """FL.ru — проекты. Не все C-level, но бывают интересные."""
    url = f"https://www.fl.ru/projects/?keywords={urllib.parse.quote(query)}"
    try:
        s = get_session({
            "User-Agent": random.choice(HH_UAS),
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for item in soup.select('[class*="project"]'):
        job = {"source": "fl_ru"}
        title_el = item.select_one("a") if hasattr(item, "select_one") else None
        if not title_el:
            continue
        name = title_el.get_text(strip=True) if hasattr(title_el, "get_text") else ""
        if not name or len(name) < 5:
            continue
        job["name"] = name
        href = title_el.get("href", "") if hasattr(title_el, "get") else ""
        if href:
            job["alternate_url"] = "https://www.fl.ru" + href if href.startswith("/") else href
        job["id"] = f"fl-{abs(hash(query + name)) % 10**8}"
        # FL.ru проекты — формат: фриланс/проектная работа
        job["_work_format"] = "project"
        jobs.append(job)
    return jobs


# --- 8. Freelance.ru ---

FR_QUERIES = [
    "CTO",
    "IT",
    "разработка",
]


@retry()
def fetch_freelanceru(query):
    """Freelance.ru — поиск проектов."""
    url = f"https://freelance.ru/projects/?q={urllib.parse.quote(query)}"
    try:
        s = get_session({
            "User-Agent": random.choice(HH_UAS),
            "Accept-Language": "ru-RU,ru;q=0.9",
        })
        r = s.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    jobs = []
    for item in soup.select('[class*="project"]'):
        job = {"source": "freelance_ru"}
        title_el = item.select_one("a")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name or len(name) < 5:
            continue
        job["name"] = name
        href = title_el.get("href", "")
        if href:
            job["alternate_url"] = "https://freelance.ru" + href if href.startswith("/") else href
        job["id"] = f"fr-{abs(hash(query + name)) % 10**8}"
        job["_work_format"] = "project"
        jobs.append(job)
    return jobs


# ────────────────────────────────────────────────────────────────────
# СКОРИНГ
# ────────────────────────────────────────────────────────────────────

# Роли C-level, которые нас интересуют (точное совпадение → +40)
EXEC_ROLES = [
    "cto", "cio", "cdto", "chief technology officer", "chief information officer",
    "chief digital officer", "technical director", "it director",
    "head of it", "head of engineering", "head of technology",
    "vp engineering", "vp of engineering", "vp of technology",
    "директор по ит", "директор по иформационным технологиям",
    "директор по цифровой трансформации", "технический директор",
    "it-директор", "it директор", "айти директор",
    "head of ai", "руководитель ai", "руководитель отдела ai",
    "ai architect", "директор по инновациям",
    "digital transformation", "chief digital",
]

# Роли, которые НЕ являются C-level (штраф)
LOW_LEVEL_ROLES = [
    "директор магазин", "директор по продажа", "коммерческий директор",
    "директор по маркетингу", "директор по персоналу", "hr директор",
    "директор по развитию бизнес", "директор филиал", "директор салон",
    "директор ресторан", "директор по снабжению", "директор департамент",
    "исполнительный директор", "генеральный директор",
    "art director", "арт-директор", "креативный директор",
    "финансовый директор", "director of sales", "sales director",
    "marketing director", "директор по закупк", "shop director",
    "store director", "директор по работе с клиент",
]


def score_vacancy(job):
    """Score 0-100. Исправлена ложная оценка низовых ролей."""
    score = 0
    name = (job.get("name") or "").lower()
    snippet = job.get("snippet") or {}
    req = (snippet.get("requirement") or "").lower()
    desc = (job.get("description") or "").lower()
    full = f"{name} {req} {desc}"

    # Штраф за низовые роли (директор магазина, etc.)
    if any(k in name for k in LOW_LEVEL_ROLES):
        return 0  # не наша категория

    # Бонус за проектную работу
    is_project = job.get("_work_format") == "project"

    # Соответствие роли (0-40)
    if any(k in name for k in EXEC_ROLES):
        score += 40
    elif any(k in full for k in EXEC_ROLES):
        score += 20
    elif any(k in full for k in ["руководитель", "lead", "head of", "manager"]):
        score += 8  # снизили с 10, чтобы не завышать

    # Зарплата (0-25)
    salary = job.get("salary")
    if salary and isinstance(salary, dict):
        amount = salary.get("from") or salary.get("to") or 0
        currency = salary.get("currency", "RUR")
        if currency == "RUR":
            if amount >= 500000:
                score += 25
            elif amount >= 400000:
                score += 15
            elif amount >= 300000:
                score += 10
            elif amount >= 200000:
                score += 5
        elif currency in ("USD", "EUR"):
            if amount >= 5000:
                score += 25
            elif amount >= 3000:
                score += 15
    else:
        score += 10  # не указана — нейтрально

    # Отрасль (0-20)
    good_industries = ["телеком", "финанс", "страхо", "фарм", "росатом", "атом",
                       "медицин", "банк", "холдинг", "производств", "логист",
                       "ритейл", "retail", "энерг"]
    employer = (job.get("employer") or {}).get("name", "").lower()
    if any(k in employer for k in good_industries):
        score += 20
    elif any(k in full for k in good_industries):
        score += 10
    else:
        score += 10

    # Формат работы (0-15)
    area_name = (job.get("area") or {}).get("name", "").lower()
    if any(w in area_name for w in ["remote", "удален", "дистанц"]):
        score += 15
    elif "москв" in area_name or "moscow" in area_name:
        score += 10
    elif "санкт" in area_name:
        score += 5

    # Бонус за проект (фриланс-проекты = высокая гибкость)
    if is_project:
        score += 5

    return min(score, 100)


# ────────────────────────────────────────────────────────────────────
# GEMINI AI-ФИЛЬТР (опционально)
# ────────────────────────────────────────────────────────────────────

def gemini_filter(jobs, max_to_check=10):
    """Использует Gemini для дополнительной фильтрации сомнительных вакансий.
    Запускается только с флагом --gemini."""
    if not GEMINI_KEY:
        print("  ⚠️  GEMINI_API_KEY не задан — AI-фильтр пропущен")
        return jobs

    # Фильтруем только средние по скорингу (40-59) — граничные случаи
    borderline = [(s, j) for s, j in jobs if 40 <= s < 60]
    if not borderline:
        return jobs

    # Берём до max_to_check самых близких к границе
    borderline.sort(key=lambda x: x[0], reverse=True)

    import google.generativeai as genai

    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
    except Exception:
        return jobs

    result = []
    for score, job in borderline[:max_to_check]:
        name = job.get("name", "")
        employer = (job.get("employer") or {}).get("name", "")
        req = (job.get("snippet") or {}).get("requirement", "")[:200]
        prompt = (
            f"Определи, является ли эта вакансия C-level (CTO/CIO/CDTO/IT Director/Head of AI). "
            f"Ответь только 'да' или 'нет'.\n"
            f"Название: {name}\n"
            f"Компания: {employer}\n"
            f"Требования: {req}"
        )
        try:
            resp = model.generate_content(prompt)
            answer = resp.text.strip().lower()
            if "да" in answer:
                result.append((score + 10, job))  # +10 за подтверждение
            else:
                result.append((score - 10, job))  # -10 за отрицание
        except Exception:
            result.append((score, job))  # без изменений

    # Не borderline оставляем как есть
    for s, j in jobs:
        if (s, j) not in borderline:
            result.append((s, j))

    return result


# ────────────────────────────────────────────────────────────────────
# ФОРМАТИРОВАНИЕ
# ────────────────────────────────────────────────────────────────────

def format_salary(job):
    s = job.get("salary")
    if s and isinstance(s, dict):
        frm, to = s.get("from"), s.get("to")
        cur = s.get("currency", "RUR")
        if frm and to:
            return f"{frm:,.0f}–{to:,.0f} {cur}"
        elif frm:
            return f"от {frm:,.0f} {cur}"
        elif to:
            return f"до {to:,.0f} {cur}"
    return "не указана"


def classify_section(job):
    """Однопроходная классификация вакансии: remote/hybrid/office/project."""
    if job.get("_work_format") == "project":
        return "project"
    name = (job.get("name") or "").lower()
    snippet = (job.get("snippet") or {}).get("requirement", "").lower()
    text = name + " " + snippet
    remote_words = ["remote", "удален", "дистанц", "online", "полностью удал"]
    if any(w in text for w in remote_words):
        return "remote"
    hybrid_words = ["гибрид", "hybrid", "частично удал", "смешан"]
    if any(w in text for w in hybrid_words):
        return "hybrid"
    area_name = (job.get("area") or {}).get("name", "").lower()
    if any(w in area_name for w in ["remote", "удален", "дистанц"]):
        return "remote"
    return "office"


def build_template_report(scored, date_str, stats):
    """Формирует отчёт по шаблону report-template.md (4 секции)."""
    # Разбиваем на секции — однопроходная классификация
    sections = {"remote": [], "hybrid": [], "office": [], "project": []}
    for s, j in scored:
        sections[classify_section(j)].append((s, j))
    # Сортируем внутри каждой секции
    for sec in sections:
        hot = sorted([x for x in sections[sec] if x[0] > 60], key=lambda x: -x[0])
        mid = sorted([x for x in sections[sec] if 40 <= x[0] <= 60], key=lambda x: -x[0])
        low = sorted([x for x in sections[sec] if x[0] < 40], key=lambda x: -x[0])
        sections[sec] = hot + mid + low

    total_new = len(scored)
    hot_all = len([s for s, _ in scored if s > 60])
    mid_all = len([s for s, _ in scored if 40 <= s <= 60])

    lines = [
        f"📊 **JOB DIGEST** · {date_str}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"Источников: {stats.get('active_sources', 0)} · Новых: {total_new} · В отчёте: {hot_all + mid_all}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]

    section_config = [
        ("remote", "🖥  **УДАЛЁНКА**"),
        ("hybrid", "🏙  **ГИБРИД**"),
        ("office", "🏢  **ОФИС**"),
        ("project", "⚡  **ПРОЕКТЫ / ФРИЛАНС**"),
    ]

    for sec_key, sec_title in section_config:
        sec_jobs = sections.get(sec_key, [])
        if not sec_jobs:
            continue
        lines.append(sec_title)
        lines.append("")
        count = 0
        for score, job in sec_jobs[:4]:  # макс 4 на секцию
            if count >= 8:  # макс 8 всего
                break
            count += 1
            icon = "🔥" if score > 60 else "📌"
            emp = (job.get("employer") or {}).get("name", "N/A")
            name = job.get("name", "")
            url = job.get("alternate_url") or ""
            area = (job.get("area") or {}).get("name", "")
            salary = format_salary(job)
            req = (job.get("snippet") or {}).get("requirement", "")[:120]
            req = re.sub(r'<[^>]+>', '', req).strip()
            source = job.get("source", "web")
            pub = (job.get("published_at") or "")[:10]

            # Определяем тип занятости
            if sec_key == "project":
                emp_type = "проект"
            elif source == "telegram":
                emp_type = "постоянная"  # по умолчанию
            else:
                emp_type = "постоянная"

            # Определяем локацию-иконку
            loc_icon = "🌍 Remote" if sec_key == "remote" else f"📍 {area}" if area else "📍 —"

            lines.append(f"{icon} **{name}** · {score}/100 · {emp_type}")

            # Пытаемся определить отрасль
            industry = ""
            if emp and emp != "N/A":
                industry = f"{emp}"
            lines.append(f"🏢 {industry}" if industry else "")

            lines.append(f"💰 {salary} · {loc_icon}")
            lines.append(f"📋 {req[:100]}" if req else "")
            lines.append(f"🔗 {clean_hh_url(url)}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────
# MAIN
# ────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    use_gemini = "--gemini" in sys.argv
    today = datetime.date.today().isoformat()

    print(f"🔎 JobScanner v4 запущен: {today}")
    print(f"Прокси: {LINEMAN_PROXY}")

    seen_data = load_seen()
    seen_ids = set(job for job in seen_data.get("seen", []))

    # Убедимся что favorites.md существует
    if not os.path.exists(FAVORITES_FILE):
        with open(FAVORITES_FILE, "w") as f:
            f.write(f"# Избранное JobScanner\n\nВакансии, отмеченные Борисом.\n\n")
        print(f"  📄 Создан favorites.md")

    all_jobs = {}
    stats = {"queries": 0, "total": 0, "active_sources": 0}

    # Определяем источники и их функции
    sources = []

    # ── Source loop ──────────────────────────────────────────────────
    title_hashes: set[str] = set(seen_data.get("title_hashes", []))

    for src in SOURCE_REGISTRY:
        print(f"\n[{src.name}]")
        src_count = 0
        for params in src.queries:
            label = str(params)[:40]
            print(f"  → {label}...", end=" ", flush=True)
            items = src.fetch(params)
            added = 0
            for job in items:
                jid = f"{src.name}-{job.get('id', '')}"
                th = _title_hash(job)
                if jid in all_jobs or th in title_hashes:
                    continue
                all_jobs[jid] = job
                title_hashes.add(th)
                src_count += 1
                added += 1
            stats["queries"] += 1
            print(f"+{added}")
            time.sleep(src.sleep)
        if src_count > 0:
            stats["active_sources"] += 1
        print(f"  → Итого: +{src_count}")

    # --- Итог ---
    stats["total"] = len(all_jobs)
    print(f"\nИтого уникальных: {len(all_jobs)}")

    # --- Скоринг ---
    new_jobs = [(jid, job) for jid, job in all_jobs.items() if jid not in seen_ids]
    print(f"Новых (не виденных ранее): {len(new_jobs)}")

    scored = [(score_vacancy(job), job) for _, job in new_jobs]

    # Gemini AI-фильтр (опционально)
    if use_gemini:
        print("\n[Gemini AI-фильтр]")
        scored = gemini_filter(scored)
        print("  ✅ Фильтрация завершена")

    # --- Отчёт по шаблону ---
    report = build_template_report(scored, today, stats)
    print("\n" + report)

    if not dry_run:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        report_path = os.path.join(REPORTS_DIR, f"{today}.md")
        with open(report_path, "w") as f:
            f.write(report)
        new_ids = [jid for jid, _ in new_jobs]
        seen_data["seen"] = list(seen_ids | set(new_ids))
        seen_data["last_scan"] = today
        seen_data["title_hashes"] = list(title_hashes)[-5000:]
        save_seen(seen_data)
        print(f"\n✅ Отчёт сохранён: {report_path}")
    else:
        print("\n[DRY RUN — изменения не сохранены]")


if __name__ == "__main__":
    main()
