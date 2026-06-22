#!/usr/bin/env bash
# Shectory Auth Guard — сторож единой системы аутентификации (portal_users = источник истины).
# Владелец стандарта: Claude/Executive Advisor (см. ~/SHECTORY_AUTH_STANDARD.md).
#
# Защищает МЕХАНИЗМ auth (то, что не должно меняться в обход стандарта), НЕ мешая
# нормальному потоку регистраций:
#   1) PRIV    — привилегированные аккаунты (superadmin/admin): хэш/роль/появление/удаление → ALERT
#   2) CODE    — sha256 auth-кода (portal-auth.ts + auth-routes + bridge) → ALERT при изменении
#   3) SECRET  — отпечаток SHECTORY_AUTH_BRIDGE_SECRET → ALERT при ротации
#   4) HEALTH  — web-логин жив (junk→4xx) + у superadmin непустой хэш
#   5) USERS   — счётчик обычных (role=user) логируется, БЕЗ тревоги (это и есть поток регистраций)
# НЕ хранит и НЕ печатает секретов (только sha256-отпечатки).
set -u

PORTAL_DIR="$HOME/workspaces/projects/CursorRPA/shectory-portal"
BDIR="$HOME/keymaster/auth-baseline"; mkdir -p "$BDIR"; chmod 700 "$BDIR"
PRIV_BASE="$BDIR/priv.baseline"
CODE_BASE="$BDIR/code.baseline"
SECRET_BASE="$BDIR/secret.baseline"
LOGDIR="$HOME/logs/auth-guard"; mkdir -p "$LOGDIR"
LOG="$LOGDIR/auth-guard.log"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
BORIS_CHAT="36910539"

log(){ echo "[$TS] $*" >> "$LOG"; }
alert(){
  local msg="$1"; log "ALERT: $msg"
  local payload; payload="$(python3 -c 'import json,sys;print(json.dumps({"account":"default","chat_id":"'"$BORIS_CHAT"'","text":"🔴 AUTH-GUARD: "+sys.argv[1]}))' "$msg")"
  curl -s --max-time 12 -X POST http://127.0.0.1:9090/api/tg/send -H 'Content-Type: application/json' -d "$payload" >/dev/null 2>&1
}

DBURL="$(grep -E '^DATABASE_URL=' "$PORTAL_DIR/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"')"
DBCLEAN="${DBURL%%\?*}"
[ -n "$DBCLEAN" ] || { alert "не найден DATABASE_URL портала — сторож слеп"; exit 2; }

# --- 1) PRIV: привилегированные аккаунты ---
PRIV="$(psql "$DBCLEAN" -At -F'|' -c "SELECT email, role, encode(sha256(coalesce(password_hash,'')::bytea),'hex') FROM portal_users WHERE role IN ('superadmin','admin') ORDER BY email;" 2>>"$LOG")"
[ -n "$PRIV" ] || { alert "0 привилегированных аккаунтов или БД недоступна — аномалия"; exit 2; }
if [ ! -f "$PRIV_BASE" ]; then printf '%s\n' "$PRIV" > "$PRIV_BASE"; chmod 600 "$PRIV_BASE"; log "PRIV baseline создан"; \
elif [ "$PRIV" != "$(cat "$PRIV_BASE")" ]; then
  alert "изменены привилегированные аккаунты (хэш/роль/состав superadmin|admin). Если это не ты — кто-то правит auth в обход стандарта. baseline НЕ тронут."
else log "OK priv"; fi

# --- 2) CODE: целостность auth-кода ---
CODE_NOW="$(cd "$PORTAL_DIR" && cat src/lib/portal-auth.ts src/app/api/auth/login/route.ts src/app/api/auth/register/confirm/route.ts src/app/api/auth/register/request-code/route.ts src/app/api/auth/set-initial-password/route.ts src/app/api/auth/forgot/confirm/route.ts src/app/api/internal/verify-portal-credentials/route.ts 2>/dev/null | sha256sum | cut -d' ' -f1)"
if [ ! -f "$CODE_BASE" ]; then echo "$CODE_NOW" > "$CODE_BASE"; chmod 600 "$CODE_BASE"; log "CODE baseline создан ($CODE_NOW)"; \
elif [ "$CODE_NOW" != "$(cat "$CODE_BASE")" ]; then
  alert "изменён auth-КОД портала (portal-auth.ts/routes/bridge). Любая правка auth — только через стандарт. baseline НЕ тронут (обнови вручную после ревью)."
