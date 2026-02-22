"""
Sync FastAPI Service
--------------------
Demonstrates synchronous request handling in FastAPI.
All endpoints use regular (blocking) Python functions.
On ECS this service runs as a dedicated sync task/container.
"""

import time
import logging
from fastapi import FastAPI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [SYNC] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sync Service",
    description="FastAPI service demonstrating synchronous request handling",
    version="1.0.0",
)


class TaskRequest(BaseModel):
    name: str
    duration_seconds: int = 1


class TaskResponse(BaseModel):
    message: str
    name: str
    elapsed_seconds: float


@app.get("/health")
def health_check():
    """Health check endpoint for ECS container health checks."""
    return {"status": "healthy", "service": "sync"}


@app.get("/")
def root():
    """Root endpoint with service info."""
    return {
        "service": "sync",
        "description": "Synchronous FastAPI service",
        "endpoints": ["/health", "/task", "/items/{item_id}"],
    }


@app.post("/task", response_model=TaskResponse)
def run_sync_task(request: TaskRequest):
    """
    Synchronous task endpoint.
    Blocks the worker thread for `duration_seconds` using time.sleep(),
    which simulates CPU-bound or blocking I/O work.
    On ECS, multiple replicas handle concurrent requests.
    """
    logger.info("Starting sync task '%s' (will block for %ds)", request.name, request.duration_seconds)
    start = time.time()
    time.sleep(request.duration_seconds)  # Simulates blocking work
    elapsed = round(time.time() - start, 3)
    logger.info("Finished sync task '%s' in %.3fs", request.name, elapsed)
    return TaskResponse(
        message=f"Sync task '{request.name}' completed",
        name=request.name,
        elapsed_seconds=elapsed,
    )


@app.get("/items/{item_id}")
def get_item(item_id: int, description: bool = False):
    """
    Sync endpoint that fetches an item by ID.
    Simulates a synchronous database lookup.
    """
    logger.info("Fetching item %d", item_id)
    time.sleep(0.1)  # Simulates a blocking DB call
    result = {"item_id": item_id, "name": f"Item-{item_id}", "service": "sync"}
    if description:
        result["description"] = f"This is a description for item {item_id}"
    return result
