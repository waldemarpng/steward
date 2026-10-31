.PHONY: install lint format typecheck test check hooks run admin api image up

install:
	uv sync --group dev

lint:
	uv run ruff check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run ty check

test:
	uv run pytest

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	uv run pytest

hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit .githooks/pre-push

run:
	uv run python -m steward

admin:
	uv run python -m steward.admin

api:
	uv run python -m steward.api

image:
	docker build -t steward .

up:
	docker compose up --build
