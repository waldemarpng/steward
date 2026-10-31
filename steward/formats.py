"""Secret maps as env, JSON, and YAML text, and env text back into a map."""

import json
import re

_ENV_RAW = re.compile(r"\A[A-Za-z0-9_./:@%+-]*\Z")
_ENV_NAME = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*\Z")
_ENV_ESCAPES = {"\\": "\\", '"': '"', "$": "$", "n": "\n", "r": "\r"}


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


def parse_env(source: str) -> dict[str, str]:
    """Names to values from KEY=value lines; reads what ``to_env`` writes.

    Blank lines and ``#`` comments are skipped, ``export`` is allowed, and a later
    line wins over an earlier one. Raises ValueError naming the first bad line,
    or when there are no values at all.
    """
    values: dict[str, str] = {}
    for number, line in enumerate(source.lstrip("\ufeff").splitlines(), start=1):
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        name, separator, raw = entry.removeprefix("export ").partition("=")
        name = name.strip()
        if not separator:
            raise ValueError(f"line {number}: expected KEY=value")
        if not _ENV_NAME.fullmatch(name):
            raise ValueError(f'line {number}: invalid name "{name}"')
        values[name] = _env_parse_value(raw.strip(), number)
    if not values:
        raise ValueError("no KEY=value lines")
    return values


def _env_value(value: str) -> str:
    if _ENV_RAW.fullmatch(value):
        return value
    if "'" not in value and "\n" not in value and "\r" not in value:
        return f"'{value}'"
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("\r", "\\r").replace("\n", "\\n")
    return f'"{escaped}"'


def _env_parse_value(raw: str, number: int) -> str:
    quote = raw[:1]
    if quote not in ("'", '"'):
        return raw.split(" #", 1)[0].rstrip()
    end = _closing_quote(raw, quote)
    if end is None:
        raise ValueError(f"line {number}: unclosed {quote}")
    tail = raw[end + 1 :].strip()
    if tail and not tail.startswith("#"):
        raise ValueError(f"line {number}: text after the closing {quote}")
    inner = raw[1:end]
    return inner if quote == "'" else _unescape(inner)


def _closing_quote(raw: str, quote: str) -> int | None:
    index = 1
    while index < len(raw):
        if quote == '"' and raw[index] == "\\":
            index += 2
            continue
        if raw[index] == quote:
            return index
        index += 1
    return None


def _unescape(inner: str) -> str:
    out: list[str] = []
    chars = iter(inner)
    for char in chars:
        if char != "\\":
            out.append(char)
            continue
        following = next(chars, "")
        out.append(_ENV_ESCAPES.get(following, "\\" + following))
    return "".join(out)


def _yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _text(lines: list[str]) -> str:
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
