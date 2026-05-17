# temporal-test-api-deployment

Template for a FastAPI service that runs a Temporal worker **in the same
container**. Built for the pattern where developers clone, add workflows,
and ship a single Cloud Run service against a centrally-deployed Temporal
Server.

## Single-container architecture

```
┌─────────────────────────────────────┐         ┌─────────────────────┐
│  uvicorn  (one process)             │  gRPC   │  Temporal Server    │
│  ┌────────────┐  ┌───────────────┐  │ ──TLS──►│  (Cloud Run / Cloud)│
│  │ FastAPI    │  │ Worker        │  │         └─────────────────────┘
│  │ endpoints  │  │ (lifespan)    │  │
│  └────────────┘  └───────────────┘  │
└─────────────────────────────────────┘
```

FastAPI's [lifespan](https://fastapi.tiangolo.com/advanced/events/) hook starts
the Temporal Worker as a background task on the same asyncio event loop, and
shares one `Client` with the request handlers. One image, one container,
one deploy.

## Endpoints

- `POST /hello` — starts `HelloWorkflow`, blocks until result, returns it
- `POST /hello/async` — starts and returns the workflow ID immediately
- `GET /workflow/{id}` — workflow status, run id, timestamps
- `GET /health` — echoes back the Temporal connection settings

`HelloWorkflow` runs two `say_hello` activities with a 2-second `workflow.sleep`
between them — enough events to see a real history in the Temporal UI.

## Layout

```
app/
  activities.py    say_hello — example activity
  workflows.py     HelloWorkflow — example workflow
  api.py           FastAPI + in-process Worker (lifespan hook)
  worker.py        (optional) standalone worker entrypoint for scale-out
  client.py        Client.connect factory
  config.py        env-driven settings
docker/Dockerfile  single image used locally and on Cloud Run
docker-compose.yml      local: temporal-dev + api (with embedded worker)
docker-compose.gcp.yml  local: api pointed at deployed GCP Temporal
.env.example      env var reference
.env              (gitignored) your local config
```

## Add a workflow (the template flow)

1. Define an activity in `app/activities.py`
2. Define a workflow in `app/workflows.py` that calls the activity
3. Register both in `app/api.py`'s lifespan (`Worker(workflows=[...], activities=[...])`)
4. Add an endpoint that calls `client.start_workflow(...)`

That's it. Local dev and Cloud Run deploy don't need any other changes.

## Run locally (Docker Compose, no Python tooling needed)

**Against a local Temporal dev server** (auto-spun-up):

```sh
docker compose up --build
# UI at http://localhost:8233, API at http://localhost:8000
```

**Against the deployed GCP Temporal Server** (uses `.env`):

```sh
cp .env.example .env   # then edit TEMPORAL_HOST + TEMPORAL_TLS=true
docker compose -f docker-compose.gcp.yml up --build
```

Smoke test either:

```sh
curl -X POST http://localhost:8000/hello \
  -H 'Content-Type: application/json' -d '{"name":"world"}'
```

## Run locally (native Python, faster iteration)

```sh
# one-time
uv sync   # or:  python -m venv .venv && pip install -e .

# foreground
uv run uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

Set `TEMPORAL_HOST` etc. via `.env` or env vars. With `--reload`, the worker
restarts when you edit a workflow/activity — fast feedback loop.

## Deploy to Cloud Run

Single service, single image. Two flags are non-negotiable for the
embedded-worker pattern:

| Flag | Why |
|---|---|
| `--min-instances=1` | Worker must keep polling task queues between requests |
| `--no-cpu-throttling` | Cloud Run pauses CPU on idle by default; that stalls the worker |

```sh
PROJECT=stunning-vertex-437612-f6
REGION=us-central1
REPO=temporal
IMAGE=$REGION-docker.pkg.dev/$PROJECT/$REPO/temporal-test-api:latest
TEMPORAL_HOST=temporal-server-x6zanzgmrq-uc.a.run.app:443   # from temporal-test-deployment outputs
TASK_QUEUE=demo-task-queue                                  # per-tenant: name it whatever

# 1. Build and push
gcloud builds submit --tag=$IMAGE --project=$PROJECT

# 2. Deploy
gcloud run deploy temporal-test-api \
  --image=$IMAGE --region=$REGION --project=$PROJECT \
  --port=8000 --allow-unauthenticated \
  --min-instances=1 --max-instances=3 \
  --no-cpu-throttling \
  --set-env-vars=TEMPORAL_HOST=$TEMPORAL_HOST,TEMPORAL_TLS=true,TEMPORAL_NAMESPACE=default,TEMPORAL_TASK_QUEUE=$TASK_QUEUE
```

Each developer's app should pick a **distinct task queue** (`TEMPORAL_TASK_QUEUE`)
so workers don't compete for each other's workflows. The Temporal namespace can
be shared (`default`) or per-tenant — your call.

## Configuration

| env var | default | notes |
|---|---|---|
| `TEMPORAL_HOST` | `localhost:7233` | `host:port` of Temporal frontend |
| `TEMPORAL_NAMESPACE` | `default` | matches `auto-setup`'s default |
| `TEMPORAL_TLS` | `false` | `true` for Cloud-Run-hosted Temporal or Temporal Cloud |
| `TEMPORAL_TASK_QUEUE` | `demo-task-queue` | per-deployment unique name |

## When to split worker out of the API

The consolidated pattern is the right default for prototypes. Split when you
hit one of these:

- **Long-running workflows (> minutes)** — API restarts kill in-flight workflow
  ticks; they'll retry on the next worker poll, but that adds latency you may
  not want.
- **CPU-heavy activities** — they compete with FastAPI request handling on the
  same event loop. A separate worker service can scale on different signals.
- **Different scaling profiles** — API needs to scale on request rate; worker
  needs to scale on task queue backlog. Splitting lets each do its own thing.

The standalone worker entrypoint at `app/worker.py` is preserved exactly for
this — you can deploy a second Cloud Run service running `python -m app.worker`
against the same image whenever you outgrow the single-container pattern.
