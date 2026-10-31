"""Admin shell: header and routes."""

from collections.abc import Awaitable, Callable

from nicegui import ui

from steward.admin.pages import audit_page, grants_page, secrets_page
from steward.admin.theme import apply
from steward.service import Service

_NAV = (("Secrets", "/"), ("Grants", "/grants"), ("Audit", "/audit"))
_FRAME = "w-full max-w-4xl mx-auto px-8"


def shell(service: Service) -> None:
    """Draw the header and the Secrets, Grants, and Audit routes."""
    apply()
    _header()
    with ui.column(align_items="stretch").classes(f"{_FRAME} py-8 gap-4"):
        ui.sub_pages(_routes(service)).classes("w-full")


def _header() -> None:
    with (
        ui.header().classes("items-center").style("padding: 12px 0"),
        ui.row().classes(f"{_FRAME} items-center"),
    ):
        with ui.row().classes("items-center no-wrap brand-lockup"):
            ui.icon("vpn_key", size="16px").classes("brand-mark")
            ui.label("steward").classes("brand")
        ui.space()
        with ui.row().classes("gap-6"):
            for title, path in _NAV:
                ui.link(title, path)


def _routes(service: Service) -> dict[str, Callable[[], Awaitable[None]]]:
    return {
        "/": lambda: secrets_page(service),
        "/grants": lambda: grants_page(service),
        "/audit": lambda: audit_page(service),
    }
