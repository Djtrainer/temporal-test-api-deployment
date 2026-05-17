TEMPORAL_HOST ?= localhost:7233
TEMPORAL_TLS ?= false
TEMPORAL_TASK_QUEUE ?= demo-task-queue

.PHONY: install temporal api worker compose-up compose-down compose-logs docker-build smoke

# Install deps into a local venv (requires uv: `brew install uv`)
install:
	uv sync || uv pip install -e .

# Local Temporal dev server (requires temporal CLI: `brew install temporal`)
temporal:
	temporal server start-dev

# API with hot-reload
api:
	TEMPORAL_HOST=$(TEMPORAL_HOST) TEMPORAL_TLS=$(TEMPORAL_TLS) TEMPORAL_TASK_QUEUE=$(TEMPORAL_TASK_QUEUE) \
	uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000

# Worker
worker:
	TEMPORAL_HOST=$(TEMPORAL_HOST) TEMPORAL_TLS=$(TEMPORAL_TLS) TEMPORAL_TASK_QUEUE=$(TEMPORAL_TASK_QUEUE) \
	uv run python -m app.worker

# Bring everything up via docker compose (temporal + api + worker)
compose-up:
	docker compose up --build

compose-down:
	docker compose down

compose-logs:
	docker compose logs -f --tail=100

# Run api + worker against the deployed GCP Temporal Server (uses .env)
compose-gcp-up:
	docker compose -f docker-compose.gcp.yml up --build

compose-gcp-down:
	docker compose -f docker-compose.gcp.yml down

compose-gcp-logs:
	docker compose -f docker-compose.gcp.yml logs -f --tail=100

# Build the image used for Cloud Run (also used by docker-compose)
docker-build:
	docker build -f docker/Dockerfile -t temporal-test-api:latest .

# End-to-end smoke test: starts a workflow, prints the result
smoke:
	curl -fsS -X POST http://localhost:8000/hello \
	  -H 'Content-Type: application/json' \
	  -d '{"name":"world"}' | jq .
