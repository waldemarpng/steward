"""Small NiceGUI pieces shared by the screens."""

from collections.abc import Awaitable, Callable
from typing import Literal

from nicegui import ui

from steward.admin.consts import TABLE_PAGE_SIZE

QUIET = "flat text-color=white"


def data_table(*, columns: list[dict[str, str]], row_key: str, selection: Literal["single", "multiple"] | None = None) -> ui.table:
    """Empty table with the shared pagination and styling."""
    table = ui.table(columns=columns, rows=[], row_key=row_key, selection=selection, pagination=TABLE_PAGE_SIZE).classes("w-full")
    table.props('flat bordered separator=horizontal no-data-label="Empty"')
    return table


def banner() -> ui.label:
    """Hidden status label. ``show_banner`` fills it in."""
    label = ui.label("").classes("hint")
    label.set_visibility(False)
    return label


def show_banner(label: ui.label, message: str, *, notify: bool = False) -> None:
    """Show message on the banner, or hide the banner when message is empty."""
    label.set_text(message)
    label.set_visibility(bool(message))
    if message and notify:
        ui.notify(message, type="negative")


def password_input(label: str) -> ui.input:
    """Masked input that the browser should not autofill."""
    return ui.input(label, password=True, password_toggle_button=True).props("autocomplete=new-password")


def readonly_dialog(title: str, value: str, *, hint: str = "") -> None:
    """Open a dialog that shows value and cannot be edited. Click the value to copy it."""

    def copy() -> None:
        ui.clipboard.write(value)
        ui.notify("Copied", type="positive")

    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3"):
        with ui.row().classes("dialog-head"):
            ui.label(title).classes("page-title")
            ui.button(icon="close", on_click=dialog.close).props(QUIET).classes("dialog-close")
        if hint:
            ui.label(hint).classes("hint")
        field = ui.input(value=value).props("readonly").classes("w-96 cursor-pointer")
        field.on("click", copy)
    dialog.open()


def paste_dialog(
    title: str,
    on_save: Callable[[str, str], Awaitable[bool]],
    *,
    placeholder: str = "",
    folder: str = "",
) -> None:
    """Open a dialog with a folder and a large text field. It closes when on_save returns True."""
    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3 paste-dialog"):
        with ui.row().classes("dialog-head"):
            ui.label(title).classes("page-title")
            ui.button(icon="close", on_click=dialog.close).props(QUIET).classes("dialog-close")
        folder_input = ui.input("Folder", value=folder, placeholder="prod/billing").props("outlined dark").classes("w-full")
        ui.label("Each key is saved inside this folder. Leave it empty for the root.").classes("hint")
        source = ui.textarea(placeholder=placeholder).props("outlined dark spellcheck=false").classes("w-full paste-source")

        async def save() -> None:
            if await on_save(source.value or "", folder_input.value or ""):
                dialog.close()

        with ui.row():
            ui.button("Save", on_click=save)
            ui.button("Cancel", on_click=dialog.close).props(QUIET)
    dialog.open()


def confirm_delete(title: str, on_yes: Callable[[], Awaitable[None]], *, hint: str = "") -> None:
    """Open a dialog that calls on_yes only after Delete."""
    with ui.dialog() as dialog, ui.card().classes("p-4 gap-3"):
        ui.label(title).classes("page-title")
        if hint:
            ui.label(hint).classes("hint")

        async def confirm() -> None:
            dialog.close()
            await on_yes()

        with ui.row():
            ui.button("Delete", on_click=confirm)
            ui.button("Cancel", on_click=dialog.close).props(QUIET)
    dialog.open()
