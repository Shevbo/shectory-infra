#!/usr/bin/env python3
"""Read LINEMAN_IPROYAL_URL from keymaster env file → update VS Code Machine settings.json."""
import json, os, re, shutil, sys
from pathlib import Path

ENV_FILE = Path.home() / 'keymaster' / '.lineman-proxy.env'
SETTINGS = Path.home() / '.vscode-server' / 'data' / 'Machine' / 'settings.json'

def load_proxy_url() -> str:
    text = ENV_FILE.read_text()
    m = re.search(r'export\s+LINEMAN_IPROYAL_URL=(.+)', text)
    if not m:
        print('ERROR: LINEMAN_IPROYAL_URL not found in', ENV_FILE, file=sys.stderr)
        sys.exit(1)
    return m.group(1).strip().strip('"').strip("'")

def update_settings(proxy_url: str) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except Exception:
        cfg = {}

    cfg['http.proxy'] = proxy_url
    cfg['http.proxyStrictSSL'] = False

    env_map = {e['name']: e for e in cfg.get('claudeCode.environmentVariables', [])}
    # HTTPS_PROXY/HTTP_PROXY: ignored by Claude Code (Bun binary uses direct syscalls),
    # but useful for bash subprocesses Claude Code spawns.
    env_map['HTTPS_PROXY'] = {'name': 'HTTPS_PROXY', 'value': proxy_url}
    env_map['HTTP_PROXY']  = {'name': 'HTTP_PROXY',  'value': proxy_url}
    env_map['NO_PROXY']    = {'name': 'NO_PROXY',    'value': 'localhost,127.0.0.1,10.66.0.0/24'}
    # Remove any stale LD_PRELOAD/proxychains entries
    env_map.pop('LD_PRELOAD', None)
    env_map.pop('PROXYCHAINS_CONF_FILE', None)

    cfg['claudeCode.environmentVariables'] = list(env_map.values())

    tmp = SETTINGS.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    shutil.move(str(tmp), str(SETTINGS))
    print(f'Updated {SETTINGS}')

if __name__ == '__main__':
    proxy_url = load_proxy_url()
    update_settings(proxy_url)
