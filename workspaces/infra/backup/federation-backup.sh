#!/usr/bin/env bash
# federation-backup.sh — disaster-recovery backup of the whole Shectory federation.
# Runs on smain. Gathers every node over WG, snapshots incrementally, encrypts for
# offsite, and keeps media/temp as a single FULL copy.
#
# Design (approved 2026-07-24, retention re-architected 2026-09-07):
#   - Incremental: rsync --link-dest hardlinks. Unchanged files cost 0 bytes; every dated
#     snapshot is still a full, browsable restore point. Pruning frees only unreferenced data.
#   - RETENTION DEPTH LIVES ON GOOGLE DRIVE, NOT ON smain. smain's disk is a shared production
#     resource (Lineman, Klod, mail, portal) and hit 90% full holding a local 15-snapshot GFS
#     chain. Locally we now keep exactly ONE daily (just enough to --link-dest tomorrow's diff);
#     the real 6 daily / 5 weekly / 4 monthly history is three subfolders on Drive
#     (gdrive-master:federation-backup/{daily,weekly,monthly}), each rotated independently.
#   - Media + temp: ONE full copy (media-full/), overwritten each run, never versioned.
#   - Excludes: vendor/regenerable (node_modules, venv, build, caches, SDKs, downloadable
#     archives/installers) AND all secret material (canon §7) — raw keys/values never archived.
#   - Offsite: gpg AES-256 (pass=BACKUP_ZIP_PASS from Keymaster, fetched at runtime, never stored).
#     Restore re-provisions all secrets via Keymaster — see RESTORE_PROMPT.md.
set -uo pipefail

### ---- config ---------------------------------------------------------------
DEST="${FED_BK_DEST:-/home/shectory/backups/federation}"   # local working copy (1 daily only)
STAGE="${FED_BK_STAGE:-/home/shectory/backups/.stage}"     # live gather mirror (current state)
MEDIA="${FED_BK_MEDIA:-/home/shectory/backups/media-full}" # FULL-once tier (single copy)
LOGDIR="${FED_BK_LOG:-/home/shectory/backups/logs}"
OFFSITE="${FED_BK_OFFSITE:-/home/shectory/backups/offsite}" # transient: built, uploaded, then deleted
DUMPS="${FED_BK_DUMPS:-/home/shectory/backups/db-dumps}"    # big DB dumps: own rotation, not versioned
KEEP_DUMPS=1   # один дамп: каждый ~1ГБ и растёт, диск smain - узкое место

# Локальная глубина: 1 daily и ноль weekly/monthly (см. заголовок файла, 2026-09-07).
KEEP_DAILY=1; KEEP_WEEKLY=0; KEEP_MONTHLY=0
# Глубина на Google Drive — вот тут теперь живёт настоящий GFS.
DRIVE_KEEP_DAILY=6; DRIVE_KEEP_WEEKLY=5; DRIVE_KEEP_MONTHLY=4

KM="http://127.0.0.1:9093"
REQUESTER="fed-backup"
RCLONE_REMOTE="${FED_BK_RCLONE:-gdrive-master:federation-backup}"  # 400GB account; the 15GB one is not used
TODAY="$(TZ=Europe/Moscow date +%F)"
TS="$(TZ=Europe/Moscow date '+%F %H:%M MSK')"
mkdir -p "$DEST"/{daily,weekly,monthly} "$STAGE" "$MEDIA" "$LOGDIR" "$OFFSITE" "$DUMPS"
LOG="$LOGDIR/backup-$(TZ=Europe/Moscow date +%Y%m%d-%H%M%S).log"
log(){ echo "$(TZ=Europe/Moscow date '+%H:%M:%S')  $*" | tee -a "$LOG"; }
rclone_bin(){ command -v rclone 2>/dev/null || echo "$HOME/bin/rclone"; }

### ---- nodes to gather:  label ssh-host src-path  (ssh-host 'local' = this box) ----
NODES=(
  "smain local  /home/shectory/workspaces"
  "sdev  sdev   workspaces"
  "hoster hoster workspaces"
  "pi2   pi2    ."          # у pi2 нет ~/workspaces: там claude-smarthome, vpn-state, конфиги роутера
)

### ---- excludes -------------------------------------------------------------
# vendor / regenerable (re-downloadable from the manufacturer) + build output + caches
VENDOR_EX=(
  node_modules .venv venv env __pycache__ .pytest_cache .mypy_cache
  dist build target out .next .nuxt .svelte-kit .cache .turbo .parcel-cache
  .gradle .mvn .m2 .cargo/registry go/pkg vendor/bundle .bundle .toolchain Distr
  .vscode-server/bin .vscode-server/extensions
  mariadb mysql postgresql   # raw DB datadirs: unreadable live + inconsistent if copied; dumped instead
)
VENDOR_EX_GLOB=( '*.zip' '*.7z' '*.tar.gz' '*.tgz' '*.tar.xz' '*.iso' '*.deb' '*.rpm'
  '*.appimage' '*.exe' '*.msi' '*.dmg' '*.jar' '*.whl' '*.gem' '*.nupkg' '*.apk' )
