"""Grant screen."""

from datetime import datetime

from nicegui import events, ui

from steward import paths
from steward.admin.calls import Failure, call, finish, show_failure
from steward.admin.consts import DEFAULT_EXPIRY_HOURS, EXPIRY_HOURS
from steward.admin.present import as_names, expires_at_from, grant_row, prefixes_of, secret_names_of, text
from steward.admin.widgets import banner, confirm_delete, data_table, readonly_dialog, show_banner
from steward.db.models import Grant, Secret
from steward.service import Service

_ROOT_KEY = paths.SEPARATOR
_ROOT_WARNING = "The root folder gives this grant every secret, including ones added later."

_COLUMNS = [
    {"name": "label", "label": "Label", "field": "label", "align": "left"},
    {"name": "state", "label": "State", "field": "state", "align": "left"},
    {"name": "expires", "label": "Expires", "field": "expires", "align": "left"},
    {"name": "names", "label": "Secrets", "field": "names", "align": "left"},
]


class GrantsPage:
    def __init__(self, service: Service) -> None:
        self._service = service
        self._secret_names: list[str] = []
        self._folders: list[str] = []
        self._by_id: dict[int, Grant] = {}
        self._status = banner()
        self._label, self._names, self._prefixes, self._root_warning, self._preset, self._custom = self._form()
        self._table = data_table(columns=_COLUMNS, row_key="id").classes("pick-row")
        self._table.on("save", self._on_save)
        self._table.on("revoke", self._on_revoke)
        self._table.on("delete", self._on_delete)
        self._table.add_slot("body", _body())

    async def show(self) -> None:
        await self._refresh()

    def _form(self) -> tuple[ui.input, ui.select, ui.select, ui.label, ui.toggle, ui.input]:
        with ui.card().classes("w-full p-4 gap-4"):
            ui.label("Issue").classes("page-title")
            label = ui.input("Label").classes("w-full")
            names = ui.select([], multiple=True, label="Secrets").classes("w-full").props("use-chips")
            prefixes = (
                ui.select({}, multiple=True, label="Folders", new_value_mode="add-unique", on_change=self._warn_root)
                .classes("w-full")
                .props('use-chips use-input hint="Every secret inside, now and later. Type a prefix to add one that does not exist yet."')
            )
            root_warning = ui.label(_ROOT_WARNING).classes("hint root-warning")
            root_warning.set_visibility(False)
            with ui.row().classes("items-end"):
                preset = ui.toggle(EXPIRY_HOURS, value=DEFAULT_EXPIRY_HOURS)
                custom = ui.input("Custom expiry").props("type=datetime-local")
                ui.button("Issue", on_click=self._create)
        return label, names, prefixes, root_warning, preset, custom

    def _warn_root(self) -> None:
        self._root_warning.set_visibility(_has_root(as_names(self._prefixes.value)))

    async def _refresh(self) -> None:
        secrets_result = await call(self._service.list_secrets)
        grants_result = await call(self._service.list_grants)
        messages: list[str] = []
        missing = self._take_secrets(secrets_result, messages)
        self._names.options = self._secret_names
        self._names.update()
        self._prefixes.options = _prefix_options(self._folders)
        self._prefixes.update()
        if isinstance(grants_result, Failure):
            messages.append(grants_result.message)
            missing = missing and grants_result.missing
            self._by_id.clear()
            self._table.update_rows([])
        else:
            self._show_grants(grants_result)
        show_banner(self._status, " ".join(dict.fromkeys(messages)), notify=bool(messages) and not missing)

    def _take_secrets(self, result: list[Secret] | Failure, messages: list[str]) -> bool:
        self._secret_names.clear()
        self._folders.clear()
        if isinstance(result, Failure):
            messages.append(result.message)
            return result.missing
        self._secret_names.extend(secret.name for secret in result)
        self._folders.extend(paths.folders(self._secret_names))
        return True

    def _show_grants(self, grants: list[Grant]) -> None:
        self._by_id.clear()
        self._by_id.update({grant.id: grant for grant in grants})
        self._table.update_rows(self._rows(grants))

    def _rows(self, grants: list[Grant]) -> list[dict[str, str | int | bool | list[str]]]:
        previous = {row["id"]: row for row in self._table.rows}
        rows: list[dict[str, str | int | bool | list[str]]] = []
        for grant in grants:
            names = secret_names_of(grant)
            prefixes = prefixes_of(grant)
            old = previous.get(grant.id, {})
            name_list = [] if names is None else names
            prefix_list = [] if prefixes is None else [prefix or _ROOT_KEY for prefix in prefixes]
            row: dict[str, str | int | bool | list[str]] = {
                **grant_row(grant),
                "open": bool(old.get("open")),
                "label_draft": grant.label,
                "expiry_draft": "",
                "name_list": name_list,
                "options": sorted(set(self._secret_names) | set(name_list)),
                "names_ready": names is not None and prefixes is not None,
                "prefix_list": prefix_list,
                "prefix_options": [_ROOT_KEY, *sorted((set(self._folders) | set(prefix_list)) - {_ROOT_KEY})],
                "prefix_draft": "",
            }
            rows.append(row)
        return rows

    async def _on_save(self, event: events.GenericEventArguments) -> None:
        payload = event.args if isinstance(event.args, dict) else {}
        grant_id = _grant_id(payload)
        if grant_id is None:
            return
        label = payload.get("label") if isinstance(payload.get("label"), str) else ""
        expiry = payload.get("expiry") if isinstance(payload.get("expiry"), str) else ""
        try:
            deadline = _optional_expiry(expiry)
        except ValueError:
            ui.notify("Expiry is invalid", type="warning")
            return
        updated = await call(lambda: self._service.update_grant(grant_id, label=text(label) or None, expires_at=deadline))
        if isinstance(updated, Failure):
            show_failure(updated)
            return
        if updated is None:
            ui.notify("Grant not found", type="warning")
            return
        names = payload.get("names")
        if isinstance(names, list):
            raw_prefixes = payload.get("prefixes")
            prefixes = [str(item) for item in raw_prefixes] if isinstance(raw_prefixes, list) else None
            named = await call(lambda: self._service.set_grant_secrets(grant_id, [str(item) for item in names], prefixes))
            if isinstance(named, Failure):
                show_failure(named)
                return
            if named is None:
                ui.notify("Grant not found", type="warning")
                return
        ui.notify("Grant updated", type="positive")
        await self._refresh()

    async def _on_revoke(self, event: events.GenericEventArguments) -> None:
        payload = event.args if isinstance(event.args, dict) else {}
        grant_id = _grant_id(payload)
        if grant_id is not None:
            await self._revoke(grant_id)

    async def _on_delete(self, event: events.GenericEventArguments) -> None:
        payload = event.args if isinstance(event.args, dict) else {}
        grant_id = _grant_id(payload)
        grant = None if grant_id is None else self._by_id.get(grant_id)
        if grant is not None:
            await self._remove(grant)

    async def _create(self) -> None:
        label = text(self._label.value)
        if not label:
            ui.notify("Label is required", type="warning")
            return
        deadline = self._deadline()
        if deadline is None:
            return
        created = await call(
            lambda: self._service.create_grant(label, as_names(self._names.value), deadline, as_names(self._prefixes.value))
        )
        if isinstance(created, Failure):
            show_failure(created)
            return
        _grant, token = created
        self._label.value = ""
        self._names.value = []
        self._prefixes.value = []
        self._custom.value = ""
        readonly_dialog("Grant token", token, hint="It will not be shown again.")
        await self._refresh()

    def _deadline(self) -> datetime | None:
        hours = self._preset.value if isinstance(self._preset.value, int) else DEFAULT_EXPIRY_HOURS
        try:
            return expires_at_from(hours, text(self._custom.value))
        except ValueError:
            ui.notify("Expiry is invalid", type="warning")
            return None

    async def _revoke(self, grant_id: int) -> None:
        revoked = await call(lambda: self._service.revoke_grant(grant_id))
        await finish(revoked, ok="Grant revoked", absent="Grant not found", refresh=self._refresh)

    async def _remove(self, grant: Grant) -> None:
        async def delete() -> None:
            deleted = await call(lambda: self._service.delete_grant(grant.id))
            await finish(deleted, ok="Grant deleted", absent="Grant not found", refresh=self._refresh)

        confirm_delete(f'Delete grant "{grant.label}"?', delete)


