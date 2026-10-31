"""Secret, grant, and audit tables."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, LargeBinary, String, Table, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from steward.admin.consts import AUDIT_OUTCOMES


def utcnow() -> datetime:
    """Current time in UTC."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


grant_secrets = Table(
    "grant_secrets",
    Base.metadata,
    Column("grant_id", Integer, ForeignKey("grants.id", ondelete="CASCADE"), primary_key=True),
    Column("secret_id", Integer, ForeignKey("secrets.id", ondelete="CASCADE"), primary_key=True),
)


class Secret(Base):
    """Named secret. ``value`` is ciphertext."""

    __tablename__ = "secrets"
    __table_args__ = (UniqueConstraint("name", name="uq_secrets_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    value: Mapped[bytes] = mapped_column(LargeBinary)
    note: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    grants: Mapped[list[Grant]] = relationship(secondary=grant_secrets, back_populates="secrets", lazy="selectin")


class Grant(Base):
    """Access grant. The token is stored only as ``token_hash``."""

    __tablename__ = "grants"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_grants_token_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    secrets: Mapped[list[Secret]] = relationship(secondary=grant_secrets, back_populates="grants", lazy="selectin")


class Audit(Base):
    """One recorded secret request."""

    __tablename__ = "audit"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ({})".format(", ".join(f"'{outcome}'" for outcome in AUDIT_OUTCOMES)),
            name="ck_audit_outcome",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    grant_id: Mapped[int | None] = mapped_column(Integer)
    grant_label: Mapped[str] = mapped_column(String, default="")
    secret_name: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String)
