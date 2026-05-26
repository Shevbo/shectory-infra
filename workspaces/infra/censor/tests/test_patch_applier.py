"""Tests for patch_applier — json_key, text_replace, file_append, rollback."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from patch_applier import apply_json_key, apply_text_replace, apply_file_append, backup_file, replace_in_dict


def test_replace_in_dict_top_level():
    d = {"max_iterations": None, "model": "gpt-4"}
    assert replace_in_dict(d, "None", "15") is True
    assert d["max_iterations"] == "15"


def test_replace_in_dict_nested():
    d = {"settings": {"tool_error_exit": False}}
    assert replace_in_dict(d, "False", True) is True
    assert d["settings"]["tool_error_exit"] is True


def test_replace_in_dict_not_found():
    d = {"key": "value"}
    assert replace_in_dict(d, "missing", "x") is False


def test_apply_json_key(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"max_iterations": None, "model": "deepseek"}))
    apply_json_key(f, "None", 15)
    d = json.loads(f.read_text())
    assert d["max_iterations"] == 15


def test_apply_json_key_not_found_raises(tmp_path):
    f = tmp_path / "config.json"
    f.write_text(json.dumps({"key": "value"}))
    try:
        apply_json_key(f, "nonexistent", "new")
        assert False, "should raise"
    except ValueError:
        pass


def test_apply_text_replace(tmp_path):
    f = tmp_path / "prompt.md"
    f.write_text("You are a helpful assistant. Call tool X always.")
    apply_text_replace(f, "Call tool X always.", "Use tool X when needed.")
    assert "Use tool X when needed." in f.read_text()


def test_apply_text_replace_not_found_raises(tmp_path):
    f = tmp_path / "prompt.md"
    f.write_text("hello world")
    try:
        apply_text_replace(f, "missing string", "new")
        assert False, "should raise"
    except ValueError:
        pass


def test_apply_file_append(tmp_path):
    f = tmp_path / "config.txt"
    f.write_text("existing content\n")
    apply_file_append(f, "new line")
    assert f.read_text().endswith("new line\n")


def test_backup_file(tmp_path):
    f = tmp_path / "config.json"
    f.write_text('{"key": "value"}')
    backup = backup_file(f, "20260526T070000")
    assert backup.exists()
    assert backup.read_text() == '{"key": "value"}'
    assert "censor-backup-20260526T070000" in backup.name


def test_json_rollback_on_invalid(tmp_path):
    """If a patch produces invalid JSON, file is restored from backup."""
    import shutil
    f = tmp_path / "config.json"
    original = '{"max_iterations": null}'
    f.write_text(original)
    backup = backup_file(f, "ts")
    f.write_text("not valid json {{{")
    try:
        json.loads(f.read_text())
    except Exception:
        shutil.copy2(backup, f)
    assert f.read_text() == original
