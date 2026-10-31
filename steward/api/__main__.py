"""Start the API on localhost."""

import uvicorn

from steward.api.app import create_app
from steward.settings import get_settings


def main() -> None:
    """Serve the API on the configured host and port."""
    settings = get_settings()
    uvicorn.run(create_app(), host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    main()
