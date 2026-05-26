"""
Censor Analyzer — runs every 6h, reads last 6h of JSONL,
asks DeepSeek Pro to produce aggregated findings + optimization plan,
writes report to ~/logs/censor/reports/ and sends digest to Telegram.

Invoked by crontab: */30 * * * * python3 /path/to/censor_analyzer.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

LOG_DIR = Path.home() / "logs" / "censor"
REPORT_DIR = LOG_DIR / "reports"
LINEMAN_TG_URL = "http://localhost:9090/api/tg/send"
DEEPSEEK_CHAT_URL = "https://api.deepseek.com/v1/chat/completions"
WINDOW_MINUTES = 360

# Thresholds for flagging
RETRY_SCORE_WARN = 0.85
GROWTH_PCT_WARN = 30.0
SESSION_TOKENS_WARN = 500_000


def get_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    try:
        profiles_path = Path.home() / ".openclaw/agents/main/agent/auth-profiles.json"
        d = json.loads(profiles_path.read_text())
        return d["profiles"]["deepseek:default"]["key"]
    except Exception:
        pass
    return ""


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
                    ts = row.get("timestamp", "")
                    if ts >= since.isoformat():
                        rows.append(row)
                except Exception:
                    pass
    return rows


def aggregate(rows: list[dict]) -> dict:
    if not rows:
        return {}

    agents: dict[str, dict] = defaultdict(lambda: {
        "requests": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "errors": 0,
        "high_retry": 0,
        "high_growth": [],
        "max_session_tokens": 0,
        "body_sizes": [],
    })

    for r in rows:
        key = f"{r.get('source_host') or '?'}:{r.get('source_agent') or '?'}"
        a = agents[key]
        a["requests"] += 1
        a["tokens_in"] += r.get("tokens_in") or 0
        a["tokens_out"] += r.get("tokens_out") or 0
        if r.get("error"):
            a["errors"] += 1
        if (r.get("retry_score") or 0) >= RETRY_SCORE_WARN:
            a["high_retry"] += 1
        growth = r.get("context_growth_pct")
        if growth and growth > GROWTH_PCT_WARN:
            a["high_growth"].append(round(growth, 1))
        sess = r.get("session_tokens_in") or 0
        if sess > a["max_session_tokens"]:
            a["max_session_tokens"] = sess
        bs = r.get("body_size") or 0
        if bs:
            a["body_sizes"].append(bs)

    summary = {}
    for key, a in agents.items():
        avg_bs = round(sum(a["body_sizes"]) / len(a["body_sizes"])) if a["body_sizes"] else None
        summary[key] = {
            "requests": a["requests"],
            "tokens_in": a["tokens_in"],
            "tokens_out": a["tokens_out"],
            "errors": a["errors"],
            "high_retry_count": a["high_retry"],
            "high_growth_events": a["high_growth"],
            "max_session_tokens_1h": a["max_session_tokens"],
            "avg_body_size_bytes": avg_bs,
        }

    total_tokens_in = sum(a["tokens_in"] for a in summary.values())
    total_requests = sum(a["requests"] for a in summary.values())

    return {
        "window_minutes": WINDOW_MINUTES,
        "total_requests": total_requests,
        "total_tokens_in": total_tokens_in,
        "agents": summary,
    }


SYSTEM_PROMPT = """Ты — аналитик эффективности LLM-агентов. Тебе даётся агрегат за 6 часов работы агентов через Lineman-прокси.

Твоя задача:
1. Выявить патологии: петли ретраев, бесконтрольный рост контекста, расточительное потребление токенов.
2. Назвать конкретных нарушителей (agent:host).
3. Для каждого нарушителя — одно конкретное действие по исправлению (system prompt правка, добавление лимита, circuit breaker порог, etc).
4. Общий итог: сколько токенов потрачено нецелесообразно и оценка экономии при исправлении.

