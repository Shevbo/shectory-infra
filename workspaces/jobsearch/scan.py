#!/usr/bin/env python3
"""
JobScanner v3 — поиск вакансий C-level для Бориса Шевелева
Реальные источники:
  • HH.ru           ✅ web-scraping (API заблокирован ddos-guard)
  • LinkedIn Guest  ✅ публичный endpoint
  • TrudVsem        ✅ open data API (Работа России)
  • Telegram        ✅ парсинг t.me/s/

Запуск: python3 scan.py [--dry-run]
"""

import json
import os
import sys
import datetime
import urllib.parse
import re
import time
import random
import html
import requests
from bs4 import BeautifulSoup

# ⚠️ Креды удалены в scan_v4.py. Все запросы через Lineman (http://127.0.0.1:9090)
PROXY_MAIN   = "http://127.0.0.1:9090"  # через Lineman
PROXY_BRD    = "http://127.0.0.1:9090"  # через Lineman
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-pro"  # 3.1-pro = 250 RPD кап даже на Tier1; делили с карьерой (2026-06-13)
WORKSPACE  = os.path.expanduser("~/workspaces/jobsearch")
SEEN_FILE  = os.path.join(WORKSPACE, "seen-jobs.json")
REPORTS_DIR = os.path.join(WORKSPACE, "reports")

# ===== НАСТРОЙКИ =====
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

LINKEDIN_QUERIES = [
    {"keywords": "CTO", "location": "Russia", "f_E": "5,6"},
    {"keywords": "CIO", "location": "Russia", "f_E": "5,6"},
    {"keywords": "Chief Technology Officer", "location": "Russia"},
    {"keywords": "IT Director", "location": "Moscow, Russia"},
]

TRUDVSEM_QUERIES = [
    {"text": "технический директор"},
    {"text": "директор по информационным технологиям"},
    {"text": "CTO"},
    {"text": "IT директор"},
]

TELEGRAM_CHANNELS = [
    "forchiefs",    # работает
    "jobfortm",     # работает
    "geekjobs",     # работает
    # "cto_ru",     # web-preview отключён — нет данных
    # "remote_ru",  # приватный канал (редирект на t.me/+...)
]

PROXIES = {
    "http": PROXY_MAIN,
    "https": PROXY_MAIN,
}

PROXIES_BRD = {
    "http": PROXY_BRD,
    "https": PROXY_BRD,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
}

HH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}


# ===== ВСПОМОГАТЕЛЬНЫЕ =====

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {"last_scan": None, "seen": []}


