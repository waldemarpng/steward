"""Admin screens."""

from steward.admin.pages.audit import audit_page
from steward.admin.pages.grants import grants_page
from steward.admin.pages.secrets import secrets_page

__all__ = ["audit_page", "grants_page", "secrets_page"]
