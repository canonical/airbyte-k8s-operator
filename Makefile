# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

export PYTHONPATH := lib:src

MYPY_FLAGS := --ignore-missing-imports --follow-imports=skip --install-types --non-interactive
PYLINT_DISABLE := E0401,W1203,W0613,W0718,R0903,W1514,C0103,R0913,C0301,W0212,R0902,C0104,W0640,R0801,W0511,R0914,R0912,E1120
CODESPELL_SKIPS := --skip .git --skip .tox --skip build --skip lib --skip ./.venv \
	--skip .mypy_cache --skip ./icon.svg --skip ./uv.lock \
	--skip ./documentation/.sphinx --skip ./documentation/_build

.PHONY: help lock fmt lint static unit coverage check pack clean

help:
	@echo "Targets:"
	@echo "  fmt       Format the code (isort, black)"
	@echo "  lint      Lint the code (black, isort, flake8, mypy, pylint, pydocstyle, codespell)"
	@echo "  static    Static analysis (bandit)"
	@echo "  unit      Run unit tests with coverage"
	@echo "  coverage  Print the coverage report"
	@echo "  check     Run lint, static and unit"
	@echo "  lock      Refresh uv.lock"
	@echo "  pack      Build the charm (charmcraft pack)"
	@echo "  clean     Remove build/test artifacts"

lock:
	uv lock

fmt:
	uv run --group fmt isort src tests
	uv run --group fmt black src tests

lint:
	uv run --group lint pydocstyle src
	uv run --group lint codespell . $(CODESPELL_SKIPS)
	uv run --group lint pflake8 src tests
	uv run --group lint isort --check-only --diff src tests
	uv run --group lint black --check --diff src tests
	uv run --group lint mypy src tests $(MYPY_FLAGS)
	uv run --group lint pylint src tests --disable=$(PYLINT_DISABLE)

static:
	uv run --group static bandit -c pyproject.toml -r src tests

unit:
	uv run --group test coverage run --source=src -m pytest --tb native -v tests/unit
	uv run --group test coverage report

coverage:
	uv run --group test coverage report

check: lint static unit

pack:
	charmcraft pack

clean:
	rm -rf .coverage .mypy_cache .pytest_cache build *.charm
