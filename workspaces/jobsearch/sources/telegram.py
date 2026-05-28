# sources/telegram.py
import html
import re
from .base import get_session, retry

NAME = "telegram"

CHANNELS = ["forchiefs", "jobfortm", "geekjobs", "cto_ru", "remote_ru"]

_CLEVEL_KW = [
    "директор", "cto", "cio", "cdto", "head of it", "head of engineering",
    "vp engineering", "vp of", "chief", "технический директор",
    "it director", "руководитель", "ai architect", "вакансия",
    "ищем", "требуется", "открыта", "в команду",
]

_TITLE_PATTERNS = [
    r'(?:ищем|требуется|вакансия|открыта\s+вакансия|открыта\s+позиция|нанимаем|в\s+поиск)\s+[«""]?([A-ZА-Я][A-Za-zА-Яа-я/\s]{2,60}?)[»""]?(?:\s*[\(—\-–]|\s+с\s+зарплатой|\s+в\s+команду|$)',
    r'(?:ищем|нужен|нужна|нужно)\s+([A-ZА-Я][A-Za-zА-Яа-я\s/]{2,60}?)(?:\s*[\(—\-–]|\s*с\s+зарплатой|\s+в\s+команду|$)',
    r'\b(CTO|CIO|CDTO|VP\s+of\s+[A-Z][a-z]+|Head\s+of\s+[A-Z][a-z]+|Chief\s+[A-Z][a-z]+\s+[A-Z][a-z]+|AI\s+Architect|IT\s+Director|Technical\s+Director)\b',
    r'(Технический\s+директор|IT[\s-]*директор|Директор\s+по\s+ИТ|Руководитель\s+отдела\s+разработки)',
]


def _extract_title(text: str) -> str:
    for pat in _TITLE_PATTERNS:
        m = re.search(pat, text[:400], re.IGNORECASE)
        if m:
            t = m.group(1).strip().rstrip(".,;:!?")
            if 3 < len(t) < 80:
                return t[:80]
    return ""


@retry()
def fetch(params: dict) -> list[dict]:
    channel = params.get("channel", "")
    url = f"https://t.me/s/{channel}"
    try:
        s = get_session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        html_content = r.text
    except Exception:
        return []

    messages = re.findall(
        r'<div class="tgme_widget_message_wrap[^"]*"[^>]*>.*?<div class="tgme_widget_message[^"]*"[^>]*>.*?</div>\s*</div>',
        html_content, re.DOTALL,
    )
    jobs, seen = [], set()
    for msg in messages:
        text_match = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', msg, re.DOTALL)
        if not text_match:
            continue
        text = html.unescape(re.sub(r"<[^>]+>", " ", text_match.group(1))).strip()
        if not any(k in text.lower() for k in _CLEVEL_KW):
            continue
        key = text[:100]
        if key in seen:
            continue
        seen.add(key)
        link_m = re.search(r'<a[^>]*href="([^"]+)"[^>]*class="tgme_widget_message_date"[^>]*>', msg, re.DOTALL)
        msg_url = link_m.group(1) if link_m else ""
        date_m = re.search(r'datetime="([^"]+)"', msg)
        pub_date = date_m.group(1)[:10] if date_m else ""
        jobs.append({
            "id": f"tg-{channel}-{abs(hash(text[:100])) % 10**8}",
            "name": _extract_title(text) or "Вакансия из Telegram",
            "employer": {"name": f"@{channel}"},
            "snippet": {"requirement": text[:300]},
            "alternate_url": msg_url,
            "source": NAME,
            "published_at": pub_date,
        })
    return jobs
