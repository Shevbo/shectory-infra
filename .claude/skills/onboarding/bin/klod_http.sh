#!/usr/bin/env bash
# klod_http.sh — HTTP-запрос к Lineman с обходом для узлов без WireGuard.
#
# Скрипты онбординга ходили только напрямую на 10.66.0.1:9090. С Windows-узлов без WG
# это давало http=000, и агент видел «Klod-Access лежит целиком», хотя сервис был жив
# (omniroute@vs-code-local, 2026-09-14). У fetch_canon.sh обход через Pi был, у остальных нет.
#
# Маршруты по порядку:
#   1. напрямую на $LINEMAN_BASE (узлы WG и сам smain);
#   2. ssh-jump через Pi: curl выполняется на smain против петли 127.0.0.1:9090.
#
# Использование:
#   klod_http.sh METHOD "/api/path?query" [DATA_FILE|-] [CONTENT_TYPE]
#   KLOD_AGENT=<agent_id> — добавить X-Agent-Name (по нему считаются лимиты, напр. индекса)
# stdout — тело ответа. stderr — последняя строка "http=<код> route=<direct|ssh-jump|none>".
# Код возврата: 0 — получен HTTP-ответ (любой код), 1 — ни один маршрут не ответил.
set -uo pipefail

METHOD="${1:?usage: klod_http.sh METHOD /api/path [DATA_FILE|-] [CONTENT_TYPE]}"
PATHQ="${2:?path required}"
DATA="${3:-}"
CT="${4:-text/plain}"
BASE="${LINEMAN_BASE:-http://10.66.0.1:9090}"
TMO="${KLOD_HTTP_TIMEOUT:-8}"
JUMP="${KLOD_JUMP:-shevbo-pi}"
SMAIN="${KLOD_SMAIN:-shectory@smain}"

body_file="$(mktemp)"
data_tmp=""
cleanup() { rm -f "$body_file" ${data_tmp:+"$data_tmp"}; }
trap cleanup EXIT

if [[ "$DATA" == "-" ]]; then
  data_tmp="$(mktemp)"
  cat >"$data_tmp"
  DATA="$data_tmp"
fi

# 1. Напрямую.
direct_args=(-sS --noproxy '*' --max-time "$TMO" -o "$body_file" -w '%{http_code}' -X "$METHOD")
[[ -n "$DATA" ]] && direct_args+=(--data-binary "@$DATA" -H "Content-Type: $CT")
[[ -n "${KLOD_AGENT:-}" ]] && direct_args+=(-H "X-Agent-Name: $KLOD_AGENT")
code="$(curl "${direct_args[@]}" "$BASE$PATHQ" 2>/dev/null)" || code="000"
if [[ -n "$code" && "$code" != "000" ]]; then
  cat "$body_file"
  echo "http=$code route=direct" >&2
  exit 0
fi

# 2. ssh-jump через Pi. Путь и тип передаются в одинарных кавычках: в них не бывает
# одинарных кавычек (agent_id, node, topic — идентификаторы), тело идёт через stdin.
if command -v ssh >/dev/null 2>&1; then
  remote="curl -sS --noproxy '*' --max-time $TMO -w '\\n%{http_code}' -X $METHOD"
  [[ -n "$DATA" ]] && remote="$remote --data-binary @- -H 'Content-Type: $CT'"
  [[ -n "${KLOD_AGENT:-}" ]] && remote="$remote -H 'X-Agent-Name: $KLOD_AGENT'"
  remote="$remote 'http://127.0.0.1:9090$PATHQ'"
  if [[ -n "$DATA" ]]; then
    out="$(ssh -o ConnectTimeout=6 -o BatchMode=yes -J "$JUMP" "$SMAIN" "$remote" <"$DATA" 2>/dev/null)" || out=""
  else
    out="$(ssh -o ConnectTimeout=6 -o BatchMode=yes -J "$JUMP" "$SMAIN" "$remote" </dev/null 2>/dev/null)" || out=""
  fi
  if [[ -n "$out" ]]; then
    code="${out##*$'\n'}"
    printf '%s' "${out%$'\n'*}"
    echo "http=$code route=ssh-jump" >&2
    exit 0
  fi
fi

echo "http=000 route=none" >&2
exit 1