# secrets — NEVER archived (canon §7); restore re-provisions via Keymaster
SECRET_EX=( '.env' '.env.*' '*.env' '*.env.*' '*.pem' '*.key' '*.p12' '*.pfx' 'id_rsa' 'id_rsa.*'
  'key'   # файл РОВНО с именем key: bfss-preask/data/key (32 байта) уезжал в архив открытым —
          # маска '*.key' такое имя не ловит. Канон §7: сырого секрета в архиве быть не может.
  'id_ed25519' 'id_ed25519.*' '.keymaster' 'openclaw.json' '.credentials.json'
  'credentials.json' '*.secret' '.aws' '.gnupg' 'known_hosts' 'authorized_keys' )
# media + temp — go to the FULL-once tier, excluded from the versioned tier
MEDIA_GLOB=( '*.jpg' '*.jpeg' '*.png' '*.gif' '*.webp' '*.bmp' '*.tif' '*.tiff' '*.svg'
  '*.ico' '*.psd' '*.heic' '*.pdf' '*.mp4' '*.mov' '*.mkv' '*.avi' '*.webm' '*.m4v'
  '*.mp3' '*.wav' '*.flac' '*.m4a' '*.ogg' '*.aac' )
TEMP_GLOB=( '*.tmp' '*.temp' '*.log' '*.bak' '*.swp' '*.old' 'core.*' )

build_ex(){ # emits rsync --exclude args from the given arrays
  local a; for a in "${VENDOR_EX[@]}";      do printf -- '--exclude=%s/\n' "$a"; done
  for a in "${VENDOR_EX_GLOB[@]}"; do printf -- '--exclude=%s\n' "$a"; done
  for a in "${SECRET_EX[@]}";      do printf -- '--exclude=%s\n' "$a"; done
}
mapfile -t EX_COMMON < <(build_ex)
mapfile -t EX_MEDIA  < <(for a in "${MEDIA_GLOB[@]}" "${TEMP_GLOB[@]}"; do printf -- '--exclude=%s\n' "$a"; done)

### ---- 1. gather each node -> STAGE/<label> (current mirror, vendor+secrets stripped) ----
# Холодный WireGuard-туннель требует handshake: первый коннект к pi2 занимает 8.1с против 3.1с
# на прогретом. Лимит в 8с не укладывался и давал ложный SKIP каждую ночь 7 раз подряд,
# пока узел был жив. Греем канал пингом, даём запас по времени и одну повторную попытку.
node_reachable(){
  local host="$1" i err png
  # Туннель к домашним узлам засыпает: первый пакет поднимает WG-handshake.
  # Отдельно фиксируем результат пинга — он отличает "узел выключен" от "ssh не пускает",
  # иначе в логе остаётся бесполезное "таймаут" и непонятно, чинить сеть или доступы.
  if ping -c2 -W5 "$host" >/dev/null 2>&1; then png="пинг проходит"; else png="пинг НЕ проходит (узел выключен или нет маршрута)"; fi
  for i in 1 2 3; do
    err=$(timeout 30 ssh -o BatchMode=yes -o ConnectTimeout=20 "$host" true 2>&1) && return 0
    sleep 3
  done
  log "[reach $host] недоступен: $png; ssh: ${err:-таймаут без ответа}"
  return 1
}

gather_node(){
  local label="$1" host="$2" src="$3"
  local dst="$STAGE/$label"
  mkdir -p "$dst"
  if [ "$host" = local ]; then
    rsync -a --delete --delete-excluded "${EX_COMMON[@]}" "${EX_STL_CLONE[@]}" "$src/" "$dst/" 2>>"$LOG" \
      && { rm -f "$LOGDIR/.skip-$label" 2>/dev/null; log "[gather $label] ok ($(du -sh "$dst" 2>/dev/null | cut -f1))"; } \
      || log "[gather $label] rsync issues (see log)"
  else
    if node_reachable "$host"; then
      rsync -a --delete --delete-excluded -e 'ssh -o BatchMode=yes -o ConnectTimeout=8' \
        "${EX_COMMON[@]}" "$host:$src/" "$dst/" 2>>"$LOG" \
        && { rm -f "$LOGDIR/.skip-$label" 2>/dev/null; log "[gather $label] ok ($(du -sh "$dst" 2>/dev/null | cut -f1))"; } \
        || log "[gather $label] rsync issues (see log)"
    else
      # Пропуск узла не должен выглядеть как успешный прогон: sdev не бэкапился 17 дней,
      # pi2 - вообще никогда, а итог каждый раз был "success". Считаем пропуски подряд
      # и на третьем сообщаем Борису, дальше напоминаем каждый десятый.
      local skipf="$LOGDIR/.skip-$label"
      local n=$(( $(cat "$skipf" 2>/dev/null || echo 0) + 1 ))
      echo "$n" > "$skipf"
      log "[gather $label] SKIP: $host недоступен (подряд: $n)"
      if [ "$n" -eq 3 ] || [ $((n % 10)) -eq 0 ]; then
        curl -sS --max-time 8 -X POST "http://10.66.0.1:9090/api/tg/send" -H 'Content-Type: application/json' \
          -d "{\"account\":\"default\",\"text\":\"FEDBACKUP: узел $label не попадает в бэкап уже $n прогонов подряд. Данные этого узла не защищены.\"}" >/dev/null 2>&1 || true
      fi
    fi
  fi
}

