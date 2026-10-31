"""Secrets screen: folders like a file browser, secrets of the open folder."""

from collections.abc import Awaitable, Callable

from nicegui import events, ui

from steward import paths
from steward.admin.calls import Failure, call, finish, show_failure
from steward.admin.present import folder_delete_warning, secret_delete_warning, secret_row, text
from steward.admin.widgets import QUIET, banner, confirm_delete, data_table, password_input, paste_dialog, readonly_dialog, show_banner
from steward.db.models import Grant, Secret
from steward.service import Service

_COLUMNS = [
    {"name": "label", "label": "Name", "field": "label", "align": "left"},
    {"name": "note", "label": "Note", "field": "note", "align": "left"},
    {"name": "updated", "label": "Updated", "field": "updated", "align": "left"},
    {"name": "grants", "label": "Grants", "field": "grants", "align": "left"},
]


class SecretsPage:
    def __init__(self, service: Service) -> None:
        self._service = service
        self._folder = paths.ROOT
        self._by_name: dict[str, Secret] = {}
        self._covering: list[Grant] = []
        self._status = banner()
        self._title, self._name, self._value, self._note = self._form()
        self._crumbs = ui.row().classes("crumbs")
        self._table = data_table(columns=_COLUMNS, row_key="key").classes("pick-row")
        self._table.on("save", self._on_save)
        self._table.on("reveal", self._on_reveal)
        self._table.on("delete", self._on_delete)
        self._table.on("open", self._on_open)
        self._table.on("delete_folder", self._on_delete_folder)
        self._table.add_slot("body", _body())

    async def show(self) -> None:
        await self._refresh()

    def _form(self) -> tuple[ui.label, ui.input, ui.input, ui.input]:
        with ui.card().classes("w-full p-4 gap-4"):
            title = ui.label("New").classes("page-title")
            with ui.element("div").classes("new-secret"):
                name = ui.input("Name", placeholder="KEY or sub/KEY")
                value = password_input("Value")
                note = ui.input("Note")
                ui.button("Save", on_click=self._create)
                ui.button("Import .env", on_click=self._open_import).props(QUIET)
        return title, name, value, note

    async def _refresh(self) -> None:
        result = await call(self._service.list_secrets)
        grants = await call(self._service.list_grants)
        self._covering = [] if isinstance(grants, Failure) else [grant for grant in grants if grant.prefixes]
        self._by_name.clear()
        if isinstance(result, Failure):
            self._draw_crumbs()
            self._table.update_rows([])
            show_banner(self._status, result.message, notify=not result.missing)
            return
        self._by_name.update({secret.name: secret for secret in result})
        self._draw_crumbs()
        self._table.update_rows(self._rows(result))
        show_banner(self._status, "")

    def _draw_crumbs(self) -> None:
        self._title.set_text(f"New in {_where(self._folder)}")
        self._crumbs.clear()
        with self._crumbs:
            ui.button("root", on_click=self._goer(paths.ROOT)).props(QUIET).classes("crumb")
            trail = ""
            for part in self._folder.split(paths.SEPARATOR) if self._folder else []:
                trail = paths.join(trail, part)
                ui.label(paths.SEPARATOR).classes("hint")
                ui.button(part, on_click=self._goer(trail)).props(QUIET).classes("crumb")

    def _goer(self, folder: str) -> Callable[[], Awaitable[None]]:
        async def go() -> None:
            await self._go(folder)

        return go

    async def _go(self, folder: str) -> None:
        self._folder = folder
        await self._refresh()

    def _rows(self, secrets: list[Secret]) -> list[dict[str, str | bool]]:
        previous = {row["key"]: row for row in self._table.rows}
        inside = [secret for secret in secrets if paths.covers(self._folder, secret.name)]
        rows: list[dict[str, str | bool]] = []
        for folder in _child_folders(self._folder, [secret.name for secret in inside]):
            count = sum(paths.covers(folder, secret.name) for secret in inside)
            rows.append(
                {
                    "key": f"folder:{folder}",
                    "kind": "folder",
                    "name": folder,
                    "label": paths.short_name(folder) + paths.SEPARATOR,
                    "note": "",
                    "updated": "",
                    "grants": f"{count} secret(s)",
                }
            )
        for secret in inside:
            if paths.folder_of(secret.name) != self._folder:
                continue
            old = previous.get(secret.name, {})
            row: dict[str, str | bool] = {
                **secret_row(secret, self._covering),
                "key": secret.name,
                "kind": "secret",
                "label": paths.short_name(secret.name),
                "open": bool(old.get("open")),
                "note_draft": secret.note,
                "value_draft": "",
            }
            rows.append(row)
        return rows

    async def _on_open(self, event: events.GenericEventArguments) -> None:
        if isinstance(event.args, str):
            await self._go(event.args)

    async def _on_delete_folder(self, event: events.GenericEventArguments) -> None:
        folder = event.args
        if not isinstance(folder, str) or not folder:
            return
        names = [name for name in self._by_name if paths.covers(folder, name)]

        async def delete() -> None:
            deleted = await call(lambda: self._service.delete_folder(folder))
            if isinstance(deleted, Failure):
                show_failure(deleted)
                return
            ui.notify(f'Folder "{folder}" deleted: {len(deleted)} secret(s)', type="positive")
            await self._refresh()

        confirm_delete(f'Delete folder "{folder}"?', delete, hint=folder_delete_warning(names, self._covering))

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
        path = paths.join(self._folder, name)
        created = await call(lambda: self._service.create_secret(path, value, text(self._note.value)))
        if isinstance(created, Failure):
            show_failure(created)
            return
        self._name.value = ""
        self._value.value = ""
        self._note.value = ""
        ui.notify(f'Secret "{created.name}" saved', type="positive")
        await self._refresh()

    def _open_import(self) -> None:
        paste_dialog("Import .env", self._import, folder=self._folder)

    async def _import(self, source: str, folder: str) -> bool:
        saved = await call(lambda: self._service.import_env(source, folder))
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

        confirm_delete(f'Delete "{secret.name}"?', delete, hint=secret_delete_warning(secret, self._covering))


