#!/usr/bin/env python3
"""Read LINEMAN_IPROYAL_URL from keymaster env file → update VS Code Machine settings.json.
Uses LD_PRELOAD proxychains to force Bun-based Claude Code binary through the proxy.
"""
import json, os, re, shutil, sys
from pathlib import Path

ENV_FILE  = Path.home() / 'keymaster' / '.lineman-proxy.env'
SETTINGS  = Path.home() / '.vscode-server' / 'data' / 'Machine' / 'settings.json'
PC_CONF   = Path.home() / '.proxychains.conf'
PC_LIB    = Path('/usr/lib/x86_64-linux-gnu/libproxychains.so.4')

def load_proxy_url() -> str:
    text = ENV_FILE.read_text()
    m = re.search(r'export\s+LINEMAN_IPROYAL_URL=(.+)', text)
    if not m:
        print('ERROR: LINEMAN_IPROYAL_URL not found in', ENV_FILE, file=sys.stderr)
        sys.exit(1)
    return m.group(1).strip().strip('"').strip("'")

def write_proxychains_conf(proxy_url: str) -> None:
    """Generate ~/.proxychains.conf from proxy URL (no secrets in logs)."""
    import urllib.parse
    p = urllib.parse.urlparse(proxy_url)
    cfg = f"""strict_chain
proxy_dns
remote_dns_subnet 224
tcp_read_time_out 15000
tcp_connect_time_out 8000

[ProxyList]
http {p.hostname} {p.port} {p.username} {p.password}
"""
    PC_CONF.write_text(cfg)
    PC_CONF.chmod(0o600)

def update_settings(proxy_url: str) -> None:
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    try:
        cfg = json.loads(SETTINGS.read_text()) if SETTINGS.exists() else {}
    except Exception:
        cfg = {}

    cfg['http.proxy'] = proxy_url
    cfg['http.proxyStrictSSL'] = False

    env_map = {e['name']: e for e in cfg.get('claudeCode.environmentVariables', [])}
    env_map['HTTPS_PROXY'] = {'name': 'HTTPS_PROXY', 'value': proxy_url}
    env_map['HTTP_PROXY']  = {'name': 'HTTP_PROXY',  'value': proxy_url}
    env_map['NO_PROXY']    = {'name': 'NO_PROXY',    'value': 'localhost,127.0.0.1,10.66.0.0/24'}

    # Force Bun binary through proxy via LD_PRELOAD + proxychains
    if PC_LIB.exists():
        env_map['LD_PRELOAD'] = {
            'name': 'LD_PRELOAD',
            'value': str(PC_LIB)
        }
        env_map['PROXYCHAINS_CONF_FILE'] = {
            'name': 'PROXYCHAINS_CONF_FILE',
            'value': str(PC_CONF)
        }

    cfg['claudeCode.environmentVariables'] = list(env_map.values())

    tmp = SETTINGS.with_suffix('.tmp')
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))
    shutil.move(str(tmp), str(SETTINGS))
    print(f'Updated {SETTINGS} (proxychains LD_PRELOAD: {PC_LIB.exists()})')

if __name__ == '__main__':
    proxy_url = load_proxy_url()
    write_proxychains_conf(proxy_url)
    update_settings(proxy_url)
