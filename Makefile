.PHONY: install lint format typecheck test version-check check bump hooks run admin api image up run-d

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

version-check:
	@root=$$(uv version --short); \
	client=$$(uv version --short --package steward-client); \
	test "$$root" = "$$client" || { echo "version mismatch: steward $$root, steward-client $$client"; exit 1; }

check: version-check
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check
	uv run pytest

bump:
	@test -n "$(PART)" || { echo "usage: make bump PART=patch|minor|major"; exit 1; }
	uv version --bump "$(PART)" --frozen
	uv version "$$(uv version --short)" --package steward-client --no-sync
	uv version --short

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

up run-d:
	docker compose up --build -d
