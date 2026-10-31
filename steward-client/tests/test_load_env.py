import json
import os
import socket
import threading
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from steward_client import StewardError, fetch, load_env


class _Handler(BaseHTTPRequestHandler):
    status = 200
    payload: object = {"DATABASE_URL": "s3cret"}

    def do_GET(self) -> None:
        if self.path != "/secrets.json":
            self.send_error(404)
            return
        if self.headers.get("Authorization") != "Bearer secret":
            body = b'{"detail":"invalid token"}'
            self.send_response(401)
        else:
            body = json.dumps(self.payload).encode()
            self.send_response(self.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def broker(*, payload: object = {"DATABASE_URL": "s3cret"}, status: int = 200) -> Generator[str]:
    class Handler(_Handler):
        pass

    Handler.payload = payload
    Handler.status = status
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port, *_rest = server.server_address
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def restored_environ() -> Iterator[None]:
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_fetch_returns_granted_secrets() -> None:
    with broker() as url:
        assert fetch(url=url, token="secret") == {"DATABASE_URL": "s3cret"}


def test_fetch_reads_url_and_token_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    with broker() as url:
        monkeypatch.setenv("STEWARD_URL", f"{url}/")
        monkeypatch.setenv("STEWARD_TOKEN", "secret")
        assert fetch() == {"DATABASE_URL": "s3cret"}


def test_missing_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STEWARD_TOKEN", raising=False)
    with pytest.raises(StewardError, match="missing token"):
        fetch(url="http://127.0.0.1:9")


def test_unusable_token_is_rejected() -> None:
    with broker() as url, pytest.raises(StewardError, match="invalid token"):
        fetch(url=url, token="nope")


def test_unreachable_broker_is_rejected() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(StewardError, match="broker unavailable"):
        fetch(url=f"http://127.0.0.1:{port}", token="secret")


def test_non_object_response_is_rejected() -> None:
    with broker(payload=["DATABASE_URL"]) as url, pytest.raises(StewardError, match="unexpected response"):
        fetch(url=url, token="secret")


def test_non_string_value_is_rejected() -> None:
    with broker(payload={"DATABASE_URL": 1}) as url, pytest.raises(StewardError, match="unexpected response"):
        fetch(url=url, token="secret")


def test_broker_error_status_is_rejected() -> None:
    with broker(status=500) as url, pytest.raises(StewardError, match="broker returned 500"):
        fetch(url=url, token="secret")


def test_load_env_sets_missing_names(restored_environ: None) -> None:
    os.environ.pop("DATABASE_URL", None)
    with broker() as url:
        load_env(url=url, token="secret")
    assert os.environ["DATABASE_URL"] == "s3cret"


def test_load_env_keeps_existing_names(restored_environ: None) -> None:
    os.environ["DATABASE_URL"] = "local"
    with broker() as url:
        load_env(url=url, token="secret")
    assert os.environ["DATABASE_URL"] == "local"


def test_load_env_override_replaces_existing_names(restored_environ: None) -> None:
    os.environ["DATABASE_URL"] = "local"
    with broker() as url:
        load_env(url=url, token="secret", override=True)
    assert os.environ["DATABASE_URL"] == "s3cret"
