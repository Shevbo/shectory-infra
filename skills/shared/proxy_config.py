#!/usr/bin/env python3
"""
Centralized Lineman URL for all skills.

All external API calls go through Lineman — change one place, affects everything.

Override via env var:
  LINEMAN_URL=http://127.0.0.1:9090  (default)

Usage:
  from proxy_config import LINEMAN
  url = f"{LINEMAN}/proxy/google/v1beta/models/..."
"""

import os

LINEMAN = os.environ.get("LINEMAN_URL", "http://127.0.0.1:9090")
