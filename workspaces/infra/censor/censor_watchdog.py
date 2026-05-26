"""
censor_watchdog.py — fast anomaly detector, cron */10 * * * *.
Reads last 10 min of JSONL, computes per-agent metrics.
Triggers censor_investigator.py if any threshold exceeded.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_DIR = Path.home() / "logs" / "censor"
CENSOR_DIR = Path(__file__).resolve().parent
ACTIVE_INVESTIGATIONS = CENSOR_DIR / "active_investigations.json"
INVESTIGATOR = CENSOR_DIR / "censor_investigator.py"

WINDOW_MINUTES = 10
DEDUP_MINUTES = 30
RETRY_SCORE_THRESH = 0.85
RETRY_RATE_THRESH = 0.50
SESSION_TOKENS_THRESH = 200_000
ERROR_RATE_THRESH = 0.25
TOKENS_IN_THRESH = 800_000


def load_active() -> dict:
    if ACTIVE_INVESTIGATIONS.exists():
        try:
            return json.loads(ACTIVE_INVESTIGATIONS.read_text())
        except Exception:
            pass
    return {}


def save_active(data: dict) -> None:
    ACTIVE_INVESTIGATIONS.write_text(json.dumps(data, indent=2))


def is_recent(ts_str: str, minutes: int = DEDUP_MINUTES) -> bool:
    try:
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() < minutes * 60
    except Exception:
        return False


def load_recent_rows(since: datetime) -> list[dict]:
    rows = []
    dates = {since.strftime("%Y-%m-%d"), datetime.now(timezone.utc).strftime("%Y-%m-%d")}
    for date in sorted(dates):
        path = LOG_DIR / f"{date}.jsonl"
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("timestamp", "") >= since.isoformat():
                        rows.append(row)
                except Exception:
                    pass
    return rows


def compute_metrics(rows: list[dict]) -> dict[str, dict]:
    agents: dict[str, dict] = defaultdict(lambda: {
        "requests": 0, "retries": 0, "errors": 0,
        "tokens_in": 0, "max_session_tokens": 0,
    })
    for r in rows:
        key = f"{r.get('source_host') or '?'}:{r.get('source_agent') or '?'}"
        a = agents[key]
        a["requests"] += 1
        if (r.get("retry_score") or 0) >= RETRY_SCORE_THRESH:
            a["retries"] += 1
        if r.get("error"):
            a["errors"] += 1
        a["tokens_in"] += r.get("tokens_in") or 0
        sess = r.get("session_tokens_in") or 0
        if sess > a["max_session_tokens"]:
            a["max_session_tokens"] = sess
    result = {}
    for key, a in agents.items():
        n = a["requests"]
        result[key] = {
            "requests": n,
            "retry_rate": round(a["retries"] / n, 3) if n else 0.0,
            "error_rate": round(a["errors"] / n, 3) if n else 0.0,
            "tokens_in": a["tokens_in"],
            "max_session_tokens": a["max_session_tokens"],
        }
    return result


def check_thresholds(metrics: dict) -> list[str]:
    triggered = []
    for agent, m in metrics.items():
        if (
            m["retry_rate"] > RETRY_RATE_THRESH
            or m["max_session_tokens"] > SESSION_TOKENS_THRESH
            or m["error_rate"] > ERROR_RATE_THRESH
            or m["tokens_in"] > TOKENS_IN_THRESH
        ):
            triggered.append(agent)
    return triggered


def main() -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=WINDOW_MINUTES)
    rows = load_recent_rows(since)
    if not rows:
        return
    metrics = compute_metrics(rows)
    triggered = check_thresholds(metrics)
    if not triggered:
        return
    active = load_active()
    active = {k: v for k, v in active.items() if is_recent(v)}
    new_active = dict(active)
    for agent in triggered:
        if agent in active:
            print(f"[watchdog] skip {agent}: active investigation <{DEDUP_MINUTES}min", file=sys.stderr)
            continue
        m = metrics[agent]
        print(f"[watchdog] ANOMALY {agent}: retry={m['retry_rate']:.0%} err={m['error_rate']:.0%} tok={m['tokens_in']:,} sess={m['max_session_tokens']:,}")
        new_active[agent] = now.isoformat()
        subprocess.Popen([sys.executable, str(INVESTIGATOR), "--agent", agent, "--since", since.isoformat()])
    save_active(new_active)


if __name__ == "__main__":
    main()
