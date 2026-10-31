from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from steward.db import create_tables, make_engine, make_session_factory
from steward.service import Service


@pytest.fixture
async def service(tmp_path: Path) -> AsyncIterator[Service]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/steward.db")
    await create_tables(engine)
    try:
        yield Service(make_session_factory(engine))
    finally:
        await engine.dispose()


async def test_import_writes_name_and_value(service: Service) -> None:
    saved = await service.import_env("API_KEY=value\n")
    assert [secret.name for secret in saved] == ["API_KEY"]
    assert await service.get_secret_value("API_KEY") == "value"


async def test_import_replaces_value_and_keeps_note(service: Service) -> None:
    await service.create_secret("API_KEY", "old", "keep")
    await service.import_env("API_KEY=new")
    assert await service.get_secret_value("API_KEY") == "new"
    stored = {secret.name: secret for secret in await service.list_secrets()}
    assert stored["API_KEY"].note == "keep"


async def test_import_unquotes_values(service: Service) -> None:
    await service.import_env('A=\'with space\'\nB="x\\"y"\n')
    assert await service.get_secret_value("A") == "with space"
    assert await service.get_secret_value("B") == 'x"y'


async def test_import_rejects_an_empty_text(service: Service) -> None:
    with pytest.raises(ValueError, match="no KEY=value lines"):
        await service.import_env("# only a comment\n")


async def test_import_writes_nothing_when_a_line_is_bad(service: Service) -> None:
    with pytest.raises(ValueError, match="line 2"):
        await service.import_env("GOOD=1\nnot a pair\n")
    assert await service.list_secrets() == []