def save_seen(data):
    with open(SEEN_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_session(use_proxy=True, use_brd=False):
    s = requests.Session()
    s.headers.update(HEADERS)
    if use_proxy:
        s.proxies.update(PROXIES_BRD if use_brd else PROXIES)
    return s


# ===== ЗАГРУЗЧИКИ =====

_HH_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


def fetch_hh_web(query, use_proxy=False):
    """
    HH.ru через web-scraping (API возвращает 403 из-за ddos-guard).
    Используем hh.ru/search/vacancy с сессией и cookies.
    Direct (no proxy) работает стабильнее — смain IP российский.
    """
    try:
        s = get_session(use_proxy=use_proxy)
        s.headers.update({
            "User-Agent": random.choice(_HH_UAS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Referer": "https://hh.ru/",
        })
        s.get("https://hh.ru/", timeout=15)
        time.sleep(random.uniform(1.0, 2.5))  # дать DDoS-guard успокоиться
        params = {
            "text": query,
            "area": 1,
            "items_on_page": 20,
            "order_by": "publication_time",
        }
        r = s.get("https://hh.ru/search/vacancy", params=params, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        return []

    jobs = []
    for block in soup.select('[data-qa*="vacancy-serp__vacancy"]'):
        job = {"source": "hh.ru"}

        title_el = block.select_one('[data-qa="serp-item__title"]')
        if not title_el:
            continue
        job["name"] = title_el.get_text(strip=True)
        job["alternate_url"] = title_el.get("href", "")
        if not job["name"]:
            continue

        id_match = re.search(r'/vacancy/(\d+)', job["alternate_url"])
        job["id"] = id_match.group(1) if id_match else f"hh-{abs(hash(query + job['name'])) % 10**8}"

        employer_el = block.select_one('[data-qa="vacancy-serp__vacancy-employer"]')
        if employer_el:
            job["employer"] = {"name": employer_el.get_text(strip=True)}

        # Зарплата — сперва скрытое поле, потом видимый текст
        compensation_input = block.find("input", attrs={"data-qa": "vacancy-serp__compensation"})
        if compensation_input and compensation_input.get("value"):
            pass  # значение скрыто
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
    """Парсит зарплату из текста. Ищет паттерны вида: от 300 000 ₽, 200 000–500 000 ₽, $5000"""
    text = text.replace('\u202f', ' ').replace('\xa0', ' ').replace('–', '-')
    
    currency = "RUR"
    if "₽" in text or "руб" in text:
        currency = "RUR"
    elif "$" in text:
        currency = "USD"
    elif "€" in text:
        currency = "EUR"
    
    # Ищем паттерн: от X до Y
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
    
    # Ищем паттерн: до X
    m = re.search(r'до\s*([\d\s]+)\s*(?:₽|руб|\$|€)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(' ', ''))
        if val > 1000:
            return {"to": val, "currency": currency}
    
    # Ищем паттерн: X – Y
    m = re.search(r'([\d\s]+)\s*[-–]\s*([\d\s]+)\s*(?:₽|руб|\$|€)', text)
    if m:
        frm = int(m.group(1).replace(' ', ''))
        to = int(m.group(2).replace(' ', ''))
        if frm > 1000 and to > 1000:
            return {"from": frm, "to": to, "currency": currency}
    
    # Ищем просто число с валютой
    m = re.search(r'от\s*([\d\s]+)\s*(?:₽|руб)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(' ', ''))
        if val > 1000:
            return {"from": val, "currency": currency}
    
    return None


def fetch_linkedin(params, use_proxy=True, use_brd=False):
    """LinkedIn Guest API — поиск вакансий (публичный endpoint)"""
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
        s = get_session(use_proxy=use_proxy, use_brd=use_brd)
        r = s.get(
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
            params=url_params,
            timeout=20,
        )
        r.raise_for_status()
        html_content = r.text
    except Exception as e:
        return []

    # Парсим HTML-карточки
    jobs = []
    # Ищем li с job-search-card
    cards = re.findall(
        r'<li[^>]*class="[^"]*job-result-card[^"]*"[^>]*>.*?</li>',
        html_content, re.DOTALL
    )

    for card in cards:
        job = {"source": "linkedin"}

        # ID
        id_match = re.search(r'data-entity-urn="[^:]*:(\d+)"', card)
        if id_match:
            job["id"] = id_match.group(1)

        # Название через data-entity-urn
        title_match = re.search(
            r'<span[^>]*class="[^"]*screen-reader-text[^"]*"[^>]*>(.*?)</span>',
            card, re.DOTALL
        )
        if title_match:
            job["name"] = html.unescape(title_match.group(1).strip())
        else:
            # fallback
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

        # Компания
        comp_match = re.search(
            r'class="[^"]*job-search-card__company-name[^"]*"[^>]*>\s*(.*?)\s*<',
            card, re.DOTALL
        )
        if comp_match:
            job["employer"] = {"name": html.unescape(comp_match.group(1).strip())}

        # Локация
        loc_match = re.search(
            r'class="[^"]*job-search-card__location[^"]*"[^>]*>\s*(.*?)\s*<',
            card, re.DOTALL
        )
        if loc_match:
            job["area"] = {"name": html.unescape(loc_match.group(1).strip())}

        # Ссылка
        link_match = re.search(r'href="([^"]+job/view/\d+[^"]*)"', card)
        if link_match:
            href = link_match.group(1)
            if href.startswith("/"):
                href = "https://www.linkedin.com" + href
            job["alternate_url"] = href

        jobs.append(job)

    return jobs


def fetch_trudvsem(params, use_proxy=True):
    """Работа России — open data API"""
    text = params.get("text", "")
    url = f"http://opendata.trudvsem.ru/api/v1/vacancies?text={urllib.parse.quote(text)}&offset=0&limit=50"

    try:
        s = get_session(use_proxy=use_proxy)
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


def fetch_telegram_channel(channel_name, use_proxy=True):
    """Парсинг публичной ленты Telegram-канала через t.me/s/"""
    url = f"https://t.me/s/{channel_name}"

    try:
        s = get_session(use_proxy=use_proxy)
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

    # Ключевые слова для фильтрации C-level вакансий
    c_level_kw = [
        "директор", "cto", "cio", "cdto", "head of it", "head of engineering",
        "vp engineering", "vp of", "chief", "технический директор",
        "it director", "руководитель", "ai architect", "вакансия",
        "ищем", "требуется", "открыта", "в команду",
    ]

    for msg in messages:
        text_match = re.search(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            msg, re.DOTALL
        )
        if not text_match:
            continue

        text = html.unescape(re.sub(r'<[^>]+>', ' ', text_match.group(1))).strip()
        text_lower = text.lower()

        if not any(k in text_lower for k in c_level_kw):
            continue

        text_key = text[:100]
        if text_key in seen_texts:
            continue
        seen_texts.add(text_key)

        # t.me markup puts class= before href= (attr order flipped ~2026) — the old
        # href-first regex silently returned "" for every post. data-post is stable.
        post_match = re.search(r'data-post="([^"]+/\d+)"', msg)
        if post_match:
            msg_url = f"https://t.me/{post_match.group(1)}"
        else:
            link_match = (re.search(r'<a[^>]*class="tgme_widget_message_date"[^>]*href="([^"]+)"', msg, re.DOTALL)
                          or re.search(r'<a[^>]*href="([^"]+)"[^>]*class="tgme_widget_message_date"', msg, re.DOTALL))
            msg_url = link_match.group(1) if link_match else ""

        date_match = re.search(r'datetime="([^"]+)"', msg)
        pub_date = date_match.group(1)[:10] if date_match else ""

        title = extract_job_title(text)

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


def extract_job_title(text):
    """Пытаемся вытащить название вакансии из текста"""
    patterns = [
        r'(?:ищем|требуется|вакансия|в команду|открыта вакансия|открыта позиция|нанимаем)\s+[«"“]?([^«"”,.!]+)',
        r'(?:ищем|нужен|нужна|нужно)\s+([A-ZА-Я][A-Za-zА-Яа-я\s/]{2,60}?)(?:\s*[\(—\-–]|\s*с\s+зарплатой|\s+в\s+команду|$)',
        r'([A-ZА-Я][A-Za-zА-Яа-я/\s]{2,40}?)\s*(?:\(|—|-|–|\||с зарплатой|с зп|опыт|удален)',
    ]
    for pat in patterns:
        m = re.search(pat, text[:250])
        if m:
            title = m.group(1).strip().rstrip(".,;:!?")
            if len(title) > 3:
                return title[:80]
    return ""


# ===== СКОРИНГ И ОТЧЁТЫ =====

def score_vacancy(job):
    """Score 0-100"""
    score = 0
    name = (job.get("name") or "").lower()
    snippet = job.get("snippet") or {}
    req = (snippet.get("requirement") or "").lower()
    desc = (job.get("description") or "").lower()
    full = f"{name} {req} {desc}"

    # Соответствие роли (0-40)
    exec_kw = ["директор", "cto", "cio", "технический директор", "chief technology",
               "chief information", "head of it", "head of engineering",
               "вице-президент", "vp engineering", "vp of it",
               "директор по цифровой", "cdto", "chief digital",
               "head of ai", "руководитель ai", "директор по инновациям",
               "ai architect", "digital transformation"]

    if any(k in name for k in exec_kw):
        score += 40
    elif any(k in full for k in exec_kw):
        score += 20
    elif any(k in full for k in ["руководитель", "lead", "head of", "manager"]):
        score += 10

    # Зарплата (0-25)
    salary = job.get("salary")
    if salary and isinstance(salary, dict):
        amount = salary.get("from") or salary.get("to") or 0
        currency = salary.get("currency", "RUR")
        if currency == "RUR":
            if amount >= 500000: score += 25
            elif amount >= 400000: score += 15
            elif amount >= 300000: score += 10
            elif amount >= 200000: score += 5
        elif currency in ("USD", "EUR"):
            if amount >= 5000: score += 25
            elif amount >= 3000: score += 15
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

    return min(score, 100)


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


def build_report(scored_new, date_str, stats):
    hot = sorted([(s, j) for s, j in scored_new if s >= 60], key=lambda x: -x[0])
    mid = sorted([(s, j) for s, j in scored_new if 40 <= s < 60], key=lambda x: -x[0])
    low = len([j for s, j in scored_new if s < 40])

    lines = [
        f"📊 ОТЧЁТ JOB SCANNER v3 — {date_str}",
        f"Источники: {', '.join(stats.get('source_names', []) or [])}",
        f"Запросов: {stats.get('queries', 0)}  |  Всего: {stats.get('total', 0)}  |  Новых: {len(scored_new)}",
        f"🔥 Горячих (>60): {len(hot)}  |  📌 Интересных (40-60): {len(mid)}  |  Пропущено: {low}",
        "",
    ]

    if hot:
        lines.append("━━━ 🔥 ГОРЯЧИЕ ВАКАНСИИ ━━━")
        for score, job in hot:
            emp = (job.get("employer") or {}).get("name", "N/A")
            url = job.get("alternate_url") or ""
            area = (job.get("area") or {}).get("name", "")
            source = job.get("source", "web")
            pub = (job.get("published_at") or "")[:10]
            lines += [
                f"\n🔥 {score}/100  {job['name']}",
                f"   🏢 {emp}  |  💰 {format_salary(job)}  |  📡 {source}",
                f"   📍 {area}  |  📅 {pub}",
                f"   🔗 {url}",
            ]

    if mid:
        lines.append("\n━━━ 📌 ИНТЕРЕСНЫЕ ВАКАНСИИ ━━━")
        for score, job in mid:
            emp = (job.get("employer") or {}).get("name", "N/A")
            url = job.get("alternate_url") or ""
            source = job.get("source", "web")
            lines += [
                f"\n📌 {score}/100  {job['name']}",
                f"   🏢 {emp}  |  💰 {format_salary(job)}  |  📡 {source}  |  🔗 {url}",
            ]

    if not hot and not mid:
        lines.append("Новых релевантных вакансий не найдено.")

    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv
    today = datetime.date.today().isoformat()
    print(f"🔎 JobScanner v3 запущен: {today}")
    print("Источники: HH.ru | LinkedIn | TrudVsem | Telegram")

    seen_data = load_seen()
    seen_ids = set(job for job in seen_data.get("seen", []))

    all_jobs = {}
    stats = {"queries": 0, "total": 0, "source_names": []}

    # --- 1. HH.ru web ---
    print("\n[HH.ru]")
    hh_count = 0
    for query in HH_SEARCH_QUERIES:
        print(f"  → {query}...", end=" ", flush=True)
        items = fetch_hh_web(query, use_proxy=False) or fetch_hh_web(query, use_proxy=True)
        for job in items:
            jid = job.get("id", "")
            if jid and jid not in all_jobs:
                all_jobs[jid] = job
                hh_count += 1
        stats["queries"] += 1
        print(f"+{len(items)} вакансий")
        time.sleep(random.uniform(2.0, 4.0))  # DDoS-guard требует паузы
    stats["source_names"].append(f"HH.ru (+{hh_count})")

    # --- 2. LinkedIn ---
    print("\n[LinkedIn]")
    ln_count = 0
    for params in LINKEDIN_QUERIES:
        kw = params.get("keywords", "")
        loc = params.get("location", "")
        print(f"  → {kw} ({loc})...", end=" ", flush=True)
        items = fetch_linkedin(params, use_proxy=True)
        for job in items:
            jid = f"ln-{job.get('id', '')}"
            if jid not in all_jobs:
                all_jobs[jid] = job
                ln_count += 1
        stats["queries"] += 1
        print(f"+{len(items)} вакансий")
        time.sleep(2.5)  # LinkedIn требует паузы
    stats["source_names"].append(f"LinkedIn (+{ln_count})")

    # --- 3. TrudVsem ---
    print("\n[Работа России]")
    tr_count = 0
    for params in TRUDVSEM_QUERIES:
        text = params.get("text", "")
        print(f"  → {text}...", end=" ", flush=True)
        items = fetch_trudvsem(params)
        for job in items:
            jid = f"tr-{job.get('id', '')}"
            if jid not in all_jobs:
                all_jobs[jid] = job
                tr_count += 1
        stats["queries"] += 1
        print(f"+{len(items)} вакансий")
        time.sleep(0.3)
    stats["source_names"].append(f"TrudVsem (+{tr_count})")

    # --- 4. Telegram ---
    print("\n[Telegram]")
    tg_count = 0
    for channel in TELEGRAM_CHANNELS:
        print(f"  → @{channel}...", end=" ", flush=True)
        items = fetch_telegram_channel(channel)
        for job in items:
            jid = job.get("id", "")
            if jid not in all_jobs:
                all_jobs[jid] = job
                tg_count += 1
        stats["queries"] += 1
        print(f"+{len(items)} вакансий")
        time.sleep(1.5)
    stats["source_names"].append(f"Telegram (+{tg_count})")

    # --- Итог ---
    stats["total"] = len(all_jobs)
    print(f"\nИтого уникальных: {len(all_jobs)}")

    # --- Скоринг ---
    new_jobs = [(jid, job) for jid, job in all_jobs.items() if jid not in seen_ids]
    print(f"Новых (не виденных): {len(new_jobs)}")

    scored = [(score_vacancy(job), job) for _, job in new_jobs]
    new_ids = [jid for jid, _ in new_jobs]

    report = build_report(scored, today, stats)
    print("\n" + report)

    if not dry_run:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        report_path = os.path.join(REPORTS_DIR, f"{today}.md")
        with open(report_path, "w") as f:
            f.write(report)
        seen_data["seen"] = list(seen_ids | set(new_ids))
        seen_data["last_scan"] = today
        save_seen(seen_data)
        print(f"\n✅ Отчёт сохранён: {report_path}")
    else:
        print("\n[DRY RUN]")


if __name__ == "__main__":
    main()