else log "OK code"; fi

# --- 3) SECRET: отпечаток bridge-секрета ---
SECRET_FP="$(grep -E '^SHECTORY_AUTH_BRIDGE_SECRET=' "$PORTAL_DIR/.env" 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d '\n' | sha256sum | cut -c1-16)"
if [ ! -f "$SECRET_BASE" ]; then echo "$SECRET_FP" > "$SECRET_BASE"; chmod 600 "$SECRET_BASE"; log "SECRET baseline создан"; \
elif [ "$SECRET_FP" != "$(cat "$SECRET_BASE")" ]; then
  alert "ротирован SHECTORY_AUTH_BRIDGE_SECRET на портале. Потребители (гарден/STL/дашборд/ourdiary) сломаются, пока секрет не синхронизирован. baseline НЕ тронут."
else log "OK secret"; fi

# --- 4) HEALTH ---
CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST http://127.0.0.1:3000/api/auth/login -H 'Content-Type: application/json' -d '{"email":"healthprobe@shectory.local","password":"x"}' 2>>"$LOG")"
case "$CODE" in 40*) log "OK health: login alive (HTTP $CODE)";; *) alert "web-логин портала HTTP $CODE (ожидался 4xx) — /api/auth/login деградировал";; esac
ADMIN_PW="$(psql "$DBCLEAN" -At -c "SELECT CASE WHEN password_hash IS NULL THEN 'NULL' ELSE 'SET' END FROM portal_users WHERE role='superadmin' LIMIT 1;" 2>>"$LOG")"
[ "$ADMIN_PW" = "SET" ] || alert "у superadmin пустой password_hash — вход сломан"

# --- 4b) SMTP: доставка кодов регистрации (молчаливо ломалась — теперь под надзором) ---
SMTP_RES="$(cd "$PORTAL_DIR" 2>/dev/null && timeout 25 node -e '
const {loadEnvConfig}=require("@next/env"); loadEnvConfig(process.cwd());
const nm=require("nodemailer");
if(!process.env.SMTP_HOST){console.log("SKIP");process.exit(0)}
const t=nm.createTransport({host:process.env.SMTP_HOST,port:Number(process.env.SMTP_PORT||587),secure:false,auth:{user:process.env.SMTP_USER,pass:process.env.SMTP_PASSWORD},tls:{rejectUnauthorized:false},connectionTimeout:18000,greetingTimeout:18000,socketTimeout:20000});
t.verify().then(()=>{console.log("OK");process.exit(0)}).catch(e=>{console.log("FAIL:"+e.message);process.exit(0)});
' 2>/dev/null)"
case "$SMTP_RES" in
  OK)   log "OK smtp: auth портала проходит";;
  SKIP) log "smtp: SMTP_HOST не задан — пропуск";;
  *)    alert "SMTP-логин портала НЕ проходит ($SMTP_RES) — коды регистрации НЕ доставляются. Проверь пароль ящика portal@shectory.ru vs keymaster EMAIL_PASSWORD_PORTAL.";;
esac

# --- 5) USERS: поток регистраций (инфо, без тревоги) ---
NU="$(psql "$DBCLEAN" -At -c "SELECT count(*) FROM portal_users WHERE role='user';" 2>>"$LOG")"
NV="$(psql "$DBCLEAN" -At -c "SELECT count(*) FROM portal_users WHERE role='user' AND email_verified_at IS NOT NULL;" 2>>"$LOG")"
log "USERS: role=user всего=$NU подтверждённых=$NV"
exit 0
