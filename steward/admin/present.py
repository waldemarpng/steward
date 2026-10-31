"""Turn models into the text the screens show."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import inspect as sa_inspect

from steward import paths
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


def grant_labels(secret: Secret, covering: list[Grant] | None = None) -> str:
    """Grant labels: direct links, then grants that cover the path by prefix as ``label (prod/*)``.

    ``none`` when there are none, ``n/a`` when direct grants are not loaded.
    """
    if not relation_ready(secret, "grants"):
        return "n/a"
    labels = [grant.label for grant in secret.grants]
    labels += [f"{grant.label} ({paths.prefix_label(prefix)})" for grant, prefix in _covering(secret, covering or [])]
    return ", ".join(labels) or "none"


def secret_names_of(grant: Grant) -> list[str] | None:
    """Secret names on the grant, or None when they are not loaded."""
    if not relation_ready(grant, "secrets"):
        return None
    return [secret.name for secret in grant.secrets]


def prefixes_of(grant: Grant) -> list[str] | None:
    """Folder prefixes on the grant, or None when they are not loaded."""
    if not relation_ready(grant, "prefixes"):
        return None
    return [item.prefix for item in grant.prefixes]


def secret_delete_warning(secret: Secret, covering: list[Grant] | None = None) -> str:
    """Warning text for deleting this secret."""
    labels = [grant.label for grant in secret.grants] if relation_ready(secret, "grants") else []
    labels += [f"{grant.label} ({paths.prefix_label(prefix)})" for grant, prefix in _covering(secret, covering or [])]
    if labels:
        return "Grants that will lose it: " + ", ".join(labels)
    return "Grant links to this secret will be removed."


def folder_delete_warning(names: list[str], covering: list[Grant]) -> str:
    """Warning text for deleting a folder that holds these paths."""
    lost = {grant.label for grant in covering for name in names if _reads(grant, name)}
    lines = [f"{len(names)} secret(s) will be deleted: " + ", ".join(names)]
    if lost:
        lines.append("Grants that will lose some of them: " + ", ".join(sorted(lost)))
    return " ".join(lines)


def secret_row(secret: Secret, covering: list[Grant] | None = None) -> dict[str, str]:
    """Table row for one secret. The value is not included."""
    return {"name": secret.name, "note": secret.note, "updated": fmt(secret.updated_at), "grants": grant_labels(secret, covering)}


def grant_row(grant: Grant) -> dict[str, str | int]:
    """Table row for one grant. Prefixes come first, as ``prod/billing/*``."""
    names = secret_names_of(grant)
    prefixes = prefixes_of(grant)
    shown = "n/a" if names is None or prefixes is None else _reach_text(prefixes, names)
    return {"id": grant.id, "label": grant.label, "state": grant_state(grant), "expires": fmt(grant.expires_at), "names": shown}


def _reach_text(prefixes: list[str], names: list[str]) -> str:
    return ", ".join([paths.prefix_label(prefix) for prefix in prefixes] + names) or "none"


def _covering(secret: Secret, grants: list[Grant]) -> list[tuple[Grant, str]]:
    """Grants with a prefix over this path, with the first such prefix. A grant that links it directly is left out."""
    direct = {grant.id for grant in secret.grants} if relation_ready(secret, "grants") else set()
    found: list[tuple[Grant, str]] = []
    for grant in grants:
        if grant.id in direct:
            continue
        prefix = next((item.prefix for item in grant.prefixes if paths.covers(item.prefix, secret.name)), None)
        if prefix is not None:
            found.append((grant, prefix))
    return found


def _reads(grant: Grant, name: str) -> bool:
    if relation_ready(grant, "secrets") and any(secret.name == name for secret in grant.secrets):
        return True
    return relation_ready(grant, "prefixes") and any(paths.covers(item.prefix, name) for item in grant.prefixes)


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
