# fastAPItestback

A FastAPI project that demonstrates **synchronous** and **asynchronous** service patterns with Docker, designed for deployment on **AWS ECS (Fargate)**.

---

## Project Structure

```
.
├── sync_service/          # Synchronous FastAPI service (port 8000)
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── async_service/         # Asynchronous FastAPI service with background tasks (port 8001)
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
├── ecs/                   # ECS Fargate task definitions
│   ├── sync-task-definition.json
│   └── async-task-definition.json
└── docker-compose.yml     # Local development
```

---

## Services

### Sync Service (port 8000)

Handles requests using regular blocking Python functions (`def`). Uses `time.sleep()` to simulate blocking I/O (e.g., a synchronous database call). On ECS, you scale horizontally by adding more replicas because each worker thread is blocked while processing a request.

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Service info |
| `/health` | GET | ECS health check |
| `/task` | POST | Run a blocking sync task |
| `/items/{item_id}` | GET | Fetch an item (blocking DB simulation) |

### Async Service (port 8001)

Handles requests using `async def` coroutines. Long-running work is offloaded to **FastAPI BackgroundTasks** — the HTTP response is returned immediately (202 Accepted) and the task runs in the background. Uses `asyncio.sleep()` so the event loop is never blocked, enabling high concurrency with a single process.

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Service info |
| `/health` | GET | ECS health check |
| `/task` | POST | Submit a background task (returns 202 immediately) |
| `/task/{task_id}` | GET | Poll background task status |
| `/items/{item_id}` | GET | Fetch an item (non-blocking async simulation) |

---

## Sync vs Async — Key Difference

| | Sync Service | Async Service |
|---|---|---|
| Function type | `def` (blocking) | `async def` (non-blocking) |
| Sleep | `time.sleep()` | `asyncio.sleep()` |
| Response time | Waits for work to complete | Returns immediately (202) |
| Concurrency | Multiple workers / replicas | Single process, event loop |
| Best for | CPU-bound / legacy blocking code | I/O-bound / high-concurrency |

---

## Running Locally with Docker Compose

```bash
# Build and start both services
docker-compose up --build

# Sync service
curl http://localhost:8000/health
curl http://localhost:8000/items/1
curl -X POST http://localhost:8000/task \
  -H "Content-Type: application/json" \
  -d '{"name": "my-sync-task", "duration_seconds": 2}'

# Async service
curl http://localhost:8001/health
curl http://localhost:8001/items/1

# Submit a background task (returns immediately with task_id)
curl -X POST http://localhost:8001/task \
  -H "Content-Type: application/json" \
  -d '{"name": "my-async-task", "duration_seconds": 5}'

# Poll status using the task_id from the previous response
curl http://localhost:8001/task/<task_id>
```

**Interactive API docs** are available at:
- Sync service: http://localhost:8000/docs
- Async service: http://localhost:8001/docs

---

## Deploying to AWS ECS (Fargate)

### 1. Push images to ECR

```bash
# Authenticate
aws ecr get-login-password --region YOUR_REGION | \
  docker login --username AWS --password-stdin YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com

# Create ECR repositories
aws ecr create-repository --repository-name sync-service
aws ecr create-repository --repository-name async-service

# Build and push
docker build -t sync-service ./sync_service
docker tag sync-service:latest YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/sync-service:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/sync-service:latest

docker build -t async-service ./async_service
docker tag async-service:latest YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/async-service:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/async-service:latest
```

### 2. Update task definitions

Edit `ecs/sync-task-definition.json` and `ecs/async-task-definition.json`, replacing:
- `YOUR_ACCOUNT_ID` with your AWS account ID
- `YOUR_REGION` with your AWS region (e.g., `us-east-1`)

### 3. Register task definitions

```bash
aws ecs register-task-definition --cli-input-json file://ecs/sync-task-definition.json
aws ecs register-task-definition --cli-input-json file://ecs/async-task-definition.json
```

### 4. Create CloudWatch log groups

```bash
aws logs create-log-group --log-group-name /ecs/sync-service
aws logs create-log-group --log-group-name /ecs/async-service
```

### 5. Create ECS services

```bash
# Create a cluster (if not already existing)
aws ecs create-cluster --cluster-name fastapi-demo

# Create the sync ECS service
aws ecs create-service \
  --cluster fastapi-demo \
  --service-name sync-service \
  --task-definition sync-service \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[YOUR_SUBNET],securityGroups=[YOUR_SG],assignPublicIp=ENABLED}"

# Create the async ECS service
aws ecs create-service \
  --cluster fastapi-demo \
  --service-name async-service \
  --task-definition async-service \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[YOUR_SUBNET],securityGroups=[YOUR_SG],assignPublicIp=ENABLED}"
```

> **Note:** The sync service benefits from `--desired-count 2` (or more) because each worker blocks during request processing. The async service can handle many concurrent requests with a single task due to the event loop.

---

## How It Works on ECS

```
ECS Cluster: fastapi-demo
├── Service: sync-service   (2 Fargate tasks, port 8000)
│   └── Each task runs uvicorn with 4 workers
│       Workers block on time.sleep() / DB calls
│       Scale OUT (more tasks) for more throughput
│
└── Service: async-service  (1 Fargate task, port 8001)
    └── Single uvicorn process, async event loop
        Background tasks run concurrently without blocking
        Scale UP (more CPU/memory) for heavier workloads
```