#!/usr/bin/env python3
"""Будильник FEDBACKUP: собирает факты и будит агента только когда есть что решать.

Рутина кодом, рассуждение агентом — то же разделение, что у Ключника. Скрипт сам
читает ночной лог и почту, и если решать нечего, НЕ делает запрос к модели вовсе:
простой должен стоить ноль. Курсор почты принадлежит скрипту и двигается только
после того, как агент ответил, иначе непрочитанное письмо похоронено навсегда
(ровно так ломался klod-dispatch, инцидент 2026-07-03).

Крон на smain: 30 3 * * * под flock + timeout.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
LOGDIR = HOME / "backups" / "logs"
CURSOR = HOME / ".fedbackup-cursor"
STATE = HOME / ".fedbackup-wake-state.json"
JOURNAL = HOME / "logs" / "klod" / "fedbackup.jsonl"
LINEMAN = "http://127.0.0.1:9090"
AGENT_CMD = "node /opt/node24/lib/node_modules/openclaw/dist/index.js"

# Маркеры, из-за которых агента надо будить даже без новой почты. Каждый означает
# конкретную поломку, уже случавшуюся: пропуск узла (sdev не бэкапился 17 дней),
# несогласованный дамп, незабэкапленный каталог, секрет в архиве, нет внешней копии.
ANOMALY = (
    re.compile(r"\[gather [^\]]+\] SKIP"),
    re.compile(r"\[db\] FAIL"),
    re.compile(r"FAILED"),
    re.compile(r"\[audit\] (?!clean)"),
    re.compile(r"rsync issues"),
)


def _jlog(**row) -> None:
    row["ts"] = datetime.now(timezone.utc).isoformat()
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def last_log() -> tuple[str, str]:
    logs = sorted(LOGDIR.glob("backup-*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return "", ""
    text = logs[-1].read_text(encoding="utf-8", errors="replace")
    return logs[-1].name, text


def anomalies(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        if any(rx.search(line) for rx in ANOMALY):
            out.append(line.strip())
    # Внешней копии нет — это не строка-ошибка, а ОТСУТСТВИЕ строки, поэтому отдельно.
    if text and "[offsite:daily] uploaded" not in text:
        out.append("нет строки [offsite:daily] uploaded — внешней копии за этот прогон нет")
    return out


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def repeat_ok(anom: list[str]) -> bool:
    """Будить ли агента на том же отклонении, что и в прошлый раз.

    Выключенный pi2 даёт одну и ту же строку SKIP каждый прогон. Повторять по ней
    рассуждение дважды в сутки — платить за уже сказанное: агент разобрал причину в
    первый раз, а эскалацию Боре делает сам скрипт бэкапа на третьем пропуске.
    Поэтому на неизменном отпечатке просыпаемся раз в семь прогонов, как и там.
    """
    fp = "|".join(sorted(anom))
    st = _state()
    if st.get("fingerprint") != fp:
        STATE.write_text(json.dumps({"fingerprint": fp, "count": 1}))
        return True
    n = int(st.get("count", 1)) + 1
    STATE.write_text(json.dumps({"fingerprint": fp, "count": n}))
    return n % 7 == 0


def cursor() -> int:
    try:
        return int(CURSOR.read_text().strip())
    except (OSError, ValueError):
        return 0


def inbox_since(since: int) -> list[dict]:
    url = f"{LINEMAN}/api/agent/fed-backup/inbox?since={since}&limit=50"
    try:
        raw = subprocess.run(
            ["curl", "-sS", "-m", "30", "--noproxy", "*", url],
            capture_output=True, text=True, timeout=40,
        ).stdout
    except subprocess.SubprocessError:
        return []
    # Ручка отдаёт ОДИН pretty-printed JSON `{"messages":[...]}`, а не JSONL: разбор по
    # строкам молча давал пустой список, курсор стоял на месте, и будильник не просыпался
    # на новой почте — просыпался только на отклонении в логе. Поймано живой пробой 2026-10-02.
    msgs: list[dict] = []
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        doc = None
    if isinstance(doc, dict) and isinstance(doc.get("messages"), list):
        msgs = [m for m in doc["messages"] if isinstance(m, dict)]
    elif isinstance(doc, list):
        msgs = [m for m in doc if isinstance(m, dict)]
    else:  # фолбэк на JSONL, если формат ручки когда-нибудь сменится обратно
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(d, dict) and "id" in d:
                msgs.append(d)
    return [m for m in msgs if int(m.get("id", 0)) > since]


def build_prompt(logname: str, tail: str, anom: list[str], msgs: list[dict]) -> str:
    parts = [
        "Ночной прогон бэкапа федерации. Разберись и действуй по своей карточке.",
        f"\nЛог: {logname}\nХвост лога:\n{tail}",
    ]
    if anom:
        parts.append("\nОтклонения, найденные скриптом (объясни причину каждого):\n- " + "\n- ".join(anom))
    else:
        parts.append("\nОтклонений по маркерам скрипт не нашёл. Это не значит, что всё цело: "
                     "проверь содержание, а не наличие слова finished.")
    if msgs:
        parts.append("\nНовые письма агентов (ответь на каждое, даже отказом):")
        for m in msgs:
            parts.append(f"\n#{m.get('id')} от {m.get('from')} ({str(m.get('ts'))[:16]}):\n{m.get('message','')}")
    parts.append("\nИтогом дай короткую сводку: что проверил, что изменил, кому ответил, "
                 "что осталось за Борисом. Границу помни: восстановление и удаление не твои.")
    return "\n".join(parts)


def main() -> int:
    logname, text = last_log()
    anom = anomalies(text)
    since = cursor()
    msgs = inbox_since(since)

    if not msgs and (not anom or not repeat_ok(anom)):
        _jlog(event="idle", log=logname, cursor=since, anomalies=anom,
              note="новой почты нет; отклонений нет либо они те же, что в прошлый раз — "
                   "модель не вызывалась")
        print("нечего решать, агент не разбужен")
        return 0

    tail = "\n".join(text.splitlines()[-25:])
    prompt = build_prompt(logname, tail, anom, msgs)
    session = f"wake-{int(time.time())}"
    # shlex.quote обязателен: в prompt лежит текст писем от агентов, то есть чужой ввод,
    # который иначе стал бы частью команды на удалённом узле.
    remote = (f"timeout 900 {AGENT_CMD} agent --agent fed-backup "
              f"--session-id {session} --message {shlex.quote(prompt)}")
    cmd = ["ssh", "-o", "ConnectTimeout=10", "sdev", remote]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=960)
    except subprocess.SubprocessError as exc:
        _jlog(event="wake_failed", log=logname, cursor=since, anomalies=anom,
              new_messages=[m.get("id") for m in msgs], error=str(exc))
        print(f"агент не ответил: {exc}")
        return 1

    ok = res.returncode == 0 and bool(res.stdout.strip())
    _jlog(event="woken" if ok else "wake_failed", log=logname, cursor=since,
          anomalies=anom, new_messages=[m.get("id") for m in msgs],
          session=session, rc=res.returncode,
          answer=res.stdout.strip()[-4000:] if ok else res.stderr.strip()[-1000:])

    if ok and msgs:
        # Курсор двигаем ТОЛЬКО после ответа агента: иначе сбой модели хоронит письма.
        CURSOR.write_text(str(max(int(m.get("id", 0)) for m in msgs)))
    print(res.stdout.strip() if ok else f"агент упал rc={res.returncode}: {res.stderr.strip()[:300]}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
