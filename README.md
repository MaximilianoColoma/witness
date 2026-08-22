# Witness

Private pre-release repository for the Witness evidence service and its public MCP contract.

## Current state

In build. A green merge or CI run does **not** claim publication, deployment, runtime verification, or user impact.

## Local verification

```bash
uv sync --locked
PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest -q -p no:cacheprovider tests repair-tests
uv build
```

The canonical public and wire contracts live under `spec/`. The shared identity-envelope protocol is authoritative in this repository; consumers bind a released protocol version and digest.
