"""CRUD on a caller-owned session. The caller commits.

Secret values are encrypted here. The value column stores ciphertext only.
"""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from steward import paths
from steward.db.crypto import decrypt, encrypt, hash_token
from steward.db.models import AUDIT_OUTCOMES, Audit, Grant, GrantPrefix, Secret, utcnow


async def create_secret(session: AsyncSession, name: str, value: str, note: str = "") -> Secret:
    """Encrypted secret row. Raises ValueError when the path is empty or invalid."""
    name = paths.normalize_path(name)
    now = utcnow()
    secret = Secret(name=name, value=encrypt(value), note=note, created_at=now, updated_at=now)
    session.add(secret)
    await session.flush()
    return secret


async def get_secret(session: AsyncSession, name: str) -> Secret | None:
    """The secret row, or None when the name is missing."""
    return await session.scalar(select(Secret).where(Secret.name == name))


async def get_secret_value(session: AsyncSession, name: str) -> str | None:
    """Decrypted value, or None when the name is missing."""
    secret = await get_secret(session, name)
    if secret is None:
        return None
    return secret_value(secret)


def secret_value(secret: Secret) -> str:
    """Decrypted value of a loaded secret row."""
    return decrypt(secret.value)


async def list_secrets(session: AsyncSession) -> list[Secret]:
    """Secrets, ordered by name."""
    result = await session.scalars(select(Secret).order_by(Secret.name))
    return list(result.all())


async def update_secret(
    session: AsyncSession,
    name: str,
    *,
    value: str | None = None,
    note: str | None = None,
) -> Secret | None:
    """Updated row, or None when the name is missing. A None field is left unchanged."""
    secret = await get_secret(session, name)
    if secret is None:
        return None
    if value is not None:
        secret.value = encrypt(value)
    if note is not None:
        secret.note = note
    secret.updated_at = utcnow()
    await session.flush()
    return secret


async def put_secret(session: AsyncSession, name: str, value: str) -> Secret:
    """Create the secret, or replace the value of an existing one and keep its note."""
    name = paths.normalize_path(name)
    secret = await get_secret(session, name)
    if secret is None:
        return await create_secret(session, name, value)
    secret.value = encrypt(value)
    secret.updated_at = utcnow()
    await session.flush()
    return secret


async def delete_secret(session: AsyncSession, name: str) -> bool:
    """True when a row was removed."""
    secret = await get_secret(session, name)
    if secret is None:
        return False
    await session.delete(secret)
    await session.flush()
    return True


async def list_secrets_under(session: AsyncSession, prefix: str) -> list[Secret]:
    """Secrets inside the folder prefix at any depth, ordered by name. ``""`` is every secret."""
    return await _secrets_under(session, [prefix])


async def _secrets_under(session: AsyncSession, prefixes: list[str]) -> list[Secret]:
    """Secrets inside any of the prefixes, ordered by name.

    LIKE ignores case in SQLite, so it only narrows the rows and ``paths.covers`` decides.
    """
    statement = select(Secret).order_by(Secret.name)
    if paths.ROOT not in prefixes:
        statement = statement.where(or_(*(Secret.name.startswith(prefix + paths.SEPARATOR, autoescape=True) for prefix in prefixes)))
    result = await session.scalars(statement)
    return [secret for secret in result.all() if any(paths.covers(prefix, secret.name) for prefix in prefixes)]


async def delete_folder(session: AsyncSession, prefix: str) -> list[str]:
    """Paths removed from inside the folder. Raises ValueError for the root. Grant prefixes stay."""
    prefix = paths.normalize_prefix(prefix)
    if not prefix:
        raise ValueError("the root folder cannot be deleted")
    removed = await list_secrets_under(session, prefix)
    for secret in removed:
        await session.delete(secret)
    await session.flush()
    return [secret.name for secret in removed]


async def create_grant(
    session: AsyncSession,
    label: str,
    token: str,
    secret_names: list[str],
    expires_at: datetime,
    prefixes: list[str] | None = None,
) -> Grant:
    """Stored grant. The token is hashed and not kept.

    Raises ValueError for an empty token, an unknown secret name, a bad prefix, or two secrets with one short name.
    """
    if not token:
        raise ValueError("token is empty")
    grant = Grant(
        label=label,
        token_hash=hash_token(token),
        expires_at=expires_at,
        revoked_at=None,
        created_at=utcnow(),
        secrets=await _secrets_by_names(session, secret_names),
        prefixes=[GrantPrefix(prefix=prefix) for prefix in _prefixes(prefixes or [])],
    )
    session.add(grant)
    await session.flush()
    await check_short_names(session, [grant])
    return grant


async def get_grant(session: AsyncSession, grant_id: int) -> Grant | None:
    """The grant, or None when the id is missing."""
    return await session.get(Grant, grant_id)


async def get_grant_by_token(session: AsyncSession, token: str) -> Grant | None:
    """The grant for this token, or None when it does not match."""
    return await session.scalar(select(Grant).where(Grant.token_hash == hash_token(token)))


