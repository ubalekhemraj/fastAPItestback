"""
FastAPI Application with Background Tasks
------------------------------------------
A single async FastAPI app that demonstrates:
  - Async request handling (async def endpoints, asyncio.sleep for non-blocking I/O)
  - Background tasks: POST /task returns 202 immediately; work runs in the background
  - Polling: GET /task/{task_id} lets clients check task progress
  - A continuously running background worker (started via lifespan) that processes
    tasks from an in-memory queue — demonstrating a persistent background loop on ECS

Deployment: one Docker container, one ECS Fargate task.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state (in-memory; replace with a real store like Redis in production)
# ---------------------------------------------------------------------------
task_results: dict[str, dict] = {}
task_queue: asyncio.Queue = asyncio.Queue()


# ---------------------------------------------------------------------------
# Persistent background worker — runs for the lifetime of the ECS container
# ---------------------------------------------------------------------------
async def background_worker() -> None:
    """
    Continuously drains `task_queue`.
    This coroutine is started once at app startup and keeps running until the
    container is stopped — demonstrating a long-lived background loop on ECS.
    """
    logger.info("Background worker started")
    while True:
        task_id, name, duration = await task_queue.get()
        logger.info("Worker picked up task '%s' (id=%s, duration=%ds)", name, task_id, duration)
        task_results[task_id] = {"status": "running", "name": name, "elapsed_seconds": None}
        start = time.time()
        await asyncio.sleep(duration)  # Non-blocking; event loop stays free
        elapsed = round(time.time() - start, 3)
        task_results[task_id] = {"status": "completed", "name": name, "elapsed_seconds": elapsed}
        logger.info("Worker finished task '%s' (id=%s) in %.3fs", name, task_id, elapsed)
        task_queue.task_done()


# ---------------------------------------------------------------------------
# Lifespan: start the background worker when the app boots
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(background_worker())
    logger.info("App started — background worker is running")
    yield
    worker_task.cancel()
    logger.info("App shutting down — background worker stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FastAPI Background Tasks",
    description=(
        "Single async FastAPI app with a persistent background worker. "
        "Submit tasks via POST /task; poll status via GET /task/{task_id}."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_task_id(name: str) -> str:
    return f"{name}-{int(time.time() * 1000)}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """ECS container health check."""
    return {"status": "healthy", "queue_size": task_queue.qsize()}


@app.get("/")
async def root():
    """Service info."""
    return {
        "service": "fastapi-background-tasks",
        "description": "Single async FastAPI app with a persistent background worker",
        "endpoints": {
            "GET  /health": "ECS health check",
            "POST /task": "Submit a background task (returns 202 immediately)",
            "GET  /task/{task_id}": "Poll background task status",
            "GET  /items/{item_id}": "Async item lookup",
        },
    }


@app.post("/task", response_model=TaskResponse, status_code=202)
async def submit_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """
    Submit a task for background processing.

    Returns 202 Accepted immediately — the work is queued and processed by the
    background worker without blocking this or any other request.
    Poll GET /task/{task_id} to check when it completes.
    """
    task_id = _make_task_id(request.name)
    # Reserve the slot so polling works before the worker picks it up
    task_results[task_id] = {"status": "queued", "name": request.name, "elapsed_seconds": None}
    # FastAPI BackgroundTasks enqueue the queue.put — it runs after the response is sent
    background_tasks.add_task(task_queue.put, (task_id, request.name, request.duration_seconds))
    logger.info("Accepted task '%s' (id=%s)", request.name, task_id)
    return TaskResponse(
        message=f"Task '{request.name}' queued — poll /task/{task_id} for status",
        task_id=task_id,
    )


@app.get("/task/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """Poll the status of a submitted background task."""
    if task_id not in task_results:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return TaskStatus(task_id=task_id, **task_results[task_id])


@app.get("/items/{item_id}")
async def get_item(item_id: int, description: bool = False):
    """
    Async item lookup — simulates a non-blocking database call.
    Uses asyncio.sleep so the event loop remains free while waiting.
    """
    logger.info("Fetching item %d", item_id)
    await asyncio.sleep(0.05)  # Simulated non-blocking I/O
    result = {"item_id": item_id, "name": f"Item-{item_id}"}
    if description:
        result["description"] = f"Description for item {item_id}"
    return result
