#!/usr/bin/env bash
# bootstrap.sh — развернуть новый shectory-хост из нуля
# Usage: bash bootstrap.sh [--host smain|sdev|...]
set -euo pipefail

HOST="${1:-smain}"
REPO="git@github.com:Shevbo/shectory-infra.git"
INFRA_DIR="$HOME/workspaces/shectory-infra"

echo "=== Shectory Bootstrap: $HOST ==="

# ── 1. Системные зависимости ───────────────────────────────────────────────
echo "[1/7] System packages..."
sudo apt-get update -q
sudo apt-get install -y -q python3 python3-pip python3-venv nginx git curl tmux jq

# ── 2. Клонирование infra репо ─────────────────────────────────────────────
echo "[2/7] Cloning infra repo..."
if [ -d "$INFRA_DIR/.git" ]; then
  cd "$INFRA_DIR" && git pull
else
  git clone "$REPO" "$INFRA_DIR"
fi

# ── 3. Lineman: venv + зависимости ────────────────────────────────────────
echo "[3/7] Lineman venv..."
LINEMAN_DIR="$HOME/workspaces/lineman"
mkdir -p "$LINEMAN_DIR"

# Копируем код из infra (не используем infra/lineman как рабочую директорию)
rsync -a --exclude='.venv' --exclude='*.db*' --exclude='state.json' \
  "$INFRA_DIR/lineman/" "$LINEMAN_DIR/"

cd "$LINEMAN_DIR"
python3 -m venv .venv
.venv/bin/pip install -q httpx structlog anyio aiohttp aiosqlite

echo "  ⚠️  Скопируй config.example.json → config.json и заполни секреты"

# ── 4. Nginx конфиги ──────────────────────────────────────────────────────
echo "[4/7] Nginx..."
for conf in "$INFRA_DIR/nginx/"*.nginx; do
  name=$(basename "$conf")
  echo "  → /etc/nginx/conf.d/$name"
  sudo cp "$conf" "/etc/nginx/conf.d/$name" || true
done
sudo nginx -t && sudo systemctl reload nginx || echo "  ⚠️  Nginx reload failed, check configs"

# ── 5. Systemd units ──────────────────────────────────────────────────────
echo "[5/7] Systemd units..."
mkdir -p "$HOME/.config/systemd/user"
cp "$INFRA_DIR/systemd/"*.service "$HOME/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable lineman.service 2>/dev/null || true
echo "  ⚠️  Запусти systemctl --user start lineman после настройки конфига"

# ── 6. Claude Code skills ─────────────────────────────────────────────────
echo "[6/7] Skills..."
mkdir -p "$HOME/skills"
rsync -a "$INFRA_DIR/skills/" "$HOME/skills/"

# ── 7. Claude Code config ─────────────────────────────────────────────────
echo "[7/7] Claude config..."
mkdir -p "$HOME/.claude"
cp "$INFRA_DIR/claude/settings.json" "$HOME/.claude/settings.json" 2>/dev/null || true
# CLAUDE.md и RTK.md — в ~/.claude/ для глобального действия
cp "$INFRA_DIR/claude/CLAUDE.md" "$HOME/.claude/CLAUDE.md" 2>/dev/null || true
cp "$INFRA_DIR/claude/RTK.md" "$HOME/.claude/RTK.md" 2>/dev/null || true

echo ""
echo "=== Bootstrap complete ==="
echo ""
echo "Следующие шаги:"
echo "  1. cp $LINEMAN_DIR/config.example.json $LINEMAN_DIR/config.json"
echo "  2. Заполни секреты в config.json (proxy_url, api keys, etc.)"
echo "  3. systemctl --user start lineman"
echo "  4. Проверь: systemctl --user status lineman"
echo ""
echo "Документация: $INFRA_DIR/docs/"
