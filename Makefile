RUNTIME_PREFIX := poetry run
PYTHON_DIRS := src/ tests/

.PHONY: install dev format lint test test-coverage check-format check-lint check-types checks audit ci gen-openapi

install:
	poetry install

dev:
	$(RUNTIME_PREFIX) fastapi dev

format:
	$(RUNTIME_PREFIX) black $(PYTHON_DIRS)

lint:
	$(RUNTIME_PREFIX) ruff check $(PYTHON_DIRS) --fix

test:
	$(RUNTIME_PREFIX) pytest

test-coverage:
	$(RUNTIME_PREFIX) pytest --cov=src --cov-report=term-missing

check-format:
	$(RUNTIME_PREFIX) black $(PYTHON_DIRS) --check

check-lint:
	$(RUNTIME_PREFIX) ruff check $(PYTHON_DIRS)

check-types:
	$(RUNTIME_PREFIX) pyright

checks: check-format check-lint check-types

# The project itself is installed editable and is not on PyPI, so --strict
# audits the frozen third-party set rather than the project.
audit:
	$(RUNTIME_PREFIX) bash -c 'set -o pipefail; pip freeze --exclude-editable | pip-audit --strict --no-deps --disable-pip -r /dev/stdin'

ci: checks test-coverage

gen-openapi:
	$(RUNTIME_PREFIX) python -m common_grants.scripts.generate_openapi > openapi.yaml
