import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel
from temporalio.client import Client
from temporalio.worker import Worker

from app.activities import say_hello
from app.client import get_temporal_client
from app.config import settings
from app.workflows import HelloWorkflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Temporal, share the Client with endpoints, run a Worker in-process."""
    logger.info(
        "Connecting to Temporal host=%s namespace=%s tls=%s",
        settings.temporal_host,
        settings.temporal_namespace,
        settings.temporal_tls,
    )
    client = await get_temporal_client()
    app.state.temporal_client = client

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[HelloWorkflow],
        activities=[say_hello],
    )
    logger.info("Starting in-process worker on task_queue=%s", settings.temporal_task_queue)
    worker_task = asyncio.create_task(worker.run())

    try:
        yield
    finally:
        logger.info("Shutting down worker...")
        await worker.shutdown()
        await worker_task
        logger.info("Worker stopped.")


app = FastAPI(title="Temporal demo API", lifespan=lifespan)


def get_client(request: Request) -> Client:
    return request.app.state.temporal_client


class HelloRequest(BaseModel):
    name: str


class HelloResponse(BaseModel):
    workflow_id: str
    result: str


class StartedResponse(BaseModel):
    workflow_id: str


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "ok": True,
        "temporal_host": settings.temporal_host,
        "temporal_namespace": settings.temporal_namespace,
        "temporal_task_queue": settings.temporal_task_queue,
        "temporal_tls": settings.temporal_tls,
    }


@app.post("/hello", response_model=HelloResponse)
async def hello(req: HelloRequest, client: Client = Depends(get_client)) -> HelloResponse:
    """Start a workflow and block until it completes. Good for demos, not for production endpoints."""
    workflow_id = f"hello-{uuid4()}"
    handle = await client.start_workflow(
        HelloWorkflow.run,
        req.name,
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    try:
        result = await handle.result()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return HelloResponse(workflow_id=workflow_id, result=result)


@app.post("/hello/async", response_model=StartedResponse)
async def hello_async(req: HelloRequest, client: Client = Depends(get_client)) -> StartedResponse:
    """Start a workflow and return its ID immediately. Caller polls /workflow/{id} for status."""
    workflow_id = f"hello-{uuid4()}"
    await client.start_workflow(
        HelloWorkflow.run,
        req.name,
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    return StartedResponse(workflow_id=workflow_id)


@app.get("/workflow/{workflow_id}")
async def workflow_status(workflow_id: str, client: Client = Depends(get_client)) -> dict[str, object]:
    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    return {
        "workflow_id": workflow_id,
        "status": desc.status.name if desc.status else "UNKNOWN",
        "run_id": desc.run_id,
        "start_time": desc.start_time.isoformat() if desc.start_time else None,
        "close_time": desc.close_time.isoformat() if desc.close_time else None,
    }
