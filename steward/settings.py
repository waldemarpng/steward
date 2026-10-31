"""Settings read from the environment."""

import os
from dataclasses import dataclass

DATABASE_URL_ENV = "STEWARD_DATABASE_URL"
MASTER_KEY_ENV = "STEWARD_MASTER_KEY"
ADMIN_HOST_ENV = "STEWARD_ADMIN_HOST"
ADMIN_PORT_ENV = "STEWARD_ADMIN_PORT"
API_HOST_ENV = "STEWARD_API_HOST"
API_PORT_ENV = "STEWARD_API_PORT"

DEFAULT_DATABASE_URL = "sqlite+aiosqlite:///data/steward.db"
DEFAULT_MASTER_KEY = "test"
DEFAULT_ADMIN_HOST = "127.0.0.1"
DEFAULT_ADMIN_PORT = 8081
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_PORT = 8080


@dataclass(frozen=True)
class Settings:
    database_url: str
    master_key: str
    admin_host: str
    admin_port: int
    api_host: str
    api_port: int

    def master_key_bytes(self) -> bytes:
        """Master key as bytes. Raises RuntimeError when it is empty."""
        if not self.master_key:
            raise RuntimeError(f"{MASTER_KEY_ENV} is not set")
        return self.master_key.encode()


def get_settings() -> Settings:
    """Settings from the environment, with defaults for anything unset."""
    raw_port = os.environ.get(ADMIN_PORT_ENV)
    raw_api_port = os.environ.get(API_PORT_ENV)
    return Settings(
        database_url=os.environ.get(DATABASE_URL_ENV, DEFAULT_DATABASE_URL),
        master_key=os.environ.get(MASTER_KEY_ENV, DEFAULT_MASTER_KEY),
        admin_host=os.environ.get(ADMIN_HOST_ENV, DEFAULT_ADMIN_HOST),
        admin_port=DEFAULT_ADMIN_PORT if raw_port is None else int(raw_port),
        api_host=os.environ.get(API_HOST_ENV, DEFAULT_API_HOST),
        api_port=DEFAULT_API_PORT if raw_api_port is None else int(raw_api_port),
    )
