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
import uuid
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

    def emit_and_exit(self, cache_path: Optional[Path] = None) -> None:
        payload = json.dumps(asdict(self), ensure_ascii=False)
        # Persist successful results (or terminal failures) to disk so a crashed
        # parent (Coach session timeout) doesn't lose the result and re-spend
        # tokens/bandwidth on the next attempt.
        if cache_path is not None and self.status == "ok":
            try:
                cache_path.write_text(payload, encoding="utf-8")
            except Exception:
                pass
        print(payload)
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

    # Single-flight lock: prevent multiple concurrent runs for the same URL
    # (Coach LLM duplicates "Запускаю разбор" N× during gateway OOM-restarts,
    # which would otherwise spawn N parallel downloads of the same 200MB file.)
    import fcntl, hashlib, contextlib, time
    LOCK_DIR = Path.home() / ".cache" / "process-media-locks"
    RESULT_DIR = Path.home() / ".cache" / "process-media-results"
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha256(f"{args.url_or_path}|{args.mode}".encode()).hexdigest()[:16]
    result_path = RESULT_DIR / f"{url_hash}.json"
    lock_path = LOCK_DIR / f"{url_hash}.lock"

    # Cache hit: identical URL+mode handled within last 24h → return cached result.
    # Saves tokens (no Gemini call) and bandwidth (no re-download).
    CACHE_TTL_SECONDS = 86400
    if result_path.exists() and (time.time() - result_path.stat().st_mtime) < CACHE_TTL_SECONDS:
        try:
            cached = json.loads(result_path.read_text(encoding="utf-8"))
            cached["_cached"] = True
            print(json.dumps(cached, ensure_ascii=False))
            sys.exit(0 if cached.get("status") == "ok" else 1)
        except Exception:
            pass  # corrupted cache — fall through to normal run

    lock_file = open(lock_path, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        Result(
            status="failed",
            stage="init",
            provider=detect_provider(args.url_or_path),
            reason=f"another process_media.py is already handling this URL (lock {lock_path.name})",
            should_escalate=False,
        ).emit_and_exit()

    try:
        # Stage 1: detect
        res.provider = detect_provider(args.url_or_path)
        res.stage = "detected"
        if res.provider in ("unknown",):
            res.reason = f"unsupported or unrecognized URL: {args.url_or_path}"
            res.should_escalate = True
            res.emit_and_exit()

        # Stage 2: download
        # Redirect any print() from downloaders to stderr so stdout stays clean
        # for the JSON contract Coach reads.
        out_dir = Path(args.out).expanduser() if args.out else INBOUND_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.redirect_stdout(sys.stderr):
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
        # --no-parse short-circuits before Gemini; do NOT cache (it would
        # poison later full runs that expect a parsed transcript).
        if args.no_parse:
            res.status = "ok"
            res.emit_and_exit()

        # Stage 4: parse via Gemini (import parse_voice as a module)
        try:
            import parse_voice
        except ImportError as e:
            res.reason = f"parse_voice import failed: {e}"
            res.should_escalate = True
            res.emit_and_exit()

        try:
            with contextlib.redirect_stdout(sys.stderr):
                transcript = parse_voice.parse_audio(str(downloaded), prompt=args.mode)
        except Exception as e:
            log.exception("parse_voice failed")
            res.reason = f"parse_voice error: {type(e).__name__}: {e}"
            res.should_escalate = True
            res.stage = "parsed"
            res.emit_and_exit()

        if not transcript or transcript.startswith("❌"):
            res.reason = transcript or "empty transcript from Gemini"
            res.should_escalate = True
            res.stage = "parsed"
            res.emit_and_exit()

        # Stage 5: persist transcript
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        uid = uuid.uuid4().hex[:12]
        tpath = TRANSCRIPT_DIR / f"{uid}.md"
        tpath.write_text(transcript, encoding="utf-8")
        res.transcript_path = str(tpath)
        res.summary = transcript[:200].replace("\n", " ").strip()
        res.stage = "analyzed"
        res.status = "ok"
        res.emit_and_exit(cache_path=result_path)

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
