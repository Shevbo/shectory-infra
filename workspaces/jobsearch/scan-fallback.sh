#!/usr/bin/env bash
# Fallback trigger for jobsearch-scanner.
#
# Why this exists: after the 2026-06-04 openclaw migration the internal cron
# service loads only 1 of 13 jobs ("cron service unavailable" / jobs:1 in the
# gateway log), so the scheduled daily scans stopped firing after 2026-06-03.
#
# This calls the deterministic scanner directly (run_scan.sh -> scan_v4.py)
# instead of driving the LLM agent: a one-shot `openclaw agent` turn returns
# while the scan it spawns is still running ("сканирование всё ещё выполняется")
# and never writes a report.
#
# Remove the crontab lines + this script once openclaw cron is repaired.
set -uo pipefail

LOG="$HOME/workspaces/jobsearch/scan-fallback.log"

echo "[$(date -Is)] scan start" >> "$LOG"
# No --gemini: the AI-filter needs the google SDK + ungeoblocked egress; the
# deterministic core scan (sources via requests+bs4 through Lineman) is what we
# rely on for the report. Re-add --gemini once that path is proven.
"$HOME/workspaces/jobsearch/run_scan.sh" >> "$LOG" 2>&1
rc=$?
echo "[$(date -Is)] scan done rc=$rc" >> "$LOG"
exit $rc
