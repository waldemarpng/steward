# steward-client

Load the secrets a steward grant allows into the process environment.

```bash
uv add steward-client
```

```python
from steward_client import load_env

load_env()
```

`STEWARD_URL` defaults to `http://127.0.0.1:8080`. `STEWARD_TOKEN` is the grant token. Both can be passed as arguments instead.

Names already set in the environment stay as they are. `load_env(override=True)` replaces them with the granted values.

A missing token, an unusable grant, or an unreachable broker raises `StewardError`.
