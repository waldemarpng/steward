"""Audit screen."""

from nicegui import ui

from steward.admin.calls import Failure, call
from steward.admin.consts import AUDIT_ROW_DEFAULT, AUDIT_ROW_MAX, OUTCOME_LABELS
from steward.admin.present import audit_row
from steward.admin.widgets import banner, data_table, show_banner
from steward.service import Service

_COLUMNS = [
    {"name": "at", "label": "Time", "field": "at"},
    {"name": "grant", "label": "Grant", "field": "grant"},
    {"name": "name", "label": "Secret", "field": "name"},
    {"name": "outcome", "label": "Outcome", "field": "outcome"},
]


class AuditPage:
    def __init__(self, service: Service) -> None:
        self._service = service
        self._loaded: list[dict[str, str | int]] = []
        self._ready = False
        self._status = banner()
        self._outcome, self._limit = self._filters()
        self._table = data_table(columns=_COLUMNS, row_key="id")
        self._ready = True

    async def show(self) -> None:
        await self._refresh()

    def _filters(self) -> tuple[ui.select, ui.number]:
        with ui.row().classes("items-end"):
            outcome = ui.select({"all": "all", **OUTCOME_LABELS}, value="all", label="Outcome", on_change=self._apply_filter)
            outcome.classes("w-56")
            limit = ui.number("Rows", value=AUDIT_ROW_DEFAULT, min=1, max=AUDIT_ROW_MAX).classes("w-32")
            ui.button("Show", on_click=self._refresh)
        return outcome, limit

    def _apply_filter(self) -> None:
        if not self._ready:
            return
        self._table.update_rows(self._visible())

    def _visible(self) -> list[dict[str, str | int]]:
        chosen = self._outcome.value
        if chosen in (None, "all"):
            return self._loaded
        return [row for row in self._loaded if row["outcome_key"] == chosen]

    def _row_limit(self) -> int:
        raw = self._limit.value
        if not isinstance(raw, int | float):
            return AUDIT_ROW_DEFAULT
        return max(1, int(raw))

    async def _refresh(self) -> None:
        result = await call(lambda: self._service.list_audit(self._row_limit()))
        if isinstance(result, Failure):
            self._loaded.clear()
            self._table.update_rows([])
            show_banner(self._status, result.message, notify=not result.missing)
            return
        self._loaded.clear()
        self._loaded.extend(audit_row(row) for row in result)
        show_banner(self._status, "")
        self._apply_filter()


async def audit_page(service: Service) -> None:
    """Show the audit screen."""
    await AuditPage(service).show()
