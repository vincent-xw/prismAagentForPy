.PHONY: install dev test lint format typecheck check

install:
	uv sync

dev:
	uv run uvicorn prism_agent_kit.main:app --reload

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src

check: lint typecheck test
