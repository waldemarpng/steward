"""Admin theme."""

from pathlib import Path

from nicegui import ui

_FONTS = "https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@400;500&display=swap"
_CSS = Path(__file__).with_name("theme.css").read_text(encoding="utf-8")


def apply() -> None:
    """Load the fonts, CSS, and color palette."""
    ui.add_head_html(f'<link rel="stylesheet" href="{_FONTS}">\n<style>\n{_CSS}\n</style>')
    ui.colors(
        primary="#0000ee",
        secondary="#252525",
        accent="#0000ee",
        dark="#000000",
        positive="#2ecc71",
        negative="#ff8866",
        warning="#ffaa00",
    )
    ui.button.default_props("no-caps unelevated text-color=white")
    ui.input.default_props("outlined dense dark")
    ui.select.default_props("outlined dense dark")
    ui.number.default_props("outlined dense dark")
