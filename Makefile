.DEFAULT_GOAL := help
.PHONY: help install build run run-rust run-python test test-all restart stop status clean

help:  ## Show this help menu
	@echo "Vloop Harness Makefile Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## Set up Python virtual environment and install node dependencies
	cd react && npm install
	uv venv || true
	. .venv/bin/activate && uv pip install -e .[dev]

build: ## Build React production assets and compile the Rust kernel
	cd react && npm run build
	cd src-tauri && cargo build

run: ## Start the Rust kernel (boots the backend and opens Tauri Command Center)
	cd src-tauri && cargo run

run-python: ## Start the Python orchestrator directly (launches backend/frontend and PyWebView app)
	. .venv/bin/activate && python -m harness.main run

test: ## Run unit tests (excluding e2e integration tests)
	. .venv/bin/activate && pytest tests/ -m "not e2e"

test-all: ## Run all tests (including e2e integration tests)
	. .venv/bin/activate && pytest -v

stop: ## Gracefully stop all background services (FastAPI & Vite)
	. .venv/bin/activate && python -m harness.main services stop all

restart: ## Restart all background services (FastAPI & Vite)
	. .venv/bin/activate && python -m harness.main services restart all

status: ## Show status of running background services
	. .venv/bin/activate && python -m harness.main services status

clean: ## Clean up temporary/build files and logs
	rm -rf dist/ react/dist/ react/node_modules/ src-tauri/target/ .pytest_cache/
	find . -type d -name "__pycache__" -exec rm -rf {} +
