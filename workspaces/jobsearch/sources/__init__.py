# sources/__init__.py
from .base import Source
from . import (
    hh, linkedin, trudvsem, habr, superjob, telegram,
    flru, freelanceru, remoteok, wwr, jobicy, hn_hiring,
)

SOURCE_REGISTRY: list[Source] = [
    Source(name=hh.NAME,           queries=[{"q": q} for q in hh.QUERIES],               fetch=hh.fetch,          sleep=2.0,  use_proxy=True),
    Source(name=linkedin.NAME,     queries=linkedin.QUERIES,                              fetch=linkedin.fetch,    sleep=2.0,  use_proxy=True),
    Source(name=trudvsem.NAME,     queries=trudvsem.QUERIES,                              fetch=trudvsem.fetch,    sleep=0.3,  use_proxy=True),
    Source(name=habr.NAME,         queries=[{"q": q} for q in habr.QUERIES],             fetch=habr.fetch,        sleep=1.0,  use_proxy=True),
    Source(name=superjob.NAME,     queries=[{"q": q} for q in superjob.QUERIES],         fetch=superjob.fetch,    sleep=1.0,  use_proxy=True),
    Source(name=telegram.NAME,     queries=[{"channel": c} for c in telegram.CHANNELS],  fetch=telegram.fetch,    sleep=1.5,  use_proxy=True),
    Source(name=flru.NAME,         queries=[{"q": q} for q in flru.QUERIES],             fetch=flru.fetch,        sleep=1.0,  use_proxy=True),
    Source(name=freelanceru.NAME,  queries=[{"q": q} for q in freelanceru.QUERIES],      fetch=freelanceru.fetch, sleep=1.0,  use_proxy=True),
    Source(name=remoteok.NAME,     queries=remoteok.QUERIES,                              fetch=remoteok.fetch,    sleep=1.5,  use_proxy=False),
    Source(name=wwr.NAME,          queries=wwr.QUERIES,                                   fetch=wwr.fetch,         sleep=2.0,  use_proxy=False),
    Source(name=jobicy.NAME,       queries=jobicy.QUERIES,                                fetch=jobicy.fetch,      sleep=1.0,  use_proxy=False),
    Source(name=hn_hiring.NAME,    queries=hn_hiring.QUERIES,                             fetch=hn_hiring.fetch,   sleep=0.5,  use_proxy=True),
]