### ---- 1b. extra paths outside ~/workspaces (reported by agents as backup gaps) ----
# label host  remote-path(home-relative)   stage-subdir   — extend as agents report gaps to FEDBACKUP.
EXTRAS=(
  "stl hoster apps/shectory-trader stl/apps-shectory-trader"
  "stl hoster robot_logs           stl/robot_logs"
  "stl hoster quik_build           stl/quik_build"
  # ragkit (критический RAG-демон sdev, 2026-09-12): живёт в ~/ragkit, а не в ~/workspaces,
  # и у него НЕТ git-remote — исходники существуют ровно в одном экземпляре, на sdev.
  "rag sdev  ragkit                rag/ragkit"
  "rag sdev  /etc/systemd/system   rag/systemd-system"
)
# STL-specific regenerable bulk (klod-stl doc 2026-07-25): backtest artifacts + published
# release zips + derived bars/graph. Reproducible from Postgres + code, so excluded from the
# versioned tier — logged below so the drop is never silent.
# Клон STL в ~/workspaces: история целиком есть на GitHub, в бэкапе не нужна.
EX_STL_CLONE=( --exclude=/STL/.git/ )

STL_EX=( --exclude=agent_bars/ --exclude=graphify-out/ --exclude=agent_release/ --exclude=data/ai46_bt/ )

# ragkit: берём целиком, кроме .venv (уже в VENDOR_EX). index/ формально производное, но
# пересборка STL-индекса — 4730с (79 мин, 6662 чанка) плюс докачка модели e5-large с
# HuggingFace, т.е. восстановление получало бы +1.5ч к RTO (сейчас 14 мин) и зависимость от
# стороннего хоста. 65М на архив в 2.7Г — дешевле. ~/ragkit-src (224М, read-only клон STL)
# не берём: это git, поднимается ragkit-src-pull.
RAG_EX=()

gather_extras(){
  local spec label host rpath sub dst
  for spec in "${EXTRAS[@]}"; do
    read -r label host rpath sub <<<"$spec"
    dst="$STAGE/$sub"
    if ! node_reachable "$host"; then
      log "[extra $sub] SKIP: $host unreachable"; continue
    fi
    mkdir -p "$dst"
    local ex=(); case "$label" in stl) ex=("${STL_EX[@]}");; rag) ex=("${RAG_EX[@]}");; esac
    rsync -a --delete --delete-excluded -e 'ssh -o BatchMode=yes -o ConnectTimeout=8' \
      "${EX_COMMON[@]}" "${ex[@]}" "$host:$rpath/" "$dst/" 2>>"$LOG" \
      && log "[extra $sub] ok ($(du -sh "$dst" 2>/dev/null | cut -f1))" \
      || log "[extra $sub] rsync issues (see log)"
  done
  log "[extra] excluded as regenerable: agent_bars, graphify-out, agent_release, data/ai46_bt"
  log "[extra] ragkit: index/ включён намеренно (пересборка 79 мин + модель с HF); ragkit-src опущен (git)"
}

# Loose operational scripts/journals living directly in hoster's home (outside any repo).
gather_hoster_ops(){
  local dst="$STAGE/stl/ops"
  node_reachable hoster || { log "[stl-ops] SKIP: hoster unreachable"; return; }
  mkdir -p "$dst"
  # include-filters over hoster's home: a multi-glob in one remote arg is passed as a single path
  # by rsync and fails. The trailing --exclude='*' also stops descent, so only top-level ops
  # files come across (do NOT add --no-recursive: it makes rsync skip the directory entirely).
  rsync -a -e 'ssh -o BatchMode=yes -o ConnectTimeout=8' \
    --exclude='*.bak' --exclude='*.bak-*' --exclude='*.bak.*' \
    --include='stl-*.sh' --include='stl-*.json' --include='stl-*.jsonl' \
    --include='robot_watch*.sh' --include='publish_quik_agent.sh' --exclude='*' \
    hoster:./ "$dst/" 2>>"$LOG" \
    && log "[stl-ops] scripts+journals ok ($(ls -1 "$dst" | wc -l) files)" \
    || log "[stl-ops] FAILED to fetch watchdog scripts/journals"
  ssh -o BatchMode=yes -o ConnectTimeout=8 hoster 'crontab -l' > "$dst/crontab.txt" 2>>"$LOG" \
    && log "[stl-ops] crontab captured"
}

