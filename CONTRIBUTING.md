# Contributing

Thanks for your interest in contributing to VM Power Manager!

## Getting started

```bash
git clone git@github.com:Tarunrj99/vm-power-manager.git
cd vm-power-manager
make venv
make test
make lint
```

## Development workflow

1. Fork the repo and create a feature branch from `main`.
2. Make your changes.
3. Run tests: `make test`
4. Run linter: `make lint`
5. Commit with a clear message (see style below).
6. Open a PR against `main`.

## Commit message style

```
type: short description

Longer explanation if needed.
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `config`, `chore`.

## Adding a new feature

- New VM adapter → `src/vm_power_manager/adapters/`
- New state backend → `src/vm_power_manager/state/`
- New metric source → `src/vm_power_manager/metrics/`
- New Slack command → `src/vm_power_manager/slack/commands.py`

## Code style

- Python 3.11+ type hints everywhere
- Line length: 100 chars
- Formatter/linter: `ruff`
- Models: Pydantic v2
- No hardcoded values — everything in config

## Tests

All new code should have tests under `tests/`. Run with:

```bash
pytest tests/ -v
```
