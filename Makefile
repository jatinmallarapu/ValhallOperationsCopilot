# Offline replay uses the same graph and API as imported CDF snapshots.
.PHONY: dev test eval lint up frontend
dev:
	uvicorn app.main:app --host 127.0.0.1 --port 8000
test:
	python -m pytest -q
eval:
	python scripts/evaluate.py
lint:
	ruff check .
	mypy backend/app
up:
	docker compose up --build
frontend:
	cd frontend && npm ci && npm run build
