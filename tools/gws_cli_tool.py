import json
import os
import shlex
import shutil
import subprocess

from tools.registry import registry


_BLOCKED_TOKENS = {
    "create",
    "update",
    "delete",
    "remove",
    "send",
    "draft",
    "write",
    "edit",
    "modify",
    "trash",
    "upload",
    "move",
    "copy",
    "set",
    "apply",
    "insert",
    "append",
}

_BLOCKED_FLAG_PREFIXES = (
    "--delete",
    "--update",
    "--create",
    "--write",
    "--send",
    "--modify",
)

_BLOCKED_SHELL_PATTERNS = (";", "&&", "||", "|", ">", "<", "`", "$(")


def _is_truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def check_gws_readonly_requirements() -> bool:
    toggle_enabled = _is_truthy(os.getenv("HERMES_GWS_DEV_ENABLED")) or _is_truthy(
        os.getenv("AGENT_ENABLE_GWS_READONLY_DEV")
    )
    if not toggle_enabled:
        return False
    env = (os.getenv("ENV") or os.getenv("HERMES_ENV") or "").strip().lower()
    if env in {"prod", "production"}:
        return False
    return shutil.which("gws") is not None


def _validate_and_parse_command(command: str) -> list[str]:
    raw = (command or "").strip()
    if not raw:
        raise ValueError("missing_command")

    if any(pattern in raw for pattern in _BLOCKED_SHELL_PATTERNS):
        raise ValueError("unsupported_shell_syntax")

    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        raise ValueError("invalid_command_syntax") from exc

    if not tokens:
        raise ValueError("missing_command")

    if tokens[0].lower() == "gws":
        tokens = tokens[1:]

    if not tokens:
        raise ValueError("missing_subcommand")

    lowered = [token.lower() for token in tokens]
    for token in lowered:
        if token in _BLOCKED_TOKENS:
            raise ValueError(f"blocked_operation:{token}")
        if token.startswith(_BLOCKED_FLAG_PREFIXES):
            raise ValueError(f"blocked_flag:{token}")

    return tokens


def _truncate(value: str, max_chars: int = 12000) -> str:
    value = value or ""
    return value if len(value) <= max_chars else value[:max_chars] + "\n...[truncated]"


def gws_readonly_tool(command: str, timeout_seconds: int = 30, task_id: str = None) -> str:
    try:
        tokens = _validate_and_parse_command(command)
    except ValueError as exc:
        return json.dumps({"success": False, "error": str(exc)})

    timeout = max(1, min(int(timeout_seconds or 30), 120))
    cmd = ["gws", *tokens]

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "gws_timeout", "timeout_seconds": timeout})
    except Exception as exc:
        return json.dumps({"success": False, "error": f"gws_execution_failed:{exc.__class__.__name__}"})

    return json.dumps(
        {
            "success": completed.returncode == 0,
            "command": " ".join(cmd),
            "exit_code": completed.returncode,
            "stdout": _truncate(completed.stdout),
            "stderr": _truncate(completed.stderr),
        }
    )


GWS_READONLY_SCHEMA = {
    "name": "gws_readonly",
    "description": (
        "Development-only Google Workspace CLI adapter with strict read-only enforcement. "
        "Use this to run safe gws read/list/get/search commands. "
        "Mutating operations (create/update/delete/send/write) are blocked."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": (
                    "gws subcommand to execute, with or without leading 'gws'. "
                    "Examples: 'gmail list --limit 10', 'calendar list', 'drive search \"query\"'."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Execution timeout in seconds (1-120).",
                "minimum": 1,
                "maximum": 120,
            },
        },
        "required": ["command"],
    },
}


registry.register(
    name="gws_readonly",
    toolset="gws_readonly",
    schema=GWS_READONLY_SCHEMA,
    handler=lambda args, **kw: gws_readonly_tool(
        command=args.get("command", ""),
        timeout_seconds=args.get("timeout_seconds", 30),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_gws_readonly_requirements,
)
