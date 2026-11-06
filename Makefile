# Week 1 targets. On Windows without make, run the uv commands directly.
.PHONY: install validators lint typecheck test samples validate check clean

install:
	uv sync

validators:
	bash scripts/fetch_validators.sh

lint:
	uv run ruff format --check src tests
	uv run ruff check src tests

typecheck:
	uv run mypy src tests

test:
	uv run pytest -q

samples:
	uv run einvoice sample --out out

validate: validators samples
	uv run einvoice validate out/xrechnung.xml out/zugferd.pdf --reports out/reports

check: lint typecheck test validate

clean:
	rm -rf out .pytest_cache .mypy_cache .ruff_cache
