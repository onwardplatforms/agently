.PHONY: help venv install install-dev clean clean-dist test lint format check all autofix build dist release pre-commit

# Variables
PYTHON = python3
VENV = venv
VENV_BIN = $(VENV)/bin
PYTEST = $(VENV_BIN)/pytest
PIP = $(VENV_BIN)/pip
BLACK = $(VENV_BIN)/black
FLAKE8 = $(VENV_BIN)/flake8
ISORT = $(VENV_BIN)/isort
MYPY = $(VENV_BIN)/mypy
AUTOFLAKE = $(VENV_BIN)/autoflake
SHELL := /bin/bash
PACKAGE_NAME = agently
ACTIVATE = . $(VENV)/bin/activate &&

# Directories
SRC_DIR := agently
TEST_DIR := tests
EXAMPLES_DIR := examples

# We don't need exclude patterns since we're only linting the agently directory
# and .grounding is at the root level

help:
	@echo "Available commands:"
	@echo "  make venv        - Create virtual environment"
	@echo "  make install     - Install production dependencies"
	@echo "  make install-dev - Install development dependencies"
	@echo "  make clean       - Remove virtual environment and cache files"
	@echo "  make clean-dist  - Clean distribution files but keep venv"
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run linters (flake8, isort)"
	@echo "  make format      - Format code (black, isort)"
	@echo "  make autofix     - Run autoformatters and fixers (autoflake, black, isort)"
	@echo "  make check       - Run type checking (mypy)"
	@echo "  make all         - Run all checks (format, lint, type check, test)"
	@echo "  make build       - Build source and wheel packages"
	@echo "  make dist        - Build and check distribution packages"
	@echo "  make release     - Build and upload packages to PyPI"
	@echo "  make pre-commit  - Install pre-commit hooks (optional)"

venv:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) $(PIP) install --upgrade pip

install: venv
	$(ACTIVATE) $(PIP) install -r requirements.txt
	$(ACTIVATE) $(PIP) install -e .

install-dev: install
	$(ACTIVATE) $(PIP) install -r requirements-dev.txt
	@echo "Pre-commit hooks installation is now optional, run 'make pre-commit' to install them"

clean:
	rm -rf $(VENV)
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf .tox
	rm -rf dist
	rm -rf build
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +

clean-dist:
	rm -rf dist
	rm -rf build
	find . -type d -name "*.egg-info" -exec rm -rf {} +

test:
	$(ACTIVATE) $(PYTEST) tests/ -v --cov=. --cov-report=term-missing --cov-report=html

lint:
	$(ACTIVATE) $(BLACK) --check $(SRC_DIR)
	$(ACTIVATE) $(ISORT) --check $(SRC_DIR)
	$(ACTIVATE) $(FLAKE8) $(SRC_DIR)

format:
	$(ACTIVATE) $(BLACK) $(SRC_DIR)
	$(ACTIVATE) $(ISORT) $(SRC_DIR)

autofix:
	$(ACTIVATE) $(AUTOFLAKE) --remove-all-unused-imports --recursive --remove-unused-variables --in-place $(SRC_DIR)
	$(ACTIVATE) $(BLACK) $(SRC_DIR)
	$(ACTIVATE) $(ISORT) $(SRC_DIR)
	$(ACTIVATE) $(FLAKE8) $(SRC_DIR)

check:
	$(ACTIVATE) $(MYPY) --package $(PACKAGE_NAME)

all: format lint check test

build:
	$(ACTIVATE) $(PYTHON) -m build

dist: clean-dist build
	$(ACTIVATE) twine check dist/*

release: clean-dist build
	$(ACTIVATE) twine check dist/*
	$(ACTIVATE) TWINE_USERNAME=__token__ TWINE_PASSWORD=$$(az keyvault secret show --vault-name kv-use-shared-dev --name pypi-api-token --query value --output tsv) twine upload dist/*

pre-commit:
	$(ACTIVATE) $(VENV_BIN)/pre-commit install || echo "Warning: pre-commit hooks could not be installed. You may need to run 'git config --unset-all core.hooksPath' first"
