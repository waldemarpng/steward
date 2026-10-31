"""Start the admin on localhost."""

from nicegui import app, ui
from sqlalchemy.ext.asyncio import AsyncEngine

from steward.admin.app import shell
from steward.db import create_tables, make_engine, make_session_factory
from steward.service import Service
from steward.settings import get_settings


def main() -> None:
    """Serve the admin UI on the configured host and port."""
    engine: AsyncEngine = make_engine()
    service = Service(make_session_factory(engine))
    _bind(engine)
    settings = get_settings()
    ui.run(lambda: shell(service), host=settings.admin_host, port=settings.admin_port, title="steward", dark=True, reload=False, show=False)


def _bind(engine: AsyncEngine) -> None:
    @app.on_startup
    async def startup() -> None:
        await create_tables(engine)

    @app.on_shutdown
    async def shutdown() -> None:
        await engine.dispose()


if __name__ == "__main__":
    main()