# Postgres on hoster: algo_trades (real-money fill journal) is NOT reproducible. The DSN is read
# from the node's own env at runtime and never leaves it; only the dump travels.
gather_hoster_pg(){
  # Kept OUTSIDE the versioned tier on purpose: a fresh ~900MB gzip every night is byte-different,
  # so --link-dest cannot dedupe it and GFS would pin many distinct copies. Own rotation
  # (KEEP_DUMPS) caps it instead; DR uses the newest dump alongside the newest snapshot.
  local out="$DUMPS/hoster-stl-postgres-$TODAY.sql.gz"
  mkdir -p "$(dirname "$out")"
  node_reachable hoster || { log "[stl-pg] SKIP: hoster unreachable"; return; }
  if ssh -o BatchMode=yes -o ConnectTimeout=10 hoster \
       'set -a; . ~/.shectory_trade.env 2>/dev/null; set +a; [ -n "$LAB_DB_URL" ] || exit 3; pg_dump "$LAB_DB_URL" --no-owner --no-privileges | gzip -6' \
       > "$out.tmp" 2>>"$LOG" && [ -s "$out.tmp" ]; then
    mv "$out.tmp" "$out"; log "[stl-pg] pg_dump ok ($(du -sh "$out" | cut -f1)) -> db-dumps/"
  else
    rm -f "$out.tmp"; log "[stl-pg] FAILED — algo_trades NOT backed up (check LAB_DB_URL / pg_dump on hoster)"
  fi
  ls -1t "$DUMPS"/hoster-stl-postgres-*.sql.gz 2>/dev/null | tail -n +$((KEEP_DUMPS+1)) | xargs -r rm -f
}

# sms-gateway MariaDB: шаг удалён 2026-08-11 по ответу klod-access. Сервис перепроектирован
# 05.08 — SMSGate с MariaDB на smain заменён прямым обращением к Android в LAN (~/bin/send-sms.sh).
# Контейнеров и образов больше нет, состояние живёт на телефоне, токен — в Keymaster.
# Со стороны бэкапа остаются журналы ~/logs/sms (см. SMAIN_EXTRA) и скрипты из ~/bin.

