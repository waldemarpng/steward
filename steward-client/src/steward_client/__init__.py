"""Load granted secrets into the process environment."""

import http.client
import json
import os
import urllib.parse
from importlib.metadata import version

__all__ = ["StewardError", "__version__", "fetch", "load_env"]

__version__ = version("steward-client")


class StewardError(Exception):
    """The broker refused the token or could not be reached."""


def load_env(*, url: str | None = None, token: str | None = None, override: bool = False) -> None:
    """Put the granted secrets into os.environ. Existing names stay unless override is set."""
    for name, value in fetch(url=url, token=token).items():
        if override or name not in os.environ:
            os.environ[name] = value


def fetch(*, url: str | None = None, token: str | None = None) -> dict[str, str]:
    """Granted secrets by name. StewardError when the token cannot be used."""
    base = url if url is not None else os.environ.get("STEWARD_URL", "http://127.0.0.1:8080")
    raw = token if token is not None else os.environ.get("STEWARD_TOKEN")
    if not raw:
        raise StewardError("missing token")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or parts.hostname is None:
        raise StewardError("broker unavailable")
    path = f"{parts.path.rstrip('/')}/secrets.json"
    if parts.scheme == "https":
        connection = http.client.HTTPSConnection(parts.hostname, parts.port or 443, timeout=5)
    else:
        connection = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=5)
    try:
        connection.request("GET", path, headers={"Authorization": f"Bearer {raw}"})
        response = connection.getresponse()
        payload = response.read()
        status = response.status
    except OSError as exc:
        raise StewardError("broker unavailable") from exc
    finally:
        connection.close()
    if status == 401:
        raise StewardError("invalid token")
    if 300 <= status < 400:
        raise StewardError("broker redirected")
    if status != 200:
        raise StewardError(f"broker returned {status}")
    try:
        body = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StewardError("unexpected response") from exc
    if not isinstance(body, dict):
        raise StewardError("unexpected response")
    values: dict[str, str] = {}
    for key, value in body.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise StewardError("unexpected response")
        values[key] = value
    return values
