# steward

Local secrets broker: values are stored encrypted in SQLite, and an app can fetch only the secrets its grant allows.

## Quick start

```bash
uv sync
make run
```

- Admin: http://127.0.0.1:8081
- API: http://127.0.0.1:8080

```bash
curl http://127.0.0.1:8080/health
# {"status":"ok"}
```

`make run` starts both processes (`uv run python -m steward`). You can also run them separately with `make admin` and `make api`.

## Docker

```bash
make run-d
```

`make run-d` is `docker compose up --build -d`. `make up` does the same. `make run -d` is not that command: `-d` is Make's own debug flag.

The image still listens on 8080 and 8081. On the host those are 18080 (API) and 18081 (admin), so a local `make run` can keep 8080 and 8081. The database file is `/app/data/steward.db` inside the container. It remains across `docker stop` and `docker start`. A new container starts with an empty database.

```bash
STEWARD_MASTER_KEY="..." make run-d
```

`make image` builds the image without starting it.

## Client

[`steward-client`](steward-client) loads the granted secrets into the process environment.

```bash
uv add steward-client
```

```python
from steward_client import load_env

load_env()
```

`STEWARD_URL` defaults to `http://127.0.0.1:8080`. `STEWARD_TOKEN` is the grant token. Names already set in the environment stay as they are. `load_env(override=True)` replaces them.

## How it works

- **Admin UI** — manage secrets, grants, and audit entries. Import .env on the Secrets page stores each pasted `KEY=value` line, including the quoted values that `/secrets.env` returns. Comments and `export` are allowed. A bad line is reported by number and nothing is saved. An existing name keeps its note and takes the new value.
- **API** — issue the secrets a grant allows, as `.env`, JSON, or YAML.

A grant token is shown once when the grant is created and is not stored; only its hash is kept. Secret values are Fernet-encrypted with `STEWARD_MASTER_KEY`.

## API

All secret routes require `Authorization: Bearer <token>`. A missing or unknown token returns `401`.

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/health` | `{"status":"ok"}` |
| `GET` | `/secrets.env` | dotenv text |
| `GET` | `/secrets.json` | JSON object |
| `GET` | `/secrets.yaml` | YAML mapping |

```bash
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8080/secrets.json
```

## Configuration

| Variable | Default |
|----------|---------|
| `STEWARD_DATABASE_URL` | `sqlite+aiosqlite:///data/steward.db` |
| `STEWARD_MASTER_KEY` | `test` |
| `STEWARD_ADMIN_HOST` | `127.0.0.1` |
| `STEWARD_ADMIN_PORT` | `8081` |
| `STEWARD_API_HOST` | `127.0.0.1` |
| `STEWARD_API_PORT` | `8080` |

The default master key is for local use only. Set a real `STEWARD_MASTER_KEY` for anything beyond a single machine.

The image sets `STEWARD_ADMIN_HOST` and `STEWARD_API_HOST` to `0.0.0.0`, and `STEWARD_DATABASE_URL` to `sqlite+aiosqlite:////app/data/steward.db`.

## Development

Requires Python `>=3.14`.

```bash
make install   # uv sync --group dev
make check     # versions match, ruff, ty, pytest
```

`steward` and `steward-client` share one version. `make bump PART=patch` (or `minor` / `major`) updates both and refreshes `uv.lock`.
