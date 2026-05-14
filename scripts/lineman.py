#!/usr/bin/env python3
"""
Lineman v2 — Gemini API gatekeeper.
Agents call Lineman BEFORE calling Gemini.
Lineman tracks rate limits, returns OK/WAIT.

Endpoints:
  POST /check  — Check if rate limit allows request
  GET  /stats  — Current usage stats
  POST /cache  — TTS cache: get/set voice audio

Rate limits (80% of Google quota):
  TTS:  8 RPM  / 128 RPD
  Text: 3K RPM / 8K RPD
  Pro:  40 RPM / 800 RPD
"""

import json, os, sys, hashlib, threading, time, base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

LISTEN_PORT = 18888
OPENCLAW_CONFIG = os.path.expanduser('~/.openclaw/openclaw.json')
CACHE_DIR = os.path.expanduser('~/.openclaw/lineman-cache')
STATS_FILE = os.path.expanduser('~/.openclaw/lineman-stats.json')

# Rate limits
RATE_LIMITS = {
    'tts':  {'rpm': 8,   'rpd': 128,  'rpm_win': 60, 'rpd_win': 86400},
    'text': {'rpm': 3000, 'rpd': 8000, 'rpm_win': 60, 'rpd_win': 86400},
    'pro':  {'rpm': 40,  'rpd': 800,  'rpm_win': 60, 'rpd_win': 86400},
}

class TokenBucket:
    """Thread-safe sliding window rate limiter"""
    def __init__(self):
        self.windows = {}  # model_class -> [timestamps]
        self.lock = threading.Lock()
    
    def classify(self, model_path):
        p = model_path.lower()
        if any(k in p for k in ['tts', 'native-audio']):
            return 'tts'
        if any(k in p for k in ['pro', 'gemini-3', 'ultra']):
            return 'pro'
        return 'text'
    
    def check(self, model_path):
        """Returns (allowed: bool, wait_seconds: float, stats: dict)"""
        cls = self.classify(model_path)
        limit = RATE_LIMITS.get(cls, RATE_LIMITS['text'])
        now = time.time()
        
        with self.lock:
            if cls not in self.windows:
                self.windows[cls] = []
            ts_list = self.windows[cls]
            
            # Clean old
            ts_list = [t for t in ts_list if t > now - max(limit['rpm_win'], limit['rpd_win'])]
            
            rpm_count = sum(1 for t in ts_list if t > now - limit['rpm_win'])
            rpd_count = len(ts_list)
            
            rpm_pct = round(100 * rpm_count / limit['rpm']) if limit['rpm'] > 0 else 0
            rpd_pct = round(100 * rpd_count / limit['rpd']) if limit['rpd'] > 0 else 0
            
            wait = 0
            
            if rpm_count >= limit['rpm']:
                oldest = min(t for t in ts_list if t > now - limit['rpm_win'])
                wait = oldest + limit['rpm_win'] - now + 0.5
                self.windows[cls] = ts_list
                return False, wait, {'type': cls, 'rpm': rpm_count, 'rpd': rpd_count,
                                       'rpm_pct': rpm_pct, 'rpd_pct': rpd_pct}
            
            if limit['rpd'] > 0 and rpd_count >= limit['rpd']:
                oldest = min(ts_list)
                wait = oldest + limit['rpd_win'] - now + 1
                self.windows[cls] = ts_list
                return False, wait, {'type': cls, 'rpm': rpm_count, 'rpd': rpd_count,
                                       'rpm_pct': rpm_pct, 'rpd_pct': rpd_pct}
            
            ts_list.append(now)
            self.windows[cls] = ts_list
            return True, 0, {'type': cls, 'rpm': rpm_count, 'rpd': rpd_count,
                              'rpm_pct': rpm_pct, 'rpd_pct': rpd_pct}
    
    def all_stats(self):
        now = time.time()
        result = {}
        with self.lock:
            for cls, limit in RATE_LIMITS.items():
                ts_list = self.windows.get(cls, [])
                ts_list = [t for t in ts_list if t > now - max(limit['rpm_win'], limit['rpd_win'])]
                rpm = sum(1 for t in ts_list if t > now - limit['rpm_win'])
                rpd = len(ts_list)
                result[cls] = {
                    'rpm_current': rpm, 'rpm_limit': limit['rpm'],
                    'rpm_pct': round(100*rpm/limit['rpm']) if limit['rpm'] > 0 else 0,
                    'rpd_current': rpd, 'rpd_limit': limit['rpd'],
                    'rpd_pct': round(100*rpd/limit['rpd']) if limit['rpd'] > 0 else 0,
                    'status': 'OK' if (rpm < limit['rpm']*0.9 and rpd < limit['rpd']*0.9) else 'WARN'
                }
        return result


