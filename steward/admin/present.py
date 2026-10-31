"""Turn models into the text the screens show."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect as sa_inspect

from steward.admin.consts import OUTCOME_LABELS
from steward.db.models import Audit, Grant, Secret


def text(value: str | None) -> str:
    """Stripped text, or an empty string."""
    return (value or "").strip()


def fmt(moment: datetime | None) -> str:
    """UTC timestamp as YYYY-MM-DD HH:MM UTC, or an empty string."""
    if moment is None:
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def grant_state(grant: Grant) -> str:
    """``active``, ``revoked``, or ``expired``."""
    if grant.revoked_at is not None:
        return "revoked"
    expires_at = grant.expires_at if grant.expires_at.tzinfo is not None else grant.expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return "expired"
    return "active"


def expires_at_from(hours: int, custom: str) -> datetime:
    """UTC expiry from a custom ISO time, or from hours counted from now."""
    if custom:
        parsed = datetime.fromisoformat(custom)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
        return parsed.astimezone(UTC)
    return datetime.now(UTC) + timedelta(hours=hours)


def as_names(value: object) -> list[str]:
    """A string or list coerced to names. Anything else is an empty list."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def relation_ready(obj: Secret | Grant, name: str) -> bool:
    """Whether the named relationship is loaded."""
    state = sa_inspect(obj)
    if state is None:
        return False
    return name not in state.unloaded


def grant_labels(secret: Secret) -> str:
    """Comma-separated grant labels, ``none``, or ``n/a`` when grants are not loaded."""
    if not relation_ready(secret, "grants"):
        return "n/a"
    if not secret.grants:
        return "none"
    return ", ".join(grant.label for grant in secret.grants)


def secret_names_of(grant: Grant) -> list[str] | None:
    """Secret names on the grant, or None when they are not loaded."""
    if not relation_ready(grant, "secrets"):
        return None
    return [secret.name for secret in grant.secrets]


def secret_delete_warning(secret: Secret) -> str:
    """Warning text for deleting this secret."""
    if relation_ready(secret, "grants") and secret.grants:
        return "Grants that will lose it: " + ", ".join(grant.label for grant in secret.grants)
    return "Grant links to this secret will be removed."


def secret_row(secret: Secret) -> dict[str, str]:
    """Table row for one secret. The value is not included."""
    return {"name": secret.name, "note": secret.note, "updated": fmt(secret.updated_at), "grants": grant_labels(secret)}


def grant_row(grant: Grant) -> dict[str, str | int]:
    """Table row for one grant."""
    names = secret_names_of(grant)
    shown = "n/a" if names is None else (", ".join(names) or "none")
    return {"id": grant.id, "label": grant.label, "state": grant_state(grant), "expires": fmt(grant.expires_at), "names": shown}


def audit_row(row: Audit) -> dict[str, str | int]:
    """Table row for one audit record."""
    return {
        "id": row.id,
        "at": fmt(row.at),
        "grant": row.grant_label,
        "name": row.secret_name,
        "outcome": OUTCOME_LABELS.get(row.outcome, row.outcome),
        "outcome_key": row.outcome,
    }