async def list_grants(session: AsyncSession) -> list[Grant]:
    """Grants, newest first."""
    result = await session.scalars(select(Grant).order_by(Grant.created_at.desc()))
    return list(result.all())


async def update_grant(
    session: AsyncSession,
    grant_id: int,
    *,
    label: str | None = None,
    expires_at: datetime | None = None,
) -> Grant | None:
    """Updated grant, or None when the id is missing. A None field is left unchanged."""
    grant = await get_grant(session, grant_id)
    if grant is None:
        return None
    if label is not None:
        grant.label = label
    if expires_at is not None:
        grant.expires_at = expires_at
    await session.flush()
    return grant


async def set_grant_secrets(
    session: AsyncSession,
    grant_id: int,
    secret_names: list[str],
    prefixes: list[str] | None = None,
) -> Grant | None:
    """Grant with its secret list replaced, and its prefixes too unless prefixes is None. None when the id is missing.

    Raises ValueError for an unknown secret name, a bad prefix, or two secrets with one short name.
    """
    grant = await get_grant(session, grant_id)
    if grant is None:
        return None
    grant.secrets = await _secrets_by_names(session, secret_names)
    if prefixes is not None:
        wanted = _prefixes(prefixes)
        kept = [item for item in grant.prefixes if item.prefix in wanted]
        known = {item.prefix for item in kept}
        grant.prefixes = kept + [GrantPrefix(prefix=prefix) for prefix in wanted if prefix not in known]
    await session.flush()
    await check_short_names(session, [grant])
    return grant


async def grant_reach(session: AsyncSession, grant: Grant) -> list[Secret]:
    """Secrets the grant can read: linked ones and every one under its prefixes, ordered by name."""
    found = {secret.id: secret for secret in grant.secrets}
    prefixes = [item.prefix for item in grant.prefixes]
    if prefixes:
        for secret in await _secrets_under(session, prefixes):
            found.setdefault(secret.id, secret)
    return sorted(found.values(), key=lambda secret: secret.name)


async def check_short_names(session: AsyncSession, grants: list[Grant]) -> None:
    """Raise ValueError when a grant that is not revoked would read two secrets with one short name."""
    for grant in grants:
        if grant.revoked_at is not None:
            continue
        seen: dict[str, str] = {}
        for secret in await grant_reach(session, grant):
            short = paths.short_name(secret.name)
            if short in seen:
                raise ValueError(f'grant "{grant.label}" would read two secrets named "{short}": {seen[short]}, {secret.name}')
            seen[short] = secret.name


async def check_new_paths(session: AsyncSession, names: list[str]) -> None:
    """Short-name check for every grant whose prefixes cover one of the new paths."""
    if not names:
        return
    result = await session.scalars(select(Grant).where(Grant.prefixes.any()))
    affected = [grant for grant in result.all() if any(paths.covers(item.prefix, name) for item in grant.prefixes for name in names)]
    await check_short_names(session, affected)


async def revoke_grant(session: AsyncSession, grant_id: int, at: datetime | None = None) -> Grant | None:
    """Revoked grant, or None when the id is missing."""
    grant = await get_grant(session, grant_id)
    if grant is None:
        return None
    grant.revoked_at = at or utcnow()
    await session.flush()
    return grant


async def delete_grant(session: AsyncSession, grant_id: int) -> bool:
    """True when a row was removed."""
    grant = await get_grant(session, grant_id)
    if grant is None:
        return False
    await session.delete(grant)
    await session.flush()
    return True


async def add_audit(
    session: AsyncSession,
    *,
    secret_name: str,
    outcome: str,
    grant_id: int | None = None,
    grant_label: str = "",
    at: datetime | None = None,
) -> Audit:
    """Stored audit row. Raises ValueError when the outcome is unknown."""
    if outcome not in AUDIT_OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome}")
    row = Audit(
        at=at or utcnow(),
        grant_id=grant_id,
        grant_label=grant_label,
        secret_name=secret_name,
        outcome=outcome,
    )
    session.add(row)
    await session.flush()
    return row


async def list_audit(session: AsyncSession, limit: int = 100) -> list[Audit]:
    """Audit rows, newest first, at most limit."""
    statement = select(Audit).order_by(Audit.at.desc()).limit(limit)
    result = await session.scalars(statement)
    return list(result.all())


async def _secrets_by_names(session: AsyncSession, names: list[str]) -> list[Secret]:
    """Secret rows for these names. Raises ValueError when any name is missing."""
    if not names:
        return []
    result = await session.scalars(select(Secret).where(Secret.name.in_(names)))
    found = list(result.all())
    found_names = {secret.name for secret in found}
    missing = [name for name in names if name not in found_names]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"unknown secrets: {joined}")
    return found


def _prefixes(prefixes: list[str]) -> list[str]:
    """Normalized, unique prefixes in their first order. Raises ValueError for a bad one."""
    return list(dict.fromkeys(paths.normalize_prefix(prefix) for prefix in prefixes))
