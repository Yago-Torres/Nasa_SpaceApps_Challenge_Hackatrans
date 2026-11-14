# Run from repository root. Python commands are exclusively uv-managed.
.PHONY: help setup backend web test context check infra-up infra-down
help:
	@printf 'make setup | make backend | make web | make test | make check | make context | make infra-up | make infra-down\n'
setup:
	cd backend && uv sync --extra dev
	cd frontend && npm install
backend:
	cd backend && uv run uvicorn agroblackbox.app:app --reload --port 8000
web:
	cd frontend && npm run dev
test:
	cd backend && uv run --extra dev pytest -q
context:
	uv run --no-project python scripts/check_context.py
check:
	uv run --no-project python scripts/check_context.py
	cd backend && uv run --extra dev pytest -q
	cd frontend && npm run build
infra-up:
	docker compose up -d
infra-down:
	docker compose down
