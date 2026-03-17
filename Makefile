PYTHON ?= python3

.PHONY: setup lint typecheck test migrate seed demo up down logs migrate-docker seed-docker demo-docker

setup:
	$(PYTHON) -m pip install -e .[dev]

lint:
	ruff check .

typecheck:
	mypy app tests seed

test:
	pytest

migrate:
	alembic upgrade head

seed:
	$(PYTHON) -m seed.cli

demo:
	$(PYTHON) scripts/run_demo.py

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f api worker

migrate-docker:
	docker compose exec api alembic upgrade head

seed-docker:
	docker compose exec api python -m seed.cli

demo-docker:
	docker compose exec api python scripts/run_demo.py
