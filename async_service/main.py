"""
Async FastAPI Service
---------------------
Demonstrates asynchronous request handling and background tasks in FastAPI.
All endpoints use `async def`, and long-running work is offloaded to
FastAPI BackgroundTasks so the response is returned immediately.
On ECS this service runs as a dedicated async task/container.
"""

import asyncio
import logging
import time
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ASYNC] %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Async Service",
    description="FastAPI service demonstrating asynchronous request handling and background tasks",
    version="1.0.0",
)

# In-memory store to track background task results (for demo purposes)
task_results: dict[str, dict] = {}


class TaskRequest(BaseModel):
    name: str
    duration_seconds: int = 2


class TaskResponse(BaseModel):
    message: str
    task_id: str


class TaskStatus(BaseModel):
    task_id: str
    status: str
    name: str
    elapsed_seconds: float | None = None


def _generate_task_id(name: str) -> str:
    return f"{name}-{int(time.time() * 1000)}"


async def process_background_task(task_id: str, name: str, duration_seconds: int) -> None:
    """
    Background task that runs asynchronously after the HTTP response has been sent.
    Uses asyncio.sleep() so it does NOT block the event loop, allowing the server
    to handle other requests while this task is running.
    """
    logger.info("Background task '%s' (id=%s) started", name, task_id)
    task_results[task_id] = {"status": "running", "name": name, "elapsed_seconds": None}
    start = time.time()
    await asyncio.sleep(duration_seconds)  # Non-blocking async wait
    elapsed = round(time.time() - start, 3)
    task_results[task_id] = {"status": "completed", "name": name, "elapsed_seconds": elapsed}
    logger.info("Background task '%s' (id=%s) completed in %.3fs", name, task_id, elapsed)


@app.get("/health")
async def health_check():
    """Health check endpoint for ECS container health checks."""
    return {"status": "healthy", "service": "async"}


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "async",
        "description": "Asynchronous FastAPI service with background tasks",
        "endpoints": ["/health", "/task", "/task/{task_id}", "/items/{item_id}"],
    }


@app.post("/task", response_model=TaskResponse, status_code=202)
async def submit_background_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """
    Async endpoint that immediately returns 202 Accepted and schedules
    `process_background_task` to run after the response is sent.
    The client can poll /task/{task_id} to check progress.

    This is the key difference vs the sync service:
    - Response is returned in milliseconds regardless of task duration.
    - The event loop is not blocked; other requests proceed concurrently.
    """
    task_id = _generate_task_id(request.name)
    background_tasks.add_task(
        process_background_task,
        task_id=task_id,
        name=request.name,
        duration_seconds=request.duration_seconds,
    )
    logger.info("Accepted background task '%s' (id=%s)", request.name, task_id)
    return TaskResponse(
        message=f"Task '{request.name}' accepted and running in the background",
        task_id=task_id,
    )


@app.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Poll the status of a previously submitted background task."""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    result = task_results[task_id]
    return TaskStatus(task_id=task_id, **result)


@app.get("/items/{item_id}")
async def get_item(item_id: int, description: bool = False):
    """
    Async endpoint that fetches an item by ID.
    Uses asyncio.sleep to simulate a non-blocking async DB/HTTP call.
    """
    logger.info("Fetching item %d (async)", item_id)
    await asyncio.sleep(0.1)  # Non-blocking simulated I/O
    result = {"item_id": item_id, "name": f"Item-{item_id}", "service": "async"}
    if description:
        result["description"] = f"Async description for item {item_id}"
    return result
