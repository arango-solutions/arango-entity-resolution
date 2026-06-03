.PHONY: help install install-dev install-all test test-unit test-integration lint format typecheck build clean docs docker-up docker-down docker-test ui-types

.DEFAULT_GOAL := help

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with core dependencies
	pip install -e .

install-dev: ## Install with dev + test dependencies (editable)
	pip install -e ".[dev,test]"

install-all: ## Install with ALL optional dependencies (editable)
	pip install -e ".[ml,onnx,sparse,mcp,llm,dev,test]"

test: ## Run all tests
	pytest -v

test-unit: ## Run unit tests only
	pytest -v -m unit

test-integration: ## Run integration tests only
	pytest -v -m integration

lint: ## Run flake8 linter
	flake8 src/ tests/

format: ## Run black formatter
	black src/ tests/

typecheck: ## Run mypy type checker
	mypy src/

build: ## Build distribution packages
	python -m build

clean: ## Remove build artifacts, caches, .pyc files
	rm -rf build dist .eggs *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage

docs: ## Build documentation (add Sphinx/MkDocs to the project to enable)
	@echo "No docs build configured."

ui-types: ## Regenerate the UI OpenAPI schema and TypeScript types
	python scripts/export_openapi.py
	cd ui && npm run gen:types

docker-up: ## Start ArangoDB via docker-compose
	docker-compose -f docker-compose.yml up -d

docker-down: ## Stop ArangoDB
	docker-compose -f docker-compose.yml down

docker-test: ## Start test ArangoDB instance
	docker-compose -f docker-compose.test.yml up -d
