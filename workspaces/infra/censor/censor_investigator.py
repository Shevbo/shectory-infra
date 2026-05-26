"""
censor_investigator.py — evidence collector + Opus root-cause analyst.
Called by watchdog: python3 censor_investigator.py --agent <key> --since <iso-ts>
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CENSOR_DIR = Path(__file__).resolve().parent
LINEMAN_DB = CENSOR_DIR.parent / "lineman" / "lineman.db"
PATCH_APPLIER = CENSOR_DIR / "patch_applier.py"

BORIS_CHAT_ID = "36910539"
LINEMAN_TG_URL = "http://localhost:9090/api/tg/send"
CLAUDE_BIN = "/usr/bin/claude"
MAX_BODY_SAMPLES = 20
_KEY_PATTERNS = {"key", "secret", "token", "password", "apikey", "api_key"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agent", required=True)
    p.add_argument("--since", required=True)
    return p.parse_args()


def redact_keys(obj, depth: int = 0):
    if depth > 20:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if any(p in k.lower() for p in _KEY_PATTERNS) else redact_keys(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_keys(i, depth + 1) for i in obj]
    return obj


def read_config_safe(path: Path) -> str:
    if not path.exists():
        return f"[not found: {path}]"
    try:
        text = path.read_text()
    except Exception as exc:
        return f"[read error: {exc}]"
    if path.suffix == ".json":
        try:
            text = json.dumps(redact_keys(json.loads(text)), indent=2)
        except Exception:
            pass
    return text


def fetch_request_bodies(agent_key: str, since_ts: str) -> list[dict]:
    host, _, agent = agent_key.partition(":")
    try:
        conn = sqlite3.connect(str(LINEMAN_DB))
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, timestamp, tokens_in, tokens_out, status_code, error,
                   request_body, request_size, latency_ms
            FROM request_log
            WHERE source_host = ? AND source_agent = ? AND timestamp >= ?
            ORDER BY id DESC LIMIT ?
            """,
            (host, agent, since_ts, MAX_BODY_SAMPLES),
        )
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception as exc:
        print(f"[investigator] DB error: {exc}", file=sys.stderr)
        return []


def collect_configs() -> dict[str, str]:
    home = Path.home()
    openclaw = home / ".openclaw"
    configs: dict[str, str] = {}
    configs["openclaw.json"] = read_config_safe(openclaw / "openclaw.json")
    agents_dir = openclaw / "agents"
    if agents_dir.exists():
        for agent_dir in sorted(agents_dir.iterdir()):
            agent_subdir = agent_dir / "agent"
            for fname in ["config.json", "system-prompt.md", "auth-profiles.json"]:
                fpath = agent_subdir / fname
                if fpath.exists():
                    configs[f"agents/{agent_dir.name}/agent/{fname}"] = read_config_safe(fpath)
    configs["lineman/config.json"] = read_config_safe(
        home / "workspaces" / "infra" / "lineman" / "config.json"
    )
    configs[".pm2/dump.pm2"] = read_config_safe(home / ".pm2" / "dump.pm2")
    return configs


def build_opus_prompt(agent_key: str, since_ts: str, bodies: list[dict], configs: dict[str, str]) -> str:
    samples = []
    for i, b in enumerate(bodies[:5]):
        body_preview = (b.get("request_body") or "")[:2000]
        samples.append(
            f"Request {i + 1} (id={b.get('id')}, ts={b.get('timestamp')}, "
            f"tokens_in={b.get('tokens_in')}, size={b.get('request_size')}, "
            f"status={b.get('status_code')}, error={b.get('error')}):\n{body_preview}\n"
        )

    diff_section = ""
    if len(bodies) >= 2:
        first = bodies[-1].get("request_body") or ""
        last = bodies[0].get("request_body") or ""
        if first == last:
            diff_section = "First and last request bodies are IDENTICAL (strong retry indicator)."
        else:
            diff_section = f"First body (oldest):\n{first[:500]}\n\nLast body (newest):\n{last[:500]}"

    configs_text = "\n\n".join(
        f"=== {k} ===\n{v[:3000]}" for k, v in list(configs.items())[:12]
    )

    return f"""You are an LLM agent anomaly analyst. Agent "{agent_key}" triggered anomaly detection at {since_ts}.

ANOMALY EVIDENCE ({len(bodies)} samples):
{"".join(samples)}
BODY COMPARISON:
{diff_section}

SYSTEM CONFIGS:
{configs_text}

Identify the root cause. Respond with ONLY valid JSON (no markdown fences):
{{
  "root_cause": "1-3 sentences explaining the anomaly cause",
  "severity": "critical|high|medium",
  "patches": [
    {{
      "file": "/absolute/path/to/file",
      "description": "what and why",
      "type": "json_key|text_replace|file_append",
      "old": "exact current value",
      "new": "exact replacement value"
    }}
  ],
  "restart_pm2": ["process-name-if-needed"],
  "expected_improvement": "e.g. retry_rate 76% -> <5%"
}}
If no safe clear fix exists, return patches: []. Only reference files visible in SYSTEM CONFIGS above."""


def call_opus(prompt: str) -> str:
    result = subprocess.run(
        [CLAUDE_BIN, "--model", "claude-opus-4-7", "--print", "--bare"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "CLAUDE_CODE_SIMPLE": "1"},
    )
    if result.returncode != 0:
        print(f"[investigator] claude stderr: {result.stderr[:300]}", file=sys.stderr)
    return result.stdout.strip()


def parse_opus_response(text: str) -> dict | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        cleaned = "\n".join(lines[1:end])
    try:
        return json.loads(cleaned)
    except Exception as exc:
        print(f"[investigator] JSON parse error: {exc}\nRaw: {text[:300]}", file=sys.stderr)
        return None


def send_tg(text: str) -> None:
    payload = json.dumps({"chat_id": BORIS_CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(
        LINEMAN_TG_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as exc:
        print(f"[investigator] TG failed: {exc}", file=sys.stderr)


def main() -> None:
    args = parse_args()
    print(f"[investigator] {args.agent} since {args.since}")

    bodies = fetch_request_bodies(args.agent, args.since)
    print(f"[investigator] {len(bodies)} bodies, collecting configs...")
    configs = collect_configs()

    prompt = build_opus_prompt(args.agent, args.since, bodies, configs)
    print("[investigator] calling Opus...")
    raw = call_opus(prompt)
    analysis = parse_opus_response(raw)

    if not analysis:
        send_tg(
            f"[Autopilot] Аномалия: {args.agent}\n"
            f"Opus вернул невалидный JSON. Ручной разбор нужен.\n{raw[:200]}"
        )
        return

    patches = analysis.get("patches", [])
    if not patches:
        send_tg(
            f"[Autopilot] Аномалия: {args.agent}\n"
            f"Opus: {analysis.get('root_cause', '?')}\n"
            f"Автофикс не применён — причина неоднозначна.\n"
            f"Требует ручного разбора: ~/logs/censor/reports/"
        )
        return

    result = subprocess.run(
        [sys.executable, str(PATCH_APPLIER)],
        input=json.dumps({"agent": args.agent, "since": args.since, "analysis": analysis}),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"[investigator] patch_applier failed: {result.stderr}", file=sys.stderr)
        send_tg(
            f"[Autopilot] Аномалия: {args.agent}\n"
            f"Root cause: {analysis.get('root_cause')}\n"
            f"Patch_applier упал: {result.stderr[:200]}"
        )
    else:
        print(f"[investigator] done: {result.stdout.strip()}")


if __name__ == "__main__":
    main()
