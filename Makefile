# Run from repository root. Python commands are exclusively uv-managed.
.PHONY: help setup backend web test context check db-upgrade db-downgrade infra-up infra-down
help:
	@printf 'make setup | make backend | make web | make test | make check | make context | make db-upgrade | make db-downgrade | make infra-up | make infra-down\n'
setup:
	cd backend && uv sync --locked --extra dev
	cd frontend && npm ci
backend:
	cd backend && uv run --locked uvicorn agroblackbox.app:app --reload --port 8000
web:
	cd frontend && npm run dev
test:
	cd backend && uv run --locked --extra dev pytest -q
context:
	uv run --no-project python scripts/check_context.py
check:
	uv run --no-project python scripts/check_context.py
	cd backend && uv lock --check
	cd backend && uv run --locked --extra dev pytest -q
	cd frontend && npm run build
db-upgrade:
	cd backend && uv run --locked alembic upgrade head
db-downgrade:
	cd backend && uv run --locked alembic downgrade -1
infra-up:
	docker compose up -d
infra-down:
	docker compose down
