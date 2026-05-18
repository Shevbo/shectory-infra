"""
Censor Exporter — reads Lineman request_log, writes enriched JSONL to ~/logs/censor/.

Derived metrics per row:
  body_size          — full request_size from DB (not truncated like request_body)
  context_growth_pct — % growth vs previous request from same agent/host
  retry_score        — 0.0–1.0: how similar this request is to the previous one
  session_tokens_in  — cumulative tokens_in for agent in last 60 min
  tokens_per_kb      — tokens_in / (body_size / 1024), efficiency metric

Runs as a daemon: polls every POLL_INTERVAL seconds, writes new rows only.
State persisted in state.json (last processed row id).
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "lineman" / "lineman.db"
LOG_DIR = Path.home() / "logs" / "censor"
STATE_PATH = Path(__file__).resolve().parent / "state.json"
POLL_INTERVAL = 60  # seconds
SESSION_WINDOW = 3600  # seconds for session_tokens accumulation


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"last_id": 0}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state))


def agent_key(row: dict) -> str:
    return f"{row.get('source_host') or 'unknown'}:{row.get('source_agent') or 'unknown'}"


def retry_score(body_a: str | None, body_b: str | None, size_a: int, size_b: int) -> float:
    if not body_a or not body_b:
        if size_a and size_b:
            ratio = min(size_a, size_b) / max(size_a, size_b)
            return round(ratio if ratio > 0.9 else 0.0, 3)
        return 0.0
    hash_a = hashlib.sha256(body_a.encode()).hexdigest()
    hash_b = hashlib.sha256(body_b.encode()).hexdigest()
    if hash_a == hash_b:
        return 1.0
    # size-based similarity
    if size_a and size_b:
        ratio = min(size_a, size_b) / max(size_a, size_b)
        return round(ratio if ratio > 0.85 else 0.0, 3)
    return 0.0


def fetch_new_rows(conn: sqlite3.Connection, last_id: int) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, timestamp, source_host, source_agent, llm_provider, llm_model,
               request_body, request_size, tokens_in, tokens_out,
               status_code, error, latency_ms, cache_hit,
               compression_applied, tail_tokens_before, tail_tokens_after
        FROM request_log
        WHERE id > ? AND (tokens_in IS NOT NULL OR request_size IS NOT NULL)
        ORDER BY id ASC
        LIMIT 1000
        """,
        (last_id,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def enrich(rows: list[dict]) -> list[dict]:
    # per-agent state: last body, last size, last timestamp, session token accumulator
    agent_last: dict[str, dict] = {}
    # session window: list of (ts_epoch, tokens_in) per agent
    agent_session: dict[str, list] = defaultdict(list)

    result = []
    for row in rows:
        key = agent_key(row)
        ts_str = row.get("timestamp") or ""
        try:
            ts_epoch = datetime.fromisoformat(ts_str).timestamp()
        except Exception:
            ts_epoch = time.time()

        body_size = row.get("request_size") or 0
        tokens_in = row.get("tokens_in") or 0
        body_text = row.get("request_body")

        prev = agent_last.get(key)

        # context_growth_pct
        if prev and prev["body_size"] > 0 and body_size > 0:
            growth = (body_size - prev["body_size"]) / prev["body_size"] * 100
            context_growth_pct = round(growth, 2)
        else:
            context_growth_pct = None

        # retry_score
        rscore = 0.0
        if prev:
            rscore = retry_score(prev["body_text"], body_text, prev["body_size"], body_size)

        # session_tokens_in (last SESSION_WINDOW seconds)
        cutoff = ts_epoch - SESSION_WINDOW
        session = agent_session[key]
        session.append((ts_epoch, tokens_in))
        session[:] = [(t, tk) for t, tk in session if t >= cutoff]
        session_tokens_in = sum(tk for _, tk in session)

        # tokens_per_kb
        tokens_per_kb = round(tokens_in / (body_size / 1024), 2) if body_size > 0 and tokens_in else None

        enriched = {
            "id": row["id"],
            "timestamp": ts_str,
            "source_host": row.get("source_host"),
            "source_agent": row.get("source_agent"),
            "llm_provider": row.get("llm_provider"),
            "llm_model": row.get("llm_model"),
            "body_size": body_size,
            "tokens_in": tokens_in,
            "tokens_out": row.get("tokens_out"),
            "status_code": row.get("status_code"),
            "error": row.get("error"),
            "latency_ms": row.get("latency_ms"),
            "cache_hit": row.get("cache_hit"),
            "context_growth_pct": context_growth_pct,
            "retry_score": rscore,
            "session_tokens_in": session_tokens_in,
            "tokens_per_kb": tokens_per_kb,
            "compression_applied": row.get("compression_applied") or 0,
            "tail_tokens_before": row.get("tail_tokens_before"),
            "tail_tokens_after": row.get("tail_tokens_after"),
        }
        result.append(enriched)

        agent_last[key] = {
            "body_size": body_size,
            "body_text": body_text,
            "ts": ts_epoch,
        }

    return result


def write_jsonl(rows: list[dict]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Group by date
    by_date: dict[str, list] = defaultdict(list)
    for row in rows:
        date = (row.get("timestamp") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        by_date[date].append(row)
    for date, date_rows in by_date.items():
        path = LOG_DIR / f"{date}.jsonl"
        with open(path, "a") as f:
            for row in date_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run() -> None:
    print(f"[censor] start — DB: {DB_PATH}, logs: {LOG_DIR}, poll: {POLL_INTERVAL}s")
    state = load_state()
    last_id = state["last_id"]

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row

    while True:
        try:
            rows = fetch_new_rows(conn, last_id)
            if rows:
                enriched = enrich(rows)
                write_jsonl(enriched)
                last_id = rows[-1]["id"]
                save_state({"last_id": last_id})
                print(f"[censor] wrote {len(enriched)} rows, last_id={last_id}")
        except Exception as exc:
            print(f"[censor] error: {exc}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()
