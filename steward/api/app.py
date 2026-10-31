"""FastAPI application."""

from fastapi import FastAPI

from steward.api.routers import health, secrets
from steward.service import Service


def create_app(service: Service | None = None) -> FastAPI:
    """API app with the health and secrets routes. Builds a Service when none is passed."""
    app = FastAPI(title="steward")
    app.state.service = service or Service()
    app.include_router(health.router)
    app.include_router(secrets.router)
    return app
