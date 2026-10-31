"""Service calls as values the screens can show."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

from steward.errors import SecretExists


@dataclass(frozen=True, slots=True)
class Failure:
    """A failed service call the screen can show."""

    message: str
    missing: bool = False


async def call[T](work: Callable[[], Awaitable[T]]) -> T | Failure:
    """The result of work, or a Failure when it raises."""
    try:
        return await work()
    except NotImplementedError:
        return Failure("This service method is not implemented yet", missing=True)
    except SecretExists as exc:
        return Failure(f'Secret "{exc.name}" already exists')
    except ValueError as exc:
        return Failure(str(exc))
    except Exception as exc:
        return Failure(str(exc) or exc.__class__.__name__)


def show_failure(failure: Failure) -> None:
    """Show the failure as a notification."""
    ui.notify(failure.message, type="warning" if failure.missing else "negative")


async def finish(result: object, *, ok: str, absent: str, refresh: Callable[[], Awaitable[None]]) -> None:
    """Notify for a failure, a missing row, or success, and refresh after success."""
    if isinstance(result, Failure):
        show_failure(result)
        return
    if result is None or result is False:
        ui.notify(absent, type="warning")
        return
    ui.notify(ok, type="positive")
    await refresh()
