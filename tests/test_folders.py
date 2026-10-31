from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from steward import paths
from steward.admin.present import grant_labels, grant_row
from steward.db import create_tables, make_engine, make_session_factory
from steward.service import Service

_LATER = datetime.now(UTC) + timedelta(days=1)


@pytest.fixture
async def service(tmp_path: Path) -> AsyncIterator[Service]:
    engine = make_engine(f"sqlite+aiosqlite:///{tmp_path}/steward.db")
    await create_tables(engine)
    try:
        yield Service(make_session_factory(engine))
    finally:
        await engine.dispose()


async def _audit_names(service: Service) -> list[tuple[str, str]]:
    return sorted((row.secret_name, row.outcome) for row in await service.list_audit())


@pytest.mark.parametrize("path", ["KEY", "prod/KEY", "prod/billing-v2/db.main/DB_PASSWORD"])
def test_valid_paths(path: str) -> None:
    assert paths.normalize_path(f"  {path} ") == path


@pytest.mark.parametrize(
    ("path", "message"),
    [
        ("", "name is empty"),
        ("/KEY", "empty folder"),
        ("prod//KEY", "empty folder"),
        ("prod/KEY/", "invalid name"),
        ("prod/../KEY", 'invalid folder ".."'),
        ("pr od/KEY", 'invalid folder "pr od"'),
        ("prod/1KEY", 'invalid name "1KEY"'),
        ("prod/MY-KEY", 'invalid name "MY-KEY"'),
    ],
)
def test_invalid_paths(path: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        paths.normalize_path(path)


def test_prefix_helpers() -> None:
    assert paths.normalize_prefix("/prod/billing/") == "prod/billing"
    assert paths.normalize_prefix("/") == paths.ROOT
    assert paths.covers("prod/billing", "prod/billing/sub/KEY")
    assert not paths.covers("prod/billing", "prod/billing2/KEY")
    assert not paths.covers("prod/billing", "prod/KEY")
    assert paths.covers(paths.ROOT, "anything/KEY")
    assert paths.folders(["a/b/K", "a/K", "c/K", "K"]) == ["a", "a/b", "c"]


async def test_import_into_a_folder(service: Service) -> None:
    saved = await service.import_env("A=1\nB=2\n", "/prod/billing/")
    assert [secret.name for secret in saved] == ["prod/billing/A", "prod/billing/B"]
    assert await service.get_secret_value("prod/billing/A") == "1"


async def test_prefix_grant_reads_nested_and_later_secrets_by_short_name(service: Service) -> None:
    await service.create_secret("prod/billing/DB_PASSWORD", "p1")
    await service.create_secret("prod/billing2/OTHER", "no")
    await service.create_secret("dev/API_KEY", "k")
    _grant, token = await service.create_grant("billing", ["dev/API_KEY"], _LATER, ["prod/billing"])
    await service.create_secret("prod/billing/deep/REDIS_URL", "r")

    assert await service.issue_available(token) == {"API_KEY": "k", "DB_PASSWORD": "p1", "REDIS_URL": "r"}
    assert await _audit_names(service) == [
        ("dev/API_KEY", "ok"),
        ("prod/billing/DB_PASSWORD", "ok"),
        ("prod/billing/deep/REDIS_URL", "ok"),
    ]


async def test_issue_by_path_respects_prefixes(service: Service) -> None:
    await service.create_secret("prod/billing/KEY", "v")
    await service.create_secret("prod/billing2/KEY2", "x")
    _grant, token = await service.create_grant("billing", [], _LATER, ["prod/billing"])

    assert await service.issue(token, "prod/billing/KEY") == "v"
    assert await service.issue(token, "prod/billing2/KEY2") is None
    assert await service.issue(token, "prod/billing/MISSING") is None
    assert await _audit_names(service) == [
        ("prod/billing/KEY", "ok"),
        ("prod/billing/MISSING", "unknown_name"),
        ("prod/billing2/KEY2", "not_in_grant"),
    ]


async def test_root_grant_reads_everything(service: Service) -> None:
    await service.create_secret("TOP", "1")
    await service.create_secret("a/b/DEEP", "2")
    _grant, token = await service.create_grant("all", [], _LATER, ["/"])
    assert await service.issue_available(token) == {"DEEP": "2", "TOP": "1"}


async def test_prefix_may_point_at_a_missing_folder(service: Service) -> None:
    _grant, token = await service.create_grant("future", [], _LATER, ["later"])
    assert await service.issue_available(token) == {}
    await service.create_secret("later/KEY", "v")
    assert await service.issue_available(token) == {"KEY": "v"}


async def test_grant_with_two_equal_short_names_is_rejected(service: Service) -> None:
    await service.create_secret("prod/X", "1")
    await service.create_secret("dev/X", "2")
    with pytest.raises(ValueError, match='two secrets named "X": dev/X, prod/X'):
        await service.create_grant("mixed", ["dev/X"], _LATER, ["prod"])
    assert await service.list_grants() == []

    grant, _token = await service.create_grant("prod", [], _LATER, ["prod"])
    with pytest.raises(ValueError, match="two secrets named"):
        await service.set_grant_secrets(grant.id, ["dev/X"])


async def test_new_secret_that_collides_under_a_prefix_is_rejected(service: Service) -> None:
    await service.create_secret("prod/a/X", "1")
    await service.create_grant("prod", [], _LATER, ["prod"])
    with pytest.raises(ValueError, match='grant "prod" would read two secrets named "X"'):
        await service.create_secret("prod/b/X", "2")
    with pytest.raises(ValueError, match="two secrets named"):
        await service.import_env("X=3\nY=4\n", "prod/c")
    assert [secret.name for secret in await service.list_secrets()] == ["prod/a/X"]


async def test_revoked_grant_does_not_block_new_secrets(service: Service) -> None:
    await service.create_secret("prod/a/X", "1")
    grant, _token = await service.create_grant("prod", [], _LATER, ["prod"])
    await service.revoke_grant(grant.id)
    await service.create_secret("prod/b/X", "2")


async def test_set_grant_prefixes_replaces_and_none_keeps(service: Service) -> None:
    grant, _token = await service.create_grant("g", [], _LATER, ["a", "b"])
    kept = await service.set_grant_secrets(grant.id, [])
    assert kept is not None
    assert [item.prefix for item in kept.prefixes] == ["a", "b"]
    changed = await service.set_grant_secrets(grant.id, [], ["b", "/c/"])
    assert changed is not None
    assert sorted(item.prefix for item in changed.prefixes) == ["b", "c"]


async def test_delete_folder_removes_secrets_and_keeps_the_prefix(service: Service) -> None:
    await service.create_secret("prod/A", "1")
    await service.create_secret("prod/sub/B", "2")
    await service.create_secret("prod2/C", "3")
    grant, token = await service.create_grant("prod", [], _LATER, ["prod"])

    assert sorted(await service.delete_folder("prod")) == ["prod/A", "prod/sub/B"]
    assert [secret.name for secret in await service.list_secrets()] == ["prod2/C"]
    assert await service.issue_available(token) == {}
    stored = {item.id: item for item in await service.list_grants()}
    assert [item.prefix for item in stored[grant.id].prefixes] == ["prod"]
    with pytest.raises(ValueError, match="root"):
        await service.delete_folder("/")


async def test_prefixes_are_case_sensitive(service: Service) -> None:
    await service.create_secret("prod/KEY", "lower")
    await service.create_secret("PROD/OTHER", "upper")
    _grant, token = await service.create_grant("g", [], _LATER, ["prod"])
    assert await service.issue_available(token) == {"KEY": "lower"}
    assert await service.issue(token, "PROD/OTHER") is None
    assert await service.delete_folder("prod") == ["prod/KEY"]
    assert [secret.name for secret in await service.list_secrets()] == ["PROD/OTHER"]


async def test_like_wildcards_in_a_prefix_match_literally(service: Service) -> None:
    await service.create_secret("a_b/KEY", "1")
    await service.create_secret("axb/KEY2", "2")
    _grant, token = await service.create_grant("g", [], _LATER, ["a_b"])
    assert await service.issue_available(token) == {"KEY": "1"}


async def test_admin_rows_show_prefixes(service: Service) -> None:
    await service.create_secret("prod/KEY", "v")
    await service.create_grant("direct", ["prod/KEY"], _LATER)
    await service.create_grant("wide", [], _LATER, ["prod", "/"])
    grants = await service.list_grants()
    by_label = {grant.label: grant for grant in grants}
    assert grant_row(by_label["wide"])["names"] == "/*, prod/*"
    assert grant_row(by_label["direct"])["names"] == "prod/KEY"
    secret = (await service.list_secrets())[0]
    assert grant_labels(secret, grants) == "direct, wide (/*)"
