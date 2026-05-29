#!/usr/bin/env python3
"""
process_media.py — unified media playbook entry point for interview-coach.

State machine: init -> detected -> downloaded -> validated -> parsed -> analyzed -> done

Usage:
    process_media.py <url-or-path> [--mode=interview|monologue|transcribe] [--no-parse] [--out=path]

Stable JSON output on stdout:
{
  "status": "ok" | "failed",
  "stage": "detected" | "downloaded" | "validated" | "parsed" | "analyzed" | "done",
  "provider": "gdrive" | "mailru" | "yadisk" | "dropbox" | "onedrive" | "telegram" | "direct" | "local",
  "file_path": "...",
  "size_bytes": 123,
  "duration_seconds": 12.3,
  "mime": "audio/mpeg",
  "transcript_path": "...",
  "summary": "...",
  "reason": null | "...",
  "should_escalate": true | false
}

Exit code: 0 on status=ok, non-zero on failed.
"""
import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from providers import detect_provider, download
from validators import validate_media

INBOUND_DIR = Path.home() / ".openclaw/media/inbound"
TRANSCRIPT_DIR = Path.home() / ".openclaw/media/transcripts"
LOG_FILE = Path.home() / "logs/process_media.log"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("process_media")


@dataclass
class Result:
    status: str = "failed"
    stage: str = "init"
    provider: str = ""
    file_path: Optional[str] = None
    size_bytes: int = 0
    duration_seconds: float = 0.0
    mime: str = ""
    transcript_path: Optional[str] = None
    summary: Optional[str] = None
    reason: Optional[str] = None
    should_escalate: bool = False

    def emit_and_exit(self) -> None:
        print(json.dumps(asdict(self), ensure_ascii=False))
        sys.exit(0 if self.status == "ok" else 1)


def main() -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("url_or_path", nargs="?", help="URL or local path")
    parser.add_argument("--mode", default="interview",
                        choices=["interview", "monologue", "transcribe", "workout"])
    parser.add_argument("--no-parse", action="store_true",
                        help="Stop after validation, skip Gemini parsing (for tests)")
    parser.add_argument("--out", default=None, help="Optional output directory")
    args = parser.parse_args()

    if not args.url_or_path:
        Result(reason="usage: process_media.py <url-or-path> [--mode=...]",
               should_escalate=False).emit_and_exit()

    res = Result()

    try:
        # Stage 1: detect
        res.provider = detect_provider(args.url_or_path)
        res.stage = "detected"
        if res.provider in ("unknown",):
            res.reason = f"unsupported or unrecognized URL: {args.url_or_path}"
            res.should_escalate = True
            res.emit_and_exit()

        # Stage 2: download
        out_dir = Path(args.out).expanduser() if args.out else INBOUND_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        downloaded = download(res.provider, args.url_or_path, out_dir)
        res.file_path = str(downloaded)
        res.stage = "downloaded"

        # Stage 3: validate
        v = validate_media(downloaded)
        res.size_bytes = v.size_bytes
        res.mime = v.mime
        res.duration_seconds = v.duration_seconds
        res.stage = "validated"
        if not v.ok:
            res.reason = v.reason
            res.should_escalate = v.should_escalate
            res.emit_and_exit()

        # Stage 4: parse (skipped in --no-parse mode)
        if args.no_parse:
            res.status = "ok"
            res.emit_and_exit()

        # parsing will be added in Task 7
        res.reason = "parsing stage not yet implemented"
        res.should_escalate = False
        res.emit_and_exit()

    except FileNotFoundError as e:
        log.exception("download/file error")
        res.reason = f"file not found: {e}"
        res.should_escalate = True
        res.emit_and_exit()
    except ValueError as e:
        log.exception("value error")
        res.reason = str(e)
        res.should_escalate = True
        res.emit_and_exit()
    except Exception as e:
        log.exception("unexpected error at stage=%s", res.stage)
        res.reason = f"{type(e).__name__}: {e}"
        res.should_escalate = True
        res.emit_and_exit()


if __name__ == "__main__":
    main()
