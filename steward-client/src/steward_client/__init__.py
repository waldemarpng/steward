"""Load granted secrets into the process environment."""

import json
import os
import urllib.error
import urllib.request
from importlib.metadata import version

__all__ = ["StewardError", "__version__", "fetch", "load_env"]

__version__ = version("steward-client")

_URL_ENV = "STEWARD_URL"
_TOKEN_ENV = "STEWARD_TOKEN"
_DEFAULT_URL = "http://127.0.0.1:8080"
_TIMEOUT_SECONDS = 5


class StewardError(Exception):
    """The broker refused the token or could not be reached."""


def load_env(*, url: str | None = None, token: str | None = None, override: bool = False) -> None:
    """Put the granted secrets into os.environ. Existing names stay unless override is set."""
    for name, value in fetch(url=url, token=token).items():
        if override or name not in os.environ:
            os.environ[name] = value


def fetch(*, url: str | None = None, token: str | None = None) -> dict[str, str]:
    """Granted secrets by name. StewardError when the token cannot be used."""
    base = url if url is not None else os.environ.get(_URL_ENV, _DEFAULT_URL)
    raw = token if token is not None else os.environ.get(_TOKEN_ENV)
    if not raw:
        raise StewardError("missing token")
    request = urllib.request.Request(
        f"{base.rstrip('/')}/secrets.json",
        headers={"Authorization": f"Bearer {raw}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            body = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise StewardError("invalid token") from exc
        raise StewardError(f"broker returned {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise StewardError("broker unavailable") from exc
    except json.JSONDecodeError as exc:
        raise StewardError("unexpected response") from exc
    if not isinstance(body, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in body.items()):
        raise StewardError("unexpected response")
    return body
