#!/usr/bin/env bash
# restore.sh — восстановление после сбоя (код уже есть, нужно поднять сервисы)
set -euo pipefail

LINEMAN_DIR="$HOME/workspaces/lineman"
INFRA_DIR="$HOME/workspaces/shectory-infra"

echo "=== Shectory Restore ==="

# Обновляем код из GitHub
echo "[1] Pulling latest infra..."
cd "$INFRA_DIR" && git pull
rsync -a --exclude='.venv' --exclude='*.db*' --exclude='state.json' \
  --exclude='config.json' \
  "$INFRA_DIR/lineman/" "$LINEMAN_DIR/"

# Проверяем venv
echo "[2] Checking venv..."
if [ ! -f "$LINEMAN_DIR/.venv/bin/python3" ]; then
  cd "$LINEMAN_DIR"
  python3 -m venv .venv
  .venv/bin/pip install -q httpx structlog anyio aiohttp aiosqlite
fi

# Systemd units
echo "[3] Reloading systemd..."
cp "$INFRA_DIR/systemd/"*.service "$HOME/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload

# Nginx
echo "[4] Reloading nginx..."
sudo nginx -t && sudo systemctl reload nginx || true

# Поднимаем lineman
echo "[5] Restarting lineman..."
systemctl --user restart lineman
sleep 3
systemctl --user status lineman --no-pager | head -10

echo ""
echo "=== Restore done. Check: systemctl --user status lineman ==="
