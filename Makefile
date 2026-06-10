# Thin wrappers over the canonical uv/docker commands — no extra logic.
.PHONY: setup test test-unit run docker lock-check

setup:            ## Install all dependencies from the lock file
	uv sync

test:             ## Run the full test suite
	uv run pytest

test-unit:        ## Run fast unit tests only
	uv run pytest -m unit

run:              ## Launch the interactive CLI
	uv run tradingagents

web:              ## Launch the local web console (http://127.0.0.1:8321)
	uv run tradingagents-web

docker:           ## Build and run inside Docker (requires .env)
	docker compose run --rm tradingagents

lock-check:       ## Verify uv.lock matches pyproject.toml
	uv lock --check