# smain paths outside ~/workspaces that a rebuild genuinely needs. The canon lives in ~/docs and
# was missing until 2026-08-02: without it a restored federation has code but no description of
# how it fits together, who the agents are, or which standards apply.
SMAIN_EXTRA=( docs keymaster klod-access memory skills logs/sms www )   # logs/sms: аудит sms-gateway (klod-access, 2026-08-05); www: лендинг agentin + ярлыки кредов Бори (agentin 2026-09-18)
gather_smain_home(){
  local dst="$STAGE/smain-home" d
  mkdir -p "$dst"
  for d in "${SMAIN_EXTRA[@]}"; do
    [ -d "$HOME/$d" ] || { log "[smain-home] $d SKIP: нет такого каталога"; continue; }
    mkdir -p "$(dirname "$dst/$d")"   # rsync не создаёт вложенные родительские каталоги (logs/sms)
    if rsync -a --delete --delete-excluded "${EX_COMMON[@]}" "$HOME/$d/" "$dst/$d/" 2>>"$LOG"; then
      log "[smain-home] $d ok ($(du -sh "$dst/$d" 2>/dev/null | cut -f1))"
    else
      log "[smain-home] $d FAILED — не забэкаплено"   # молчаливый пропуск недопустим
    fi
  done
  # Operational shell scripts from ~/bin (send-sms.sh, sms-gateway-doctor.sh and friends).
  # Only *.sh: the rest of ~/bin is 76MB of compiled binaries that reinstall from upstream.
  mkdir -p "$dst/bin"
  rsync -a --delete --include='*.sh' --exclude='*' "$HOME/bin/" "$dst/bin/" 2>>"$LOG" \
    && log "[smain-home] bin scripts ok ($(ls -1 "$dst/bin" 2>/dev/null | wc -l) шт.)"

  # systemd unit BODIES, not just the name list: rebuilding services from a manifest of names
  # is guesswork, the unit files are the actual definition.
  mkdir -p "$dst/systemd-user"
  rsync -a --delete "$HOME/.config/systemd/user/" "$dst/systemd-user/" 2>>"$LOG" \
    && log "[smain-home] systemd units ok ($(ls -1 "$dst/systemd-user" 2>/dev/null | wc -l) файлов)"
  if [ -d /etc/systemd/system ]; then
    mkdir -p "$dst/systemd-system"
    cp /etc/systemd/system/*.service "$dst/systemd-system/" 2>/dev/null
    log "[smain-home] systemd system units ($(ls -1 "$dst/systemd-system" 2>/dev/null | wc -l) файлов)"
  fi

  # nginx: 10 vhost'ов (портал, shectory.ru, sms, mail, dashboard, syslog, garden, pingmaster)
  # не были в бэкапе вообще — дыру заявил garden-living-cost 2026-09-29, подтверждена 2026-10-02.
  # Без них восстановление означает поднимать маршрутизацию и TLS-терминацию руками по памяти.
  # Берём ТОЛЬКО конфиги: сертификаты перевыпускает certbot, а .htpasswd* — хеши паролей,
  # то есть секретный материал по канону §7, и в архив им нельзя.
  if [ -d /etc/nginx ]; then
    mkdir -p "$dst/nginx"
    rsync -a --delete --exclude='.htpasswd*' --exclude='*.pem' --exclude='*.key' \
      /etc/nginx/nginx.conf /etc/nginx/sites-available /etc/nginx/conf.d \
      "$dst/nginx/" 2>>"$LOG" \
      && log "[smain-home] nginx configs ok ($(find "$dst/nginx" -type f 2>/dev/null | wc -l) файлов)" \
      || log "[smain-home] nginx configs FAILED — маршрутизация не забэкаплена"
  fi
}

### ---- 2. gather smain meta: DB dumps + sanitized configs + manifests (no secret values) ----
gather_meta(){
  local m="$STAGE/_meta"; mkdir -p "$m"/{db,config,manifest}
  # sqlite: online-consistent .backup for every known db
  local dbs=(
    ~/workspaces/infra/lineman/lineman.db ~/workspaces/infra/syslog-srv/data/syslog.db
    ~/workspaces/infra/syslog-srv/prisma/data/auth.db ~/workspaces/infra/cc-bot/history.db
    ~/workspaces/career-bot/pipeline.db ~/workspaces/career-bot/linkedin_state/queue.db
    ~/workspaces/nurse/memory/nurse_db.sqlite ~/workspaces/projects/PingMaster/data/pingmaster.db
    ~/workspaces/projects/PiranhaAI/cloud_server/data/control.db
    ~/mail-poste/data/users.db ~/mail-poste/data/dav.db ~/mail-poste/data/roundcube/roundcube.db
    # agentin (заявлен агентом agentin 2026-09-26): состояние намерений, заказов и аудит-цепочки.
    # Сырой файл и так уезжает rsync'ом из ~/workspaces, но под живым pm2 копия может быть
    # несогласованной — нужен .backup. test_core.db не берём: тестовая, воспроизводится прогоном.
    ~/workspaces/agentin/sandbox.db
  )
  local d; for d in "${dbs[@]}"; do
    [ -f "$d" ] || continue
    local out="$m/db/$(echo "${d#$HOME/}" | tr '/' '_')"
    sqlite3 "$d" ".backup '$out'" 2>>"$LOG" && log "[db] $out" || log "[db] FAIL $d"
  done
  # redis (small): trigger save then copy rdb out of the volume
  docker exec gemini-live-service-redis-1 redis-cli SAVE >/dev/null 2>&1 \
    && docker cp gemini-live-service-redis-1:/data/dump.rdb "$m/db/redis-dump.rdb" 2>>"$LOG" \
    && log "[db] redis-dump.rdb"
  # sanitized configs (public topology only, no secret values)
  cp ~/.ssh/config "$m/config/ssh_config" 2>/dev/null
  cp ~/workspaces/projects/gemini-live-service/docker-compose.yml "$m/config/" 2>/dev/null
  cp ~/mail-poste/docker-compose.yml "$m/config/mail-poste-compose.yml" 2>/dev/null
  systemctl --user list-unit-files --no-legend > "$m/manifest/systemd-user-units.txt" 2>/dev/null
  ls /etc/systemd/system/*.service > "$m/manifest/systemd-system-units.txt" 2>/dev/null
  docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}' > "$m/manifest/docker.txt" 2>/dev/null
  # Python venvs are excluded from the archive as regenerable — but nothing in the repos declares
  # WHAT to regenerate (no requirements.txt / pyproject.toml anywhere in the federation, checked
  # 2026-08-09). Without these freezes a restore cannot rebuild a working environment.
  local v name n
  while IFS= read -r v; do
    [ -x "$v/bin/python3" ] || continue
    name="$(echo "${v#$HOME/}" | tr '/' '_')"
    if "$v/bin/python3" -m pip freeze > "$m/manifest/pip-freeze-$name.txt" 2>/dev/null; then
      n=$(wc -l < "$m/manifest/pip-freeze-$name.txt")
      [ "$n" -gt 0 ] && log "[meta] pip freeze: $name ($n пакетов)" || rm -f "$m/manifest/pip-freeze-$name.txt"
    fi
  done < <(find "$HOME/workspaces" "$HOME/keymaster" -maxdepth 3 \( -name '.venv' -o -name 'venv' \) 2>/dev/null)
  # Node projects keep package-lock.json in-repo, so they are already covered.

  # Keymaster manifest = secret INVENTORY without values (what to re-provision on restore)
  curl -sS "$KM/keymaster/manifest" -o "$m/manifest/keymaster-manifest.json" 2>/dev/null \
    && log "[meta] keymaster manifest (no values)"
  log "[meta] gathered ($(du -sh "$m" 2>/dev/null | cut -f1))"
}

### ---- 3. daily snapshot: STAGE -> daily/TODAY, hardlinking from the (single) prior daily ----
newest_daily(){ ls -1d "$DEST"/daily/*/ 2>/dev/null | grep -vE "/$TODAY/\$" | sort | tail -1; }
snapshot(){
  local new="$DEST/daily/$TODAY" prev; prev="$(newest_daily)"
  local link=(); [ -n "$prev" ] && link=(--link-dest="$prev")
  mkdir -p "$new"
  rsync -a --delete "${EX_MEDIA[@]}" "${link[@]}" "$STAGE/" "$new/" 2>>"$LOG"
  log "[snapshot] daily/$TODAY built (base=${prev:-FULL})  size=$(du -sh "$new" 2>/dev/null | cut -f1), apparent"
}