def _optional_expiry(expiry: str | None) -> datetime | None:
    """UTC expiry parsed from text, or None when the text is blank."""
    custom = text(expiry)
    if not custom:
        return None
    return expires_at_from(DEFAULT_EXPIRY_HOURS, custom)


def _grant_id(payload: dict) -> int | None:
    grant_id = payload.get("id")
    if isinstance(grant_id, int):
        return grant_id
    return None


def _prefix_options(folders: list[str]) -> dict[str, str]:
    """Select options: the root first, then every existing folder, shown as ``prod/*``."""
    return {_ROOT_KEY: paths.prefix_label(paths.ROOT), **{folder: paths.prefix_label(folder) for folder in folders}}


def _has_root(prefixes: list[str]) -> bool:
    """Whether any chosen prefix is the root."""
    return any(not prefix.strip().strip(paths.SEPARATOR) for prefix in prefixes)


def _send(event: str, payload: str) -> str:
    return f"($parent.$refs.qRef||$parent.$parent.$refs.qRef).$emit('{event}',{payload})"


def _body() -> str:
    fields = (
        "{id:props.row.id,label:props.row.label_draft,expiry:props.row.expiry_draft,"
        "names:props.row.names_ready ? props.row.name_list : null,"
        "prefixes:props.row.names_ready ? props.row.prefix_list : null}"
    )
    identity = "{id:props.row.id}"
    save = _send("save", fields)
    revoke = _send("revoke", identity)
    delete = _send("delete", identity)
    toggle_prefix = (
        "props.row.prefix_list.includes(prefix) ? props.row.prefix_list.splice(props.row.prefix_list.indexOf(prefix), 1)"
        " : props.row.prefix_list.push(prefix)"
    )
    add_prefix = (
        "(() => { const p = (props.row.prefix_draft || '').trim().replace(/^\\/+|\\/+$/g, '') || '/';"
        " if (!props.row.prefix_options.includes(p)) props.row.prefix_options.push(p);"
        " if (!props.row.prefix_list.includes(p)) props.row.prefix_list.push(p);"
        " props.row.prefix_draft = ''; })()"
    )
    return f"""
        <q-tr :props="props" class="secret-summary" :class="props.row.open ? 'row-open' : ''"
              @click="props.row.open = !props.row.open">
            <q-td v-for="col in props.cols" :key="col.name" :props="props">{{{{ col.value }}}}</q-td>
        </q-tr>
        <q-tr v-if="props.row.open" :props="props" class="secret-expand">
            <q-td colspan="100%" @click.stop>
                <div class="secret-inline">
                    <div class="grant-fields">
                        <q-input dense outlined dark label="Label" v-model="props.row.label_draft" />
                        <q-input dense outlined dark label="New expiry" type="datetime-local" v-model="props.row.expiry_draft" />
                    </div>
                    <div v-if="props.row.names_ready" class="secret-picks" @click.stop>
                        <div class="page-title">Folders</div>
                        <div class="secret-picks-row">
                            <button v-for="prefix in props.row.prefix_options" :key="prefix" type="button"
                                    class="secret-pick" role="checkbox"
                                    :aria-checked="props.row.prefix_list.includes(prefix)"
                                    :class="{{on: props.row.prefix_list.includes(prefix)}}"
                                    @click.stop="{toggle_prefix}">
                                {{{{ prefix === '/' ? '/*' : prefix + '/*' }}}}
                            </button>
                        </div>
                        <q-input dense outlined dark label="Add folder prefix" v-model="props.row.prefix_draft"
                                 @keydown.enter.prevent="{add_prefix}">
                            <template v-slot:append>
                                <q-icon class="cursor-pointer" name="add" @click.stop="{add_prefix}" />
                            </template>
                        </q-input>
                        <div v-if="props.row.prefix_list.includes('/')" class="hint root-warning">{_ROOT_WARNING}</div>
                    </div>
                    <div v-if="props.row.names_ready" class="secret-picks" @click.stop>
                        <div class="page-title">Secrets</div>
                        <div v-if="props.row.options.length" class="secret-picks-row">
                            <button v-for="name in props.row.options" :key="name" type="button"
                                    class="secret-pick" role="checkbox"
                                    :aria-checked="props.row.name_list.includes(name)"
                                    :class="{{on: props.row.name_list.includes(name)}}"
                                    @click.stop="props.row.name_list.includes(name) ? props.row.name_list.splice(props.row.name_list.indexOf(name), 1) : props.row.name_list.push(name)">
                                {{{{ name }}}}
                            </button>
                        </div>
                        <div v-else class="hint">No secrets yet.</div>
                    </div>
                    <div v-else class="hint">Names show up when the grant list includes its links.</div>
                    <div class="secret-actions">
                        <q-btn unelevated no-caps color="primary" label="Save" @click.stop="{save}" />
                        <div class="secret-actions-left">
                            <q-btn v-if="props.row.state !== 'revoked'" flat no-caps label="Revoke" @click.stop="{revoke}" />
                            <q-btn flat no-caps class="secret-delete" label="Delete" @click.stop="{delete}" />
                        </div>
                    </div>
                </div>
            </q-td>
        </q-tr>
    """


async def grants_page(service: Service) -> None:
    """Show the grants screen."""
    await GrantsPage(service).show()
