.PHONY: help sync test lint data doctor api portal web demo demo-reset evaluate

help:
	@echo "targets: sync test lint data doctor api portal web demo demo-reset evaluate"

sync:
	uv sync

test:
	uv run pytest -q

lint:
	uv run ruff check .

data:
	uv run python -m synth.make_dataset

doctor:
	@bash scripts/doctor.sh

api:
	uv run uvicorn backend.app.main:app --reload --port 8000

portal:
	uv run uvicorn mock_portal.app:app --reload --port 8100

web:
	@if [ -f frontend/package.json ]; then cd frontend && npm install && npm run dev; \
	else echo "frontend not scaffolded yet (v1)"; fi

demo:
	uv run python scripts/demo.py

demo-reset:
	uv run python scripts/demo.py --reset --no-start-services

evaluate:
	uv run python scripts/evaluate.py
