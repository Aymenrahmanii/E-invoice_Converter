# Week 1 targets. On Windows without make, run the uv commands directly.
.PHONY: install validators lint typecheck test samples validate testset testset-validate real check clean

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

# Test set (week 2). Rendering needs WeasyPrint's Pango libraries (Linux, WSL or Docker).
testset:
	uv run einvoice testset generate --n 300

testset-validate: validators
	uv run einvoice testset generate --n 300 --xml-only
	uv run einvoice testset validate

real:
	uv run einvoice testset real

check: lint typecheck test validate testset-validate

clean:
	rm -rf out .pytest_cache .mypy_cache .ruff_cache
