# fastAPItestback

A single **async FastAPI** application with a **persistent background worker**, containerised with Docker and ready for deployment on **AWS ECS Fargate**.

---

## How It Works

The app runs as one process inside one Docker container (one ECS task):

```
ECS Fargate Task: fastapi-app
└── uvicorn (single process, async event loop)
    ├── HTTP endpoints  — handle requests without blocking the event loop
    └── Background worker loop  — drains task_queue concurrently in the same event loop
```

### Background task flow

```
Client                    FastAPI App                  Background Worker
  │                           │                               │
  │  POST /task               │                               │
  │ ─────────────────────────►│                               │
  │                           │  queue.put(task_id, ...)      │
  │  202 Accepted (instant)   │ ──────────────────────────────│
  │ ◄─────────────────────────│                               │
  │                           │             await asyncio.sleep(duration)
  │                           │                               │ (non-blocking)
  │  GET /task/{task_id}      │                               │
  │ ─────────────────────────►│                               │
  │  {"status": "running"…}   │                               │
  │ ◄─────────────────────────│                               │
  │                           │    task_results[id] = done    │
  │  GET /task/{task_id}      │ ◄─────────────────────────────│
  │ ─────────────────────────►│                               │
  │  {"status": "completed"…} │                               │
  │ ◄─────────────────────────│                               │
```

---

## Project Structure

```
.
├── main.py               # Single async FastAPI app + background worker
├── requirements.txt
├── Dockerfile
├── docker-compose.yml    # Local development
└── ecs/
    └── task-definition.json   # ECS Fargate task definition
```

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Service info |
| `GET` | `/health` | ECS health check (includes queue size) |
| `POST` | `/task` | Submit a task — returns **202 immediately** |
| `GET` | `/task/{task_id}` | Poll task status (`queued` → `running` → `completed`) |
| `GET` | `/items/{item_id}` | Async item lookup (`?description=true` for details) |

---

## Running Locally with Docker Compose

```bash
docker-compose up --build
```

Then exercise the app:

```bash
# Health check
curl http://localhost:8000/health

# Submit a background task (returns 202 immediately)
curl -X POST http://localhost:8000/task \
  -H "Content-Type: application/json" \
  -d '{"name": "my-task", "duration_seconds": 5}'

# Poll status using the task_id from the previous response
curl http://localhost:8000/task/<task_id>

# Async item lookup
curl "http://localhost:8000/items/42?description=true"
```

Interactive API docs: http://localhost:8000/docs

---

## Deploying to AWS ECS Fargate

### 1. Build and push the image to ECR

```bash
# Authenticate
aws ecr get-login-password --region YOUR_REGION | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com

# Create ECR repository
aws ecr create-repository --repository-name fastapi-app

# Build and push
docker build -t fastapi-app .
docker tag fastapi-app:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/fastapi-app:latest
docker push \
  YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/fastapi-app:latest
```

### 2. Update the task definition

Edit `ecs/task-definition.json`, replacing:
- `YOUR_ACCOUNT_ID` → your AWS account ID
- `YOUR_REGION` → your AWS region (e.g. `us-east-1`)

### 3. Register the task definition and create the service

```bash
# Create log group
aws logs create-log-group --log-group-name /ecs/fastapi-app

# Register task definition
aws ecs register-task-definition \
  --cli-input-json file://ecs/task-definition.json

# Create a cluster (if needed)
aws ecs create-cluster --cluster-name fastapi-demo

# Create the ECS service
aws ecs create-service \
  --cluster fastapi-demo \
  --service-name fastapi-app \
  --task-definition fastapi-app \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration \
    "awsvpcConfiguration={subnets=[YOUR_SUBNET],securityGroups=[YOUR_SG],assignPublicIp=ENABLED}"
```

The single running Fargate task will serve HTTP traffic **and** continuously process background tasks — no second service needed.