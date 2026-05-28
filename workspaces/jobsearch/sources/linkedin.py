import re
from bs4 import BeautifulSoup
from .base import get_session, retry

NAME = "linkedin"

QUERIES = [
    # Russia — remote-only (f_WT=2)
    {"keywords": "CTO", "location": "Russia", "f_E": "5,6", "f_WT": "2"},
    {"keywords": "Head of Engineering", "location": "Russia", "f_E": "5", "f_WT": "2"},
    # EU
    {"keywords": "CTO", "location": "European Union", "f_E": "5,6"},
    {"keywords": "VP Engineering", "location": "European Union", "f_E": "5"},
    # US
    {"keywords": "Chief Technology Officer", "location": "United States", "f_E": "5,6"},
    {"keywords": "Director of Engineering", "location": "United States", "f_E": "5"},
]

_URN_RE = re.compile(r"jobPosting")
_ID_RE = re.compile(r"jobPosting:(\d+)")


@retry()
def fetch(params: dict) -> list[dict]:
    try:
        s = get_session(
            extra_headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
            use_proxy=True,
        )
        r = s.get(
            "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search",
            params={k: v for k, v in params.items()},
            timeout=25,
        )
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # LinkedIn puts data-entity-urn on a <div> inside each <li>
    cards = soup.find_all(attrs={"data-entity-urn": _URN_RE})

    jobs = []
    for card in cards:
        urn = card.get("data-entity-urn", "")
        id_match = _ID_RE.search(urn)
        if not id_match:
            continue

        # Title: sr-only span (screen-reader text) or h3
        title_el = card.find("span", class_="sr-only")
        if not title_el:
            title_el = card.find("h3")
        if not title_el:
            continue
        name = title_el.get_text(strip=True)
        if not name:
            continue

        comp_el = card.find(class_=re.compile(r"base-search-card__subtitle"))
        if not comp_el:
            comp_el = card.find(class_=re.compile(r"job-search-card__company-name"))
        company = comp_el.get_text(strip=True) if comp_el else ""

        loc_el = card.find(class_=re.compile(r"job-search-card__location"))
        area = loc_el.get_text(strip=True) if loc_el else ""

        link_el = card.find("a", href=re.compile(r"jobs/view/"))
        url = link_el["href"] if link_el else ""
        if url.startswith("/"):
            url = "https://www.linkedin.com" + url

        jobs.append({
            "id": id_match.group(1),
            "source": NAME,
            "name": name,
            "employer": {"name": company},
            "area": {"name": area},
            "alternate_url": url,
            "remote_flag": params.get("f_WT") == "2",
        })

    return jobs
