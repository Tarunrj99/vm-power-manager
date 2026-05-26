.PHONY: venv install test lint clean

venv:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

format:
	ruff format src/ tests/

clean:
	rm -rf .venv/ dist/ build/ *.egg-info/ .pytest_cache/ .ruff_cache/ state/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
