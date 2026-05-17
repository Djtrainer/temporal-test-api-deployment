import logging
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.client import get_temporal_client
from app.config import settings
from app.workflows import HelloWorkflow

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Temporal demo API")


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
async def hello(req: HelloRequest) -> HelloResponse:
    """Start a workflow and block until it completes. Good for demos, not for production endpoints."""
    client = await get_temporal_client()
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
async def hello_async(req: HelloRequest) -> StartedResponse:
    """Start a workflow and return its ID immediately. Caller polls /workflow/{id} for status."""
    client = await get_temporal_client()
    workflow_id = f"hello-{uuid4()}"
    await client.start_workflow(
        HelloWorkflow.run,
        req.name,
        id=workflow_id,
        task_queue=settings.temporal_task_queue,
    )
    return StartedResponse(workflow_id=workflow_id)


@app.get("/workflow/{workflow_id}")
async def workflow_status(workflow_id: str) -> dict[str, object]:
    client = await get_temporal_client()
    handle = client.get_workflow_handle(workflow_id)
    desc = await handle.describe()
    return {
        "workflow_id": workflow_id,
        "status": desc.status.name if desc.status else "UNKNOWN",
        "run_id": desc.run_id,
        "start_time": desc.start_time.isoformat() if desc.start_time else None,
        "close_time": desc.close_time.isoformat() if desc.close_time else None,
    }
