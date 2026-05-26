"""Tests for censor_investigator — redaction, prompt build, response parsing."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from censor_investigator import redact_keys, parse_opus_response, build_opus_prompt


def test_redact_keys_api_key():
    d = {"model": "gpt-4", "key": "sk-abc123", "name": "main"}
    result = redact_keys(d)
    assert result["key"] == "[REDACTED]"
    assert result["model"] == "gpt-4"
    assert result["name"] == "main"


def test_redact_keys_nested():
    d = {"profiles": {"default": {"key": "sk-secret", "url": "https://api.example.com"}}}
    result = redact_keys(d)
    assert result["profiles"]["default"]["key"] == "[REDACTED]"
    assert result["profiles"]["default"]["url"] == "https://api.example.com"


def test_redact_keys_token_field():
    d = {"token": "abc", "data": "ok"}
    result = redact_keys(d)
    assert result["token"] == "[REDACTED]"


def test_parse_opus_response_valid():
    raw = json.dumps({
        "root_cause": "Agent stuck in retry loop",
        "severity": "critical",
        "patches": [{"file": "/tmp/x.json", "description": "fix", "type": "json_key", "old": "null", "new": "15"}],
        "restart_pm2": [],
        "expected_improvement": "retry 76% -> <5%",
    })
    result = parse_opus_response(raw)
    assert result["severity"] == "critical"
    assert len(result["patches"]) == 1


def test_parse_opus_response_with_fences():
    inner = json.dumps({"root_cause": "x", "severity": "high", "patches": [], "restart_pm2": [], "expected_improvement": "y"})
    raw = f"```json\n{inner}\n```"
    result = parse_opus_response(raw)
    assert result["root_cause"] == "x"


def test_parse_opus_response_invalid():
    result = parse_opus_response("not json at all")
    assert result is None


def test_build_opus_prompt_contains_agent():
    bodies = [
        {"id": 1, "timestamp": "2026-05-26T07:00:00Z", "tokens_in": 18000,
         "request_size": 69000, "status_code": 200, "error": None, "request_body": "test body"},
    ]
    configs = {"openclaw.json": '{"gateway": {"port": 18789}}'}
    prompt = build_opus_prompt("smain:main", "2026-05-26T07:00:00Z", bodies, configs)
    assert "smain:main" in prompt
    assert "2026-05-26T07:00:00Z" in prompt
    assert "openclaw.json" in prompt


def test_build_opus_prompt_identical_bodies_detected():
    bodies = [
        {"id": 1, "timestamp": "2026-05-26T07:00:00Z", "tokens_in": 18000,
         "request_size": 69000, "status_code": 200, "error": None, "request_body": "same body"},
        {"id": 2, "timestamp": "2026-05-26T07:01:00Z", "tokens_in": 18000,
         "request_size": 69000, "status_code": 200, "error": None, "request_body": "same body"},
    ]
    configs = {}
    prompt = build_opus_prompt("smain:main", "2026-05-26T07:00:00Z", bodies, configs)
    assert "IDENTICAL" in prompt
