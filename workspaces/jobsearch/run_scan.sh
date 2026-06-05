#!/bin/bash
# Обёртка для сканера — сбрасывает прокси и запускает scan_v4.py
# Использует выделенный venv (bs4/lxml/requests); системный python3 их потерял.
cd /home/shectory/workspaces/jobsearch
unset http_proxy
unset https_proxy
unset HTTP_PROXY
unset HTTPS_PROXY
exec /home/shectory/workspaces/jobsearch/venv/bin/python scan_v4.py "$@"
