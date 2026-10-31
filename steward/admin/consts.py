"""Admin UI constants."""

EXPIRY_HOURS = {1: "1 hour", 24: "1 day", 168: "7 days", 720: "30 days"}
DEFAULT_EXPIRY_HOURS = 24

AUDIT_OUTCOMES = (
    "ok",
    "unknown_token",
    "revoked",
    "expired",
    "not_in_grant",
    "unknown_name",
)
OUTCOME_LABELS = {
    "ok": "issued",
    "unknown_token": "unknown token",
    "revoked": "revoked",
    "expired": "expired",
    "not_in_grant": "not in grant",
    "unknown_name": "unknown name",
}

TABLE_PAGE_SIZE = 20
AUDIT_ROW_DEFAULT = 100
AUDIT_ROW_MAX = 500
