import secrets
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from steward import formats, paths
from steward.db import crypto, make_session_factory, queries
from steward.db.models import Audit, Grant, Secret
from steward.errors import SecretExists


class Service:
    """Secret, grant, and audit operations. Each method owns its transaction."""

    def __init__(self, factory: async_sessionmaker[AsyncSession] | None = None) -> None:
        self._factory = factory or make_session_factory()

    async def create_secret(self, name: str, value: str, note: str = "") -> Secret:
        """Store a secret at a path. The value is encrypted before it is written.

        Raises ValueError for a bad path, or when a grant with a covering prefix would read two secrets with one short name.
        """
        name = paths.normalize_path(name)
        async with self._factory.begin() as session:
            if await queries.get_secret(session, name) is not None:
                raise SecretExists(name)
            secret = await queries.create_secret(session, name, value, note)
            await queries.check_new_paths(session, [secret.name])
            return secret

    async def import_env(self, source: str, folder: str = "") -> list[Secret]:
        """Store every KEY=value line inside folder in one transaction. An existing path keeps its note.

        Raises ValueError before anything is written when a line cannot be read, the folder is bad,
        or a grant would read two secrets with one short name.
        """
        values = formats.parse_env(source)
        folder = paths.normalize_prefix(folder)
        async with self._factory.begin() as session:
            saved = [await queries.put_secret(session, paths.join(folder, name), value) for name, value in values.items()]
            await queries.check_new_paths(session, [secret.name for secret in saved])
            return saved

    async def list_secrets(self) -> list[Secret]:
        """Secrets, ordered by name."""
        async with self._factory.begin() as session:
            return await queries.list_secrets(session)

    async def update_secret(self, name: str, *, value: str | None = None, note: str | None = None) -> Secret | None:
        """Change the value, the note, or both. None when the name is missing."""
        async with self._factory.begin() as session:
            return await queries.update_secret(session, name, value=value, note=note)

    async def get_secret_value(self, name: str) -> str | None:
        """Decrypted value, or None when the name is missing."""
        async with self._factory.begin() as session:
            secret = await queries.get_secret(session, name)
            if secret is None:
                return None
            return crypto.decrypt(secret.value)

    async def delete_secret(self, name: str) -> bool:
        """Delete a secret. True when a row was removed."""
        async with self._factory.begin() as session:
            return await queries.delete_secret(session, name)

    async def delete_folder(self, prefix: str) -> list[str]:
        """Delete every secret inside the folder. Paths removed. Grant prefixes stay. Raises ValueError for the root."""
        async with self._factory.begin() as session:
            return await queries.delete_folder(session, prefix)

    async def create_grant(
        self,
        label: str,
        secret_names: list[str],
        expires_at: datetime,
        prefixes: list[str] | None = None,
    ) -> tuple[Grant, str]:
        """Issue a grant on secrets and folder prefixes. The token is returned once and is not stored."""
        token = secrets.token_urlsafe(32)
        async with self._factory.begin() as session:
            grant = await queries.create_grant(session, label, token, secret_names, expires_at, prefixes)
            return grant, token

    async def list_grants(self) -> list[Grant]:
        """Grants, newest first."""
        async with self._factory.begin() as session:
            return await queries.list_grants(session)

    async def update_grant(self, grant_id: int, *, label: str | None = None, expires_at: datetime | None = None) -> Grant | None:
        """Label and expiry. None when the grant is missing."""
        async with self._factory.begin() as session:
            return await queries.update_grant(session, grant_id, label=label, expires_at=expires_at)

    async def set_grant_secrets(self, grant_id: int, secret_names: list[str], prefixes: list[str] | None = None) -> Grant | None:
        """Replace the secret names on a grant, and the prefixes unless prefixes is None. None when the grant is missing."""
        async with self._factory.begin() as session:
            return await queries.set_grant_secrets(session, grant_id, secret_names, prefixes)

    async def revoke_grant(self, grant_id: int) -> Grant | None:
        """Revoke a grant. None when the grant is missing."""
        async with self._factory.begin() as session:
            return await queries.revoke_grant(session, grant_id)

    async def delete_grant(self, grant_id: int) -> bool:
        """Delete a grant. True when a row was removed."""
        async with self._factory.begin() as session:
            return await queries.delete_grant(session, grant_id)

    async def issue(self, token: str, name: str) -> str | None:
        """Return the secret value for a token and full path, and record the outcome."""
        async with self._factory.begin() as session:
            grant = await queries.get_grant_by_token(session, token)
            if grant is None:
                await _audit(session, name=name, outcome="unknown_token")
                return None
            stored = await queries.get_secret(session, name)
            readable = stored is not None and _reads(grant, stored)
            denial = _denial(grant)
            if denial is not None:
                outcome = denial
            elif stored is None:
                outcome = "unknown_name"
            elif not readable:
                outcome = "not_in_grant"
            else:
                outcome = "ok"
            await _audit(session, name=name, outcome=outcome, grant=grant)
            if stored is None or outcome != "ok":
                return None
            return crypto.decrypt(stored.value)

    async def issue_available(self, token: str) -> dict[str, str] | None:
        """Decrypted secrets on a live grant, by short name. None when the token cannot be used.

        Audit rows keep the full path.
        """
        async with self._factory.begin() as session:
            grant = await queries.get_grant_by_token(session, token)
            if grant is None:
                await _audit(session, name="", outcome="unknown_token")
                return None
            denial = _denial(grant)
            ordered = await queries.grant_reach(session, grant)
            if denial is not None:
                names = [item.name for item in ordered] or [""]
                for name in names:
                    await _audit(session, name=name, outcome=denial, grant=grant)
                return None
            for item in ordered:
                await _audit(session, name=item.name, outcome="ok", grant=grant)
            return {paths.short_name(item.name): crypto.decrypt(item.value) for item in ordered}

    async def list_audit(self, limit: int = 100) -> list[Audit]:
        """Audit rows, newest first."""
        async with self._factory.begin() as session:
            return await queries.list_audit(session, limit)


def _reads(grant: Grant, secret: Secret) -> bool:
    """Whether the grant links the secret or has a prefix that covers it."""
    return any(item.id == secret.id for item in grant.secrets) or any(paths.covers(item.prefix, secret.name) for item in grant.prefixes)


def _denial(grant: Grant) -> str | None:
    """``revoked`` or ``expired`` when the grant cannot be used, otherwise None."""
    if grant.revoked_at is not None:
        return "revoked"
    expires_at = grant.expires_at if grant.expires_at.tzinfo is not None else grant.expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return "expired"
    return None


async def _audit(session: AsyncSession, *, name: str, outcome: str, grant: Grant | None = None) -> None:
    """Record one issue attempt on the caller's session."""
    await queries.add_audit(
        session,
        secret_name=name,
        outcome=outcome,
        grant_id=None if grant is None else grant.id,
        grant_label="" if grant is None else grant.label,
    )
