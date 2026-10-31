FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    STEWARD_ADMIN_HOST=0.0.0.0 \
    STEWARD_API_HOST=0.0.0.0 \
    STEWARD_DATABASE_URL=sqlite+aiosqlite:////app/data/steward.db

COPY pyproject.toml uv.lock README.md ./
COPY steward ./steward
COPY steward-client ./steward-client

RUN uv sync --frozen --no-dev --no-editable --package steward

EXPOSE 8080 8081

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')"

CMD ["python", "-m", "steward"]
