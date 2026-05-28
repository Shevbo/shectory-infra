import functools
import hashlib
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Callable

import requests

LINEMAN_PROXY = os.environ.get("LINEMAN_PROXY", "http://127.0.0.1:9090")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
}

HH_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

CLEVEL_PATTERN = re.compile(
    r"(?i)\b(CTO|CIO|Chief Technology|Chief Information|VP Engineering|VP of Engineering"
    r"|Head of Engineering|Director of Engineering|Engineering Director)\b"
)


@dataclass
class Source:
    name: str
    queries: list
    fetch: Callable
    sleep: float = 1.0
    use_proxy: bool = True


def get_session(extra_headers=None, use_proxy=True):
    s = requests.Session()
    s.headers.update(HEADERS)
    if extra_headers:
        s.headers.update(extra_headers)
    if use_proxy:
        s.proxies = {"http": LINEMAN_PROXY, "https": LINEMAN_PROXY}
    else:
        s.trust_env = False
    return s


def retry(max_attempts=3, delay=2.0, backoff=2.0,
          exceptions=(ConnectionError, TimeoutError,
                      requests.ConnectionError, requests.Timeout)):
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
                        time.sleep(wait)
            raise last_exc
        return wrapper
    return decorator


def title_hash(job: dict) -> str:
    name = re.sub(r"[^\w\s]", "", (job.get("name") or "").lower()).strip()
    company = re.sub(r"[^\w\s]", "", ((job.get("employer") or {}).get("name") or "").lower()).strip()
    return hashlib.sha1(f"{name}|{company}".encode()).hexdigest()[:12]
