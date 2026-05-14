#!/bin/bash
# MCP-сервер OpenClaw для Claude Code
# Claude запускает этот скрипт как subprocess MCP-сервер
exec /usr/bin/env node /usr/lib/node_modules/openclaw/dist/index.js mcp serve --url ws://127.0.0.1:18789 "$@"
