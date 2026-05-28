# sources/trudvsem.py
import urllib.parse
from .base import get_session, retry

NAME = "trudvsem"

QUERIES = [
    {"text": "технический директор"},
    {"text": "директор по информационным технологиям"},
    {"text": "CTO"},
    {"text": "IT директор"},
]


@retry()
def fetch(params: dict) -> list[dict]:
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
            "employer": {"name": v.get("company", {}).get("short_name", "") or v.get("company", {}).get("name", "")},
            "area": {"name": v.get("region", {}).get("name", "")},
            "alternate_url": f"https://trudvsem.ru/vacancy/view/{v.get('id', '')}",
            "source": NAME,
            "description": v.get("duty", ""),
        }
        salary: dict = {}
        if v.get("salary_min"):
            salary["from"] = int(float(v["salary_min"]))
        if v.get("salary_max"):
            salary["to"] = int(float(v["salary_max"]))
        salary["currency"] = "RUR"
        job["salary"] = salary if salary.get("from") or salary.get("to") else None
        if job["name"]:
            jobs.append(job)
    return jobs
