"""Secrets screen."""

from nicegui import events, ui

from steward.admin.calls import Failure, call, finish, show_failure
from steward.admin.present import secret_delete_warning, secret_row, text
from steward.admin.widgets import QUIET, banner, confirm_delete, data_table, password_input, paste_dialog, readonly_dialog, show_banner
from steward.db.models import Secret
from steward.service import Service

_COLUMNS = [
    {"name": "name", "label": "Name", "field": "name", "align": "left"},
    {"name": "note", "label": "Note", "field": "note", "align": "left"},
    {"name": "updated", "label": "Updated", "field": "updated", "align": "left"},
    {"name": "grants", "label": "Grants", "field": "grants", "align": "left"},
]


class SecretsPage:
    def __init__(self, service: Service) -> None:
        self._service = service
        self._by_name: dict[str, Secret] = {}

    async def show(self) -> None:
        self._status = banner()
        self._form()
        self._table = data_table(columns=_COLUMNS, row_key="name").classes("pick-row")
        self._table.on("save", self._on_save)
        self._table.on("reveal", self._on_reveal)
        self._table.on("delete", self._on_delete)
        self._table.add_slot("body", _body())
        await self._refresh()

    def _form(self) -> None:
        with ui.card().classes("w-full p-4 gap-4"):
            ui.label("New").classes("page-title")
            with ui.element("div").classes("new-secret"):
                self._name = ui.input("Name")
                self._value = password_input("Value")
                self._note = ui.input("Note")
                ui.button("Save", on_click=self._create)
                ui.button("Import .env", on_click=self._open_import).props(QUIET)

    async def _refresh(self) -> None:
        result = await call(self._service.list_secrets)
        if isinstance(result, Failure):
            self._by_name.clear()
            self._table.update_rows([])
            show_banner(self._status, result.message, notify=not result.missing)
            return
        self._by_name.clear()
        self._by_name.update({secret.name: secret for secret in result})
        self._table.update_rows(self._rows(result))
        show_banner(self._status, "")

    def _rows(self, secrets: list[Secret]) -> list[dict[str, str | bool]]:
        previous = {row["name"]: row for row in self._table.rows}
        rows: list[dict[str, str | bool]] = []
        for secret in secrets:
            old = previous.get(secret.name, {})
            row: dict[str, str | bool] = {
                **secret_row(secret),
                "open": bool(old.get("open")),
                "note_draft": secret.note,
                "value_draft": "",
            }
            rows.append(row)
        return rows

    async def _on_save(self, event: events.GenericEventArguments) -> None:
        payload = event.args if isinstance(event.args, dict) else {}
        name = payload.get("name")
        if not isinstance(name, str) or not name:
            return
        note = payload.get("note") if isinstance(payload.get("note"), str) else ""
        draft = payload.get("value") if isinstance(payload.get("value"), str) else ""
        await self._save(name, note, draft)

    async def _on_reveal(self, event: events.GenericEventArguments) -> None:
        name = event.args
        if not isinstance(name, str) or not name:
            return
        revealed = await call(lambda: self._service.get_secret_value(name))
        if isinstance(revealed, Failure):
            show_failure(revealed)
            return
        if revealed is None:
            ui.notify("Secret not found", type="warning")
            return
        readonly_dialog(name, revealed)

    async def _on_delete(self, event: events.GenericEventArguments) -> None:
        name = event.args
        if not isinstance(name, str):
            return
        secret = self._by_name.get(name)
        if secret is not None:
            await self._remove(secret)

    async def _create(self) -> None:
        name = text(self._name.value)
        value = self._value.value or ""
        if not name or not value:
            ui.notify("Name and value are required", type="warning")
            return
        created = await call(lambda: self._service.create_secret(name, value, text(self._note.value)))
        if isinstance(created, Failure):
            show_failure(created)
            return
        self._name.value = ""
        self._value.value = ""
        self._note.value = ""
        ui.notify(f'Secret "{created.name}" saved', type="positive")
        await self._refresh()

    def _open_import(self) -> None:
        paste_dialog("Import .env", self._import)

    async def _import(self, source: str) -> bool:
        saved = await call(lambda: self._service.import_env(source))
        if isinstance(saved, Failure):
            show_failure(saved)
            return False
        ui.notify(f"Saved {len(saved)} secret(s): {', '.join(secret.name for secret in saved)}", type="positive")
        await self._refresh()
        return True

    async def _save(self, name: str, note: str | None, value: str | None) -> None:
        updated = await call(lambda: self._service.update_secret(name, value=value or None, note=note))
        await finish(updated, ok=f'Secret "{name}" updated', absent="Secret not found", refresh=self._refresh)

    async def _remove(self, secret: Secret) -> None:
        async def delete() -> None:
            deleted = await call(lambda: self._service.delete_secret(secret.name))
            await finish(deleted, ok=f'Secret "{secret.name}" deleted', absent="Secret not found", refresh=self._refresh)

        confirm_delete(f'Delete "{secret.name}"?', delete, hint=secret_delete_warning(secret))


def _send(event: str, payload: str) -> str:
    return f"($parent.$refs.qRef||$parent.$parent.$refs.qRef).$emit('{event}',{payload})"


def _body() -> str:
    fields = "{name:props.row.name,note:props.row.note_draft,value:props.row.value_draft}"
    save = _send("save", fields)
    reveal = _send("reveal", "props.row.name")
    delete = _send("delete", "props.row.name")
    return f"""
        <q-tr :props="props" class="secret-summary" :class="props.row.open ? 'row-open' : ''"
              @click="props.row.open = !props.row.open">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">{{{{ col.value }}}}</q-td>
        </q-tr>
        <q-tr v-if="props.row.open" :props="props" class="secret-expand">
            <q-td colspan="100%" @click.stop>
                <div class="secret-inline">
                    <q-input dense outlined dark label="Note" v-model="props.row.note_draft" />
                    <q-input dense outlined dark label="New value" v-model="props.row.value_draft"
                             :type="props.row.peek ? 'text' : 'password'">
                        <template v-slot:append>
                            <q-icon class="cursor-pointer" :name="props.row.peek ? 'visibility' : 'visibility_off'"
                                    @click.stop="props.row.peek = !props.row.peek" />
                        </template>
                    </q-input>
                    <div class="secret-actions">
                        <div class="secret-actions-left">
                            <q-btn unelevated no-caps color="primary" label="Save" @click.stop="{save}" />
                            <q-btn flat no-caps label="Reveal" @click.stop="{reveal}" />
                        </div>
                        <q-btn flat no-caps class="secret-delete" label="Delete" @click.stop="{delete}" />
                    </div>
                </div>
            </q-td>
        </q-tr>
    """


async def secrets_page(service: Service) -> None:
    """Show the secrets screen."""
    await SecretsPage(service).show()
