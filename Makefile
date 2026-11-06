.PHONY: up test lint smoke seed reset migrate
up:
	docker compose up --build -d --wait
test:
	python -m pytest -m 'not integration'
lint:
	ruff check .
	ruff format --check .
smoke:
	RUN_INTEGRATION=1 python -m pytest -m integration -v
seed:
	python scripts/seed.py
migrate:
	docker compose run --rm migrate
reset:
	docker compose down -v --remove-orphans

delete-demo:
	python scripts/deletion_demo.py
