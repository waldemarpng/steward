"""CRUD on a caller-owned session. The caller commits.

Secret values are encrypted here. The value column stores ciphertext only.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from steward.db.crypto import decrypt, encrypt, hash_token
from steward.db.models import AUDIT_OUTCOMES, Audit, Grant, Secret, utcnow


async def create_secret(session: AsyncSession, name: str, value: str, note: str = "") -> Secret:
    """Encrypted secret row. Raises ValueError when the name is empty."""
    if not name:
        raise ValueError("name is empty")
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


async def delete_secret(session: AsyncSession, name: str) -> bool:
    """True when a row was removed."""
    secret = await get_secret(session, name)
    if secret is None:
        return False
    await session.delete(secret)
    await session.flush()
    return True


async def create_grant(
    session: AsyncSession,
    label: str,
    token: str,
    secret_names: list[str],
    expires_at: datetime,
) -> Grant:
    """Stored grant. The token is hashed and not kept. Raises ValueError for an empty token or an unknown secret name."""
    if not token:
        raise ValueError("token is empty")
    grant = Grant(
        label=label,
        token_hash=hash_token(token),
        expires_at=expires_at,
        revoked_at=None,
        created_at=utcnow(),
        secrets=await _secrets_by_names(session, secret_names),
    )
    session.add(grant)
    await session.flush()
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


async def set_grant_secrets(session: AsyncSession, grant_id: int, secret_names: list[str]) -> Grant | None:
    """Grant with its secret list replaced, or None when the id is missing."""
    grant = await get_grant(session, grant_id)
    if grant is None:
        return None
    grant.secrets = await _secrets_by_names(session, secret_names)
    await session.flush()
    return grant


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