class TTSCache:
    """Simple file-based TTS cache"""
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self.hits = 0
        self.misses = 0
        self.lock = threading.Lock()
    
    def key(self, text, prompt=''):
        h = hashlib.sha256(f"{text}|{prompt}".encode()).hexdigest()[:32]
        return h
    
    def get(self, text, prompt=''):
        k = self.key(text, prompt)
        path = os.path.join(CACHE_DIR, k + '.ogg')
        if os.path.exists(path):
            with open(path, 'rb') as f:
                data = f.read()
            with self.lock:
                self.hits += 1
            return data
        with self.lock:
            self.misses += 1
        return None
    
    def set(self, text, prompt, data):
        k = self.key(text, prompt)
        path = os.path.join(CACHE_DIR, k + '.ogg')
        with open(path, 'wb') as f:
            f.write(data)
    
    def stats(self):
        total = self.hits + self.misses
        return {'hits': self.hits, 'misses': self.misses, 'total': total,
                'hit_rate': round(100 * self.hits / total) if total > 0 else 0}


bucket = TokenBucket()
cache = TTSCache()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    
    def _ok(self, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    
    def _err(self, code, msg):
        body = json.dumps({'error': msg}).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)
    
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length)
        
        if self.path == '/check':
            # { "model": "gemini-2.5-flash-preview-tts" }
            try:
                req = json.loads(raw)
                model = req.get('model', '')
                allowed, wait, stats = bucket.check(model)
                if allowed:
                    self._ok({'allowed': True, 'wait': 0, 'stats': stats})
                else:
                    self._ok({'allowed': False, 'wait': round(wait, 1), 'stats': stats,
                              'retry_after': int(wait + 1)})
            except Exception as e:
                self._err(400, str(e))
        
        elif self.path == '/cache/put':
            try:
                req = json.loads(raw)
                text = req.get('text', '')
                prompt = req.get('prompt', '')
                data_b64 = req.get('data', '')
                if data_b64:
                    cache.set(text, prompt, base64.b64decode(data_b64))
                    self._ok({'cached': True})
                else:
                    self._err(400, 'no data')
            except Exception as e:
                self._err(400, str(e))
        
        elif self.path == '/cache/get':
            try:
                req = json.loads(raw)
                text = req.get('text', '')
                prompt = req.get('prompt', '')
                data = cache.get(text, prompt)
                if data:
                    self._ok({'cached': True, 'data': base64.b64encode(data).decode()})
                else:
                    self._ok({'cached': False})
            except Exception as e:
                self._err(400, str(e))
        
        else:
            self._err(404, 'unknown endpoint')
    
    def do_GET(self):
        if self.path == '/stats':
            self._ok({
                'limits': bucket.all_stats(),
                'cache': cache.stats(),
            })
        elif self.path == '/health':
            self._ok({'status': 'ok'})
        else:
            self._err(404, 'unknown')

    def log_message(self, fmt, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {args[0] if args else ''}", flush=True)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def save_stats():
    while True:
        time.sleep(10)
        try:
            with open(STATS_FILE, 'w') as f:
                json.dump({'limits': bucket.all_stats(), 'cache': cache.stats()}, f, indent=2)
        except:
            pass


def main():
    os.makedirs(CACHE_DIR, exist_ok=True)
    threading.Thread(target=save_stats, daemon=True).start()
    print(f"🚦 Lineman v2 on :{LISTEN_PORT} — gatekeeper mode")
    httpd = ThreadedServer(('127.0.0.1', LISTEN_PORT), Handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == '__main__':
    main()
