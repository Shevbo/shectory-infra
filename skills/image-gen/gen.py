#!/usr/bin/env python3
"""Imagen 4 image generation CLI. Usage: gen.py <prompt> [count] [model]"""
import sys, requests, base64, time, json

import os
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
PROXY = os.getenv("AGENT_PROXY", "")

def generate(prompt, model="imagen-4.0-fast-generate-001", count=1):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={GEMINI_KEY}"
    r = requests.post(url, json={"instances":[{"prompt":prompt}],"parameters":{"sampleCount":count}},
                      proxies={"https":PROXY,"http":PROXY}, timeout=90)
    r.raise_for_status()
    paths = []
    for i, pred in enumerate(r.json()["predictions"]):
        path = f"/tmp/imagen_{int(time.time())}_{i}.jpg"
        with open(path, "wb") as f:
            f.write(base64.b64decode(pred["bytesBase64Encoded"]))
        paths.append(path)
        print(path)
    return paths

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: gen.py <prompt> [count=1] [model=imagen-4.0-fast-generate-001]")
        sys.exit(1)
    prompt = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    model = sys.argv[3] if len(sys.argv) > 3 else "imagen-4.0-fast-generate-001"
    generate(prompt, model, count)
