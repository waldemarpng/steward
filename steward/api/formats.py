"""Secret maps as env, JSON, and YAML text."""

import json
import re

_ENV_RAW = re.compile(r"\A[A-Za-z0-9_./:@%+-]*\Z")


def to_env(values: dict[str, str]) -> str:
    """KEY=value lines. A value is quoted when it is not a bare token."""
    lines = [f"{name}={_env_value(value)}" for name, value in values.items()]
    return _text(lines)


def to_json(values: dict[str, str]) -> str:
    """JSON object of name to value, with a trailing newline."""
    return json.dumps(values, ensure_ascii=False, indent=2) + "\n"


def to_yaml(values: dict[str, str]) -> str:
    """YAML mapping of name to value. An empty map is an empty string."""
    lines = [f"{_yaml_scalar(name)}: {_yaml_scalar(value)}" for name, value in values.items()]
    return _text(lines)


def _env_value(value: str) -> str:
    if _ENV_RAW.fullmatch(value):
        return value
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\r", "\\r").replace("\n", "\\n")
    return f'"{escaped}"'


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _text(lines: list[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
