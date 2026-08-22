# Witness

Witness is the official upstream evidence-oriented MCP service for cryptographically identified agents, bounded public contracts, privacy-preserving records, and append-only audit.

## Status

Version `0.1.0` is a validated public release candidate. The service is **not deployed**. Repository publication or a green CI run does not mean production support, runtime verification in a target environment, or proven user impact.

## Install and verify

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
./install.sh --manifest --json
./install.sh --target "$HOME/.local/share/witness" --non-interactive --json
uv sync --locked
PYTHONDONTWRITEBYTECODE=1 uv run python -m pytest -q -p no:cacheprovider tests repair-tests
uv build
```

The staged installer scrubs inherited Python environment variables, performs a locked installation, writes bounded local configuration/storage, and runs a real MCP first-run doctor.

## Contracts and compatibility

The canonical public and wire contracts live under `spec/`. The canonical identity-envelope contract is `spec/identity-envelope.json` in this repository. Downstream consumers must bind an explicit protocol version and digest; generated documentation and copies are projections, not parallel authorities.

## Project center

- Governance and release authority: [`GOVERNANCE.md`](GOVERNANCE.md)
- Contributions and DCO: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security reporting: [`SECURITY.md`](SECURITY.md)
- Support boundaries: [`SUPPORT.md`](SUPPORT.md)
- Official naming and forks: [`TRADEMARKS.md`](TRADEMARKS.md)

## License

Licensed under the [Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE). Apache-2.0 permits use, modification, redistribution, and commercial use; it does not grant permission to imply official project status or trademark endorsement.
