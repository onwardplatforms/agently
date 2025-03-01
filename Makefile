.PHONY: help venv install install-dev clean test lint format check all autofix

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
	@echo "  make test        - Run tests with coverage"
	@echo "  make lint        - Run linters (flake8, isort)"
	@echo "  make format      - Format code (black, isort)"
	@echo "  make autofix     - Run autoformatters and fixers (autoflake, black, isort)"
	@echo "  make check       - Run type checking (mypy)"
	@echo "  make all         - Run all checks (format, lint, type check, test)"

venv:
	$(PYTHON) -m venv $(VENV)
	$(ACTIVATE) $(PIP) install --upgrade pip

install: venv
	$(ACTIVATE) $(PIP) install -r requirements.txt
	$(ACTIVATE) $(PIP) install -e .

install-dev: install
	$(ACTIVATE) $(PIP) install pytest pytest-asyncio pytest-cov pytest-mock black flake8 flake8-docstrings isort mypy pre-commit autoflake
	$(ACTIVATE) $(VENV_BIN)/pre-commit install

clean:
	rm -rf $(VENV)
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov
	rm -rf .mypy_cache
	rm -rf .tox
	find . -type d -name "__pycache__" -exec rm -rf {} +
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
