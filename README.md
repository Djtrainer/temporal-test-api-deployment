# temporal-test-api-deployment

Dummy FastAPI app that triggers a Temporal workflow. Designed to run:

1. **Locally** against a Temporal dev server (`temporal server start-dev`)
2. **Locally via Docker Compose** (single command, no Python tooling required)
3. **On Cloud Run** against the deployed Temporal Server from
   [`temporal-test-deployment`](../temporal-test-deployment/)

## What it does

- `POST /hello` — starts `HelloWorkflow`, blocks until result, returns it
- `POST /hello/async` — starts the workflow and returns the workflow ID immediately
- `GET /workflow/{id}` — returns workflow status / run id / timestamps
- `GET /health` — sanity check that also echoes back the Temporal connection settings

`HelloWorkflow` runs two `say_hello` activities with a 2-second `workflow.sleep`
between them — enough events to see a real history in the Temporal UI.

## Layout

```
app/
  activities.py    say_hello activity
  workflows.py     HelloWorkflow
  api.py           FastAPI entrypoint
  worker.py        Temporal worker entrypoint
  client.py        shared Client.connect factory
  config.py        env-driven settings (pydantic-settings)
docker/Dockerfile  shared image used by api + worker (and Cloud Run)
docker-compose.yml temporal-dev + api + worker
```

The **API and worker are separate processes**. They share workflow/activity code
but have independent lifecycles — the worker keeps polling task queues even when
the API restarts.

## Running locally (Python, three terminals)

Prereqs: `brew install uv temporal` (or equivalent installers).

```sh
# Terminal 1 — Temporal dev server (in-memory, UI at http://localhost:8233)
temporal server start-dev

# Terminal 2 — worker
make worker            # or:  uv run python -m app.worker

# Terminal 3 — API
make api               # or:  uv run uvicorn app.api:app --reload
```

Then hit it:

```sh
curl -X POST http://localhost:8000/hello -H 'Content-Type: application/json' -d '{"name":"world"}'
```

You should get back something like `{"workflow_id":"hello-...","result":"Hello, world! ... | Hello, dlrow! ..."}`,
and the workflow will appear in the Temporal UI at http://localhost:8233.

## Running locally (Docker Compose)

No Python tooling needed. One command brings up Temporal, the API, and the worker:

```sh
docker compose up --build
```

Same curl command as above. Temporal UI at http://localhost:8233.

## Connecting to the deployed GCP Temporal Server

After `temporal-test-deployment` has been applied and the server URL is known
(e.g. `https://temporal-server-x6zanzgmrq-uc.a.run.app`), point this app at it
by setting three env vars:

```sh
export TEMPORAL_HOST=temporal-server-x6zanzgmrq-uc.a.run.app:443
export TEMPORAL_TLS=true
export TEMPORAL_NAMESPACE=default

# Then run the worker + api as usual:
make worker  &
make api
```

The same code runs against local-dev Temporal and Cloud-Run-hosted Temporal —
only the env vars change.

## Deploying the API + worker to Cloud Run

After the server is deployed in the sibling repo, push this image to Artifact
Registry and create two Cloud Run services pointing at it.

```sh
PROJECT_ID=stunning-vertex-437612-f6
REGION=us-central1
REPO=temporal
IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/temporal-test-api:latest
TEMPORAL_HOST=temporal-server-x6zanzgmrq-uc.a.run.app:443   # from the other repo's outputs

# 1. Build & push
gcloud builds submit --tag=$IMAGE

# 2. API — public, scales to zero
gcloud run deploy temporal-test-api \
  --image=$IMAGE --region=$REGION --project=$PROJECT_ID \
  --command=uvicorn --args=app.api:app,--host,0.0.0.0,--port,8080 \
  --port=8080 --allow-unauthenticated \
  --set-env-vars=TEMPORAL_HOST=$TEMPORAL_HOST,TEMPORAL_TLS=true,TEMPORAL_NAMESPACE=default,TEMPORAL_TASK_QUEUE=demo-task-queue

# 3. Worker — needs min-instances=1 to keep polling task queues
gcloud run deploy temporal-test-worker \
  --image=$IMAGE --region=$REGION --project=$PROJECT_ID \
  --command=python --args=-m,app.worker \
  --min-instances=1 --max-instances=1 \
  --no-cpu-throttling \
  --set-env-vars=TEMPORAL_HOST=$TEMPORAL_HOST,TEMPORAL_TLS=true,TEMPORAL_NAMESPACE=default,TEMPORAL_TASK_QUEUE=demo-task-queue
```

Notes on the worker on Cloud Run:
- `--min-instances=1` and `--no-cpu-throttling` are non-negotiable — the worker
  must stay alive *between* requests to poll the task queue. With CPU throttling
  it gets paused and starts dropping heartbeats.
- There's no ingress port for the worker; the `--port` flag is ignored.
- For real workloads the worker belongs on GKE/Compute Engine, not Cloud Run.
  Cloud Run is fine for this dummy app.

## Configuration reference

| env var | default | notes |
|---|---|---|
| `TEMPORAL_HOST` | `localhost:7233` | `host:port` of Temporal frontend |
| `TEMPORAL_NAMESPACE` | `default` | matches `auto-setup`'s default namespace |
| `TEMPORAL_TLS` | `false` | set `true` for Cloud Run / Temporal Cloud |
| `TEMPORAL_TASK_QUEUE` | `demo-task-queue` | must match between API and worker |
