.DEFAULT_GOAL := help

.PHONY: help install qa lint format types architecture test test-bdd test-integration test-e2e coverage security clean

help: ## Show this list of available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Sync the environment from the committed lockfile
	uv sync --frozen

qa: lint types architecture coverage security ## Run the quality gates: lint, types, architecture, tests with coverage, security

lint: ## Check formatting and lint rules without modifying files
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .

format: ## Auto-fix formatting and lint issues
	uv run --frozen ruff format .
	uv run --frozen ruff check --fix .

types: ## Run both type checkers (pyright + pyrefly)
	uv run --frozen pyright
	uv run --frozen pyrefly check

architecture: ## Check the ports-and-adapters rules on the imports (import-linter contracts in pyproject.toml)
	uv run --frozen lint-imports --no-cache

test: ## Run the unit and acceptance tests (nothing needs to be running)
	uv run --frozen pytest

test-bdd: ## Run only the BDD/acceptance tests (pytest-bdd)
	uv run --frozen pytest -m bdd

test-integration: ## Run the integration tests (needs the emulator up and "terraform apply" done)
	uv run --frozen pytest -m integration

test-e2e: ## Run the end-to-end tests (needs the app deployed, and: uv run --frozen playwright install chromium)
	uv run --frozen pytest -m e2e

coverage: ## Run the unit and acceptance tests with coverage and enforce the floor from .coveragerc
	uv run --frozen pytest --cov=guestbook --cov-config=.coveragerc --cov-report=term-missing

security: ## Run the security scans (SAST + known vulnerabilities in the locked dependencies)
	uv run --frozen bandit -c bandit.yaml -r guestbook application.py
	uv run --frozen pip-audit --skip-editable

clean: ## Remove cache and coverage artifacts
	rm -rf htmlcov/ .coverage .pytest_cache/ .ruff_cache/ .pyrefly_cache/ .hypothesis/