### ---- 4. media/temp FULL-once: single mirror, no versioning ----
media_full(){
  # include only media+temp files (prune empty dirs), single --delete mirror
  local inc=(); local g
  for g in "${MEDIA_GLOB[@]}" "${TEMP_GLOB[@]}"; do inc+=(--include="$g"); done
  rsync -a --delete --prune-empty-dirs --include='*/' "${inc[@]}" --exclude='*' \
    "$STAGE/" "$MEDIA/" 2>>"$LOG"
  log "[media-full] single copy size=$(du -sh "$MEDIA" 2>/dev/null | cut -f1)"
}

### ---- 5. weekly / monthly (link-dest from today's daily; built locally just long enough to upload) ----
# Локально weekly/monthly не хранятся (KEEP_WEEKLY=KEEP_MONTHLY=0), поэтому "когда я последний раз
# строил weekly" нельзя узнать по содержимому папки — она всегда пустая после prune. Дата последней
# постройки живёт в отдельном маркер-файле (несколько байт, не сам снапшот).
promote(){ # $1=tier -> exit 0 если построил новый снапшот сегодня, 1 если пропустил (рано ещё)
  local tier="$1" parent="$DEST/$1" today_daily="$DEST/daily/$TODAY" want=false
  local marker="$LOGDIR/.last-$tier"
  local last; last="$(cat "$marker" 2>/dev/null || true)"
  if [ "$tier" = weekly ]; then
    if [ -z "$last" ]; then want=true
    else local age=$(( ($(date -d "$TODAY" +%s) - $(date -d "$last" +%s)) / 86400 )); [ "$age" -ge 7 ] && want=true; fi
  else # monthly
    [ "${last:0:7}" = "$(TZ=Europe/Moscow date +%Y-%m)" ] || want=true
  fi
  if $want; then
    rsync -a --delete --link-dest="$today_daily" "$today_daily/" "$parent/$TODAY/" 2>>"$LOG"
    # Маркер НЕ пишем здесь: 08.09 monthly-архив умер на ENOSPC, аплоад упал, а маркер уже
    # стоял — тир считался сделанным и не повторялся до октября. Пишет offsite() после
    # успешной загрузки, тогда неудача просто повторится завтра.
    log "[$tier] snapshot $TODAY (linked from today's daily)"
    return 0
  fi
  log "[$tier] latest is $last, skipping"
  return 1
}

### ---- 6. encrypt + push to Drive, one tier at a time; each tier keeps its own GFS depth ----
km_value(){ # $1=secret name -> value on stdout, empty if not approved
  local r; r="$(curl -sS -X POST "$KM/keymaster/request-value?name=$1&requester=$REQUESTER&purpose=federation-offsite-backup" 2>/dev/null)"
  case "$r" in *'"status": "approved"'*|*'"status":"approved"'*)
    local del; del="$(printf '%s' "$r" | grep -oE '"delivery"[: ]*"[^"]+"' | grep -oE '/[^"]+|~[^"]+' | head -1)"
    del="${del/#\~/$HOME}"; [ -f "$del" ] && cat "$del" ;;
  esac
}