def _where(folder: str) -> str:
    """``/`` for the root, ``prod/billing/`` for a folder."""
    return f"{folder}{paths.SEPARATOR}" if folder else paths.SEPARATOR


def _child_folders(folder: str, names: list[str]) -> list[str]:
    """Folders one level below folder that hold at least one of the paths."""
    depth = len(folder.split(paths.SEPARATOR)) + 1 if folder else 1
    return [
        candidate
        for candidate in paths.folders(names)
        if len(candidate.split(paths.SEPARATOR)) == depth and paths.covers(folder, candidate)
    ]


def _send(event: str, payload: str) -> str:
    return f"($parent.$refs.qRef||$parent.$parent.$refs.qRef).$emit('{event}',{payload})"


def _body() -> str:
    fields = "{name:props.row.name,note:props.row.note_draft,value:props.row.value_draft}"
    save = _send("save", fields)
    reveal = _send("reveal", "props.row.name")
    delete = _send("delete", "props.row.name")
    open_folder = _send("open", "props.row.name")
    delete_folder = _send("delete_folder", "props.row.name")
    return f"""
        <q-tr v-if="props.row.kind === 'folder'" :props="props" class="secret-summary folder-row" @click="{open_folder}">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">
                <template v-if="col.name === 'label'">
                    <q-icon name="folder" size="16px" class="folder-icon" /> {{{{ col.value }}}}
                </template>
                <template v-else-if="col.name === 'updated'">
                    <q-btn flat dense no-caps class="secret-delete" label="Delete folder" @click.stop="{delete_folder}" />
                </template>
                <template v-else>{{{{ col.value }}}}</template>
            </q-td>
        </q-tr>
        <q-tr v-if="props.row.kind !== 'folder'" :props="props" class="secret-summary" :class="props.row.open ? 'row-open' : ''"
              @click="props.row.open = !props.row.open">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">{{{{ col.value }}}}</q-td>
        </q-tr>
        <q-tr v-if="props.row.kind !== 'folder' && props.row.open" :props="props" class="secret-expand">
            <q-td colspan="100%" @click.stop>
                <div class="secret-inline">
                    <div class="hint">{{{{ props.row.name }}}}</div>
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
