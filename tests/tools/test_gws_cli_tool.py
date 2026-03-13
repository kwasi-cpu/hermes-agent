import json

from tools.gws_cli_tool import _validate_and_parse_command, check_gws_readonly_requirements, gws_readonly_tool


def test_check_requirements_needs_dev_toggle(monkeypatch):
    monkeypatch.delenv("HERMES_GWS_DEV_ENABLED", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/gws")
    assert check_gws_readonly_requirements() is False


def test_check_requirements_blocked_in_prod(monkeypatch):
    monkeypatch.setenv("HERMES_GWS_DEV_ENABLED", "true")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/gws")
    assert check_gws_readonly_requirements() is False


def test_validate_blocks_mutating_operation():
    try:
        _validate_and_parse_command("gmail send --to foo@example.com")
        assert False, "expected mutating command to be blocked"
    except ValueError as exc:
        assert "blocked_operation:send" in str(exc)


def test_validate_accepts_readonly_command():
    tokens = _validate_and_parse_command("gws gmail list --limit 5")
    assert tokens == ["gmail", "list", "--limit", "5"]


def test_tool_returns_command_output(monkeypatch):
    class _Completed:
        def __init__(self):
            self.returncode = 0
            self.stdout = "ok"
            self.stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _Completed())
    result = json.loads(gws_readonly_tool("gmail list --limit 1"))
    assert result["success"] is True
    assert result["stdout"] == "ok"