offsite_tier(){ # $1=tier(daily|weekly|monthly) $2=local-src-dir $3=drive-keep-depth $4=passphrase
  local tier="$1" srcdir="$2" keep="$3" pass="$4"
  local arc="$OFFSITE/federation-$tier-$TODAY.tar.gz.gpg"
  local remote="$RCLONE_REMOTE/$tier"
  # Only the NEWEST dump per database goes offsite. Bundling the whole db-dumps rotation shipped
  # near-identical ~1GB copies in every archive — pure redundancy per upload.
  local newest_dumps; newest_dumps=$(cd "$DUMPS" 2>/dev/null && ls -1t *.sql.gz 2>/dev/null | head -1)
  if ! tar -C "$(dirname "$srcdir")" -cf - "$(basename "$srcdir")" -C "$MEDIA/.." "$(basename "$MEDIA")" \
        ${newest_dumps:+-C "$DUMPS" $newest_dumps} 2>>"$LOG" \
    | gzip -6 \
    | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase "$pass" -o "$arc" 2>>"$LOG"; then
    # ENOSPC на локальном диске (08.09) оставлял обрезанный .gpg — грузить его нельзя:
    # в Drive лёг бы архив, который не расшифруется, и это выяснилось бы только на учениях.
    log "[offsite:$tier] encrypt FAILED (место на диске? см. лог) -> аплоад отменён"
    rm -f "$arc"; return 1
  fi
  log "[offsite:$tier] encrypted $(du -sh "$arc" 2>/dev/null | cut -f1) -> $arc"

  local RC; RC="$(rclone_bin)"   # systemd timers get a bare PATH
  if [ ! -x "$RC" ]; then log "[offsite:$tier] rclone not installed -> staged locally: $arc"; return 1; fi
  if ! "$RC" listremotes 2>/dev/null | grep -q "^${RCLONE_REMOTE%%:*}:"; then
    log "[offsite:$tier] rclone remote '${RCLONE_REMOTE%%:*}' not configured -> staged locally: $arc"; return 1
  fi
  # Preflight: refuse to start an upload that cannot fit, otherwise rclone dies mid-transfer
  # and leaves a partial file eating the same space.
  local need free
  need=$(stat -c %s "$arc" 2>/dev/null || echo 0)
  free=$("$RC" about "${RCLONE_REMOTE%%:*}:" --json 2>/dev/null | grep -oE '"free":[0-9]+' | cut -d: -f2)
  if [ -n "$free" ] && [ "$need" -gt 0 ] && [ "$free" -lt "$need" ]; then
    log "[offsite:$tier] ABORT: need $((need/1024/1024))MB, free $((free/1024/1024))MB on Drive — freeing oldest in $tier first"
    "$RC" lsf "$remote" 2>/dev/null | grep "^federation-$tier-.*\.gpg\$" | sort | head -n -1 \
      | while read -r old; do "$RC" deletefile "$remote/$old" 2>>"$LOG" && log "[offsite:$tier] freed $old"; done
  fi
  local rc=1
  if "$RC" copy "$arc" "$remote" 2>>"$LOG"; then
    log "[offsite:$tier] uploaded $(du -h "$arc" | cut -f1) -> $remote"
    rc=0
    # Rotation: rclone copy only ever adds, so without this each tier's quota fills over time.
    "$RC" lsf "$remote" 2>/dev/null | grep "^federation-$tier-.*\.gpg\$" | sort | head -n -"$keep" \
      | while read -r old; do "$RC" deletefile "$remote/$old" 2>>"$LOG" && log "[offsite:$tier] rotated out $old (keep=$keep)"; done
  else
    log "[offsite:$tier] rclone upload FAILED (check remote/auth/quota)"
  fi
  # smain's disk is the binding constraint, Drive holds the depth now — never keep the local copy.
  rm -f "$arc"
  return $rc
}

offsite(){ # $1=weekly-built(0/1) $2=monthly-built(0/1)
  local weekly_built="$1" monthly_built="$2"
  local pass; pass="$(km_value BACKUP_ZIP_PASS)"
  if [ -z "$pass" ]; then log "[offsite] SKIP: BACKUP_ZIP_PASS not delivered (approve in Keymaster bot)"; return; fi
  offsite_tier daily "$DEST/daily/$TODAY" "$DRIVE_KEEP_DAILY" "$pass"
  # Маркер тира ставим только после успешного аплоада — см. комментарий в promote().
  [ "$weekly_built"  -eq 0 ] && { offsite_tier weekly  "$DEST/weekly/$TODAY"  "$DRIVE_KEEP_WEEKLY"  "$pass" \
    && echo "$TODAY" > "$LOGDIR/.last-weekly"  || log "[weekly] маркер не поставлен — тир повторится завтра"; }
  [ "$monthly_built" -eq 0 ] && { offsite_tier monthly "$DEST/monthly/$TODAY" "$DRIVE_KEEP_MONTHLY" "$pass" \
    && echo "$TODAY" > "$LOGDIR/.last-monthly" || log "[monthly] маркер не поставлен — тир повторится завтра"; }
  local RC; RC="$(rclone_bin)"
  [ -x "$RC" ] && log "[offsite] Drive now: $("$RC" about "${RCLONE_REMOTE%%:*}:" 2>/dev/null | grep -E '^(Used|Free):' | tr '\n' ' ')"
  pass=""
}