Формат ответа — Markdown, кратко. Не более 600 слов.
Секции: ## Патологии | ## Рекомендации | ## Итог"""


def call_deepseek(api_key: str, agg: dict) -> str:
    payload = {
        "model": "deepseek-v4-pro",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"```json\n{json.dumps(agg, ensure_ascii=False, indent=2)}\n```"},
        ],
        "max_tokens": 1024,
        "temperature": 0.3,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        DEEPSEEK_CHAT_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            return body["choices"][0]["message"]["content"]
    except Exception as exc:
        return f"[DeepSeek error: {exc}]"


def save_report(ts: datetime, agg: dict, analysis: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    slug = ts.strftime("%Y-%m-%d_%H-%M")
    path = REPORT_DIR / f"{slug}.md"
    content = f"""# Censor Report — {slug}

**Window:** last {WINDOW_MINUTES} min
**Requests:** {agg.get('total_requests', 0)}
**Tokens in:** {agg.get('total_tokens_in', 0):,}

## Agent Summary

| Agent | Requests | Tokens In | Retries | Max Session |
|-------|----------|-----------|---------|-------------|
"""
    for agent, a in (agg.get("agents") or {}).items():
        content += f"| {agent} | {a['requests']} | {a['tokens_in']:,} | {a['high_retry_count']} | {a['max_session_tokens_1h']:,} |\n"

    content += f"\n## DeepSeek Analysis\n\n{analysis}\n"
    path.write_text(content)
    return path


BORIS_CHAT_ID = "36910539"


def send_tg(text: str) -> None:
    payload = json.dumps({"chat_id": BORIS_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        LINEMAN_TG_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"[censor] TG send failed: {exc}", file=sys.stderr)


def build_tg_digest(ts: datetime, agg: dict, analysis: str, report_path: Path) -> str:
    total_tok = agg.get("total_tokens_in", 0)
    total_req = agg.get("total_requests", 0)
    agents_str = ""
    for agent, a in list((agg.get("agents") or {}).items())[:5]:
        flags = []
        if a["high_retry_count"]:
            flags.append(f"retries:{a['high_retry_count']}")
        if a["high_growth_events"]:
            flags.append(f"growth:{len(a['high_growth_events'])}x")
        if a["max_session_tokens_1h"] > SESSION_TOKENS_WARN:
            flags.append(f"sess:{a['max_session_tokens_1h']//1000}k")
        flag_str = " ".join(flags) if flags else "ok"
        agents_str += f"  {agent}: {a['tokens_in']:,} tok [{flag_str}]\n"

    # First 3 lines of analysis for TG preview
    preview = "\n".join(analysis.strip().splitlines()[:6])

    return (
        f"Censor {ts.strftime('%H:%M')} ({WINDOW_MINUTES}m)\n"
        f"Запросов: {total_req} | Tokens in: {total_tok:,}\n\n"
        f"{agents_str}\n"
        f"{preview}\n\n"
        f"Отчёт: {report_path}"
    )


def main() -> None:
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=WINDOW_MINUTES)

    print(f"[censor-analyzer] {now.isoformat()} — loading rows since {since.isoformat()}")

    rows = load_recent_rows(since)
    print(f"[censor-analyzer] {len(rows)} rows loaded")

    if not rows:
        print("[censor-analyzer] no data, skipping")
        return

    agg = aggregate(rows)

    api_key = get_deepseek_key()
    if not api_key:
        print("[censor-analyzer] DEEPSEEK key not found", file=sys.stderr)
        analysis = "[no API key]"
    else:
        print("[censor-analyzer] calling DeepSeek Pro...")
        analysis = call_deepseek(api_key, agg)

    report_path = save_report(now, agg, analysis)
    print(f"[censor-analyzer] report saved: {report_path}")

    digest = build_tg_digest(now, agg, analysis, report_path)
    send_tg(digest)
    print("[censor-analyzer] done")


if __name__ == "__main__":
    main()