### ---- 7. prune GFS (local depth is 1 daily / 0 weekly / 0 monthly — see header) ----
prune(){ # $1=tier $2=keep
  local parent="$DEST/$1"
  ls -1d "$parent"/*/ 2>/dev/null | sort -r | tail -n +"$(( $2 + 1 ))" | while read -r d; do
    rm -rf "$d" && log "[prune $1] removed $(basename "$d")"
  done
}

### ---- 8. secret-leak audit: fail loudly if anything secret reached the snapshot ----
# rsync --exclude alone PROTECTS pre-existing files on the receiver from --delete, so a secret
# copied before an exclude rule existed would persist silently. --delete-excluded fixes new runs;
# this audit is the safety net that proves each snapshot is clean.
audit_secrets(){
  local target="$DEST/daily/$TODAY" hits
  hits="$(find "$target" \( -name '*.env' -o -name '.env' -o -name '.env.*' -o -name 'openclaw.json' \
      -o -name '*.pem' -o -name '*.p12' -o -name '*.pfx' -o -name 'id_rsa' -o -name 'id_ed25519' \
      -o -name 'credentials.json' -o -name '.credentials.json' -o -name '*.secret' \) 2>/dev/null | head -20)"
  if [ -n "$hits" ]; then
    log "[audit] SECRET LEAK — $(printf '%s\n' "$hits" | wc -l) file(s) in snapshot; purging:"
    printf '%s\n' "$hits" | while read -r f; do log "[audit]   purged $(basename "$f")"; rm -f "$f"; done
  else
    log "[audit] clean: no secret material in snapshot"
  fi
}

### ---- run -----------------------------------------------------------------
log "=== federation backup start $TS ==="

# smain also runs Lineman, Klod, mail and the portal. Filling its disk takes production down
# (ENOSPC crash-loop, 2026-07-21). Encryption alone needs ~2x the archive size in free space,
# so bail out early and loudly rather than wedge the host.
FREE_GB=$(df -BG /home | awk 'NR==2{gsub("G","",$4); print $4}')
if [ "${FREE_GB:-99}" -lt 4 ]; then
  log "ABORT: свободно ${FREE_GB}GB (<4GB). Бэкап не запускается, чтобы не уронить smain."
  curl -sS --max-time 8 -X POST "http://10.66.0.1:9090/api/tg/send" -H 'Content-Type: application/json' \
    -d "{\"account\":\"default\",\"text\":\"FEDBACKUP: бэкап федерации ОТМЕНЁН — на smain свободно ${FREE_GB}GB. Нужна очистка диска.\"}" >/dev/null 2>&1 || true
  exit 8
fi
[ "${FREE_GB:-99}" -lt 8 ] && log "ВНИМАНИЕ: свободно ${FREE_GB}GB — приближаемся к порогу отмены (4GB)"
for spec in "${NODES[@]}"; do read -r l h s <<<"$spec"; gather_node "$l" "$h" "$s"; done
gather_extras
gather_hoster_ops
gather_hoster_pg
gather_smain_home
gather_meta
snapshot
audit_secrets          # must run BEFORE weekly/monthly link-dest from today's daily
media_full
WEEKLY_BUILT=1; MONTHLY_BUILT=1
promote weekly  && WEEKLY_BUILT=0
promote monthly && MONTHLY_BUILT=0
offsite "$WEEKLY_BUILT" "$MONTHLY_BUILT"
prune daily   "$KEEP_DAILY"
prune weekly  "$KEEP_WEEKLY"
prune monthly "$KEEP_MONTHLY"
find "$LOGDIR" -name 'backup-*.log' -mtime +30 -delete 2>/dev/null
log "[SIZE] local(daily=$KEEP_DAILY,weekly=$KEEP_WEEKLY,monthly=$KEEP_MONTHLY)=$(du -sh "$DEST" 2>/dev/null | cut -f1)  media-full=$(du -sh "$MEDIA" 2>/dev/null | cut -f1)  db-dumps=$(du -sh "$DUMPS" 2>/dev/null | cut -f1)  stage=$(du -sh "$STAGE" 2>/dev/null | cut -f1)  disk-free=$(df -h /home | awk 'NR==2{print $4}')"
log "=== finished $(TZ=Europe/Moscow date '+%F %H:%M MSK') ==="
