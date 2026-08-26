# SoroScan: Soroban Event Indexer 🔍

![Rust](https://img.shields.io/badge/Soroban-Rust-orange?style=for-the-badge&logo=rust) ![Django](https://img.shields.io/badge/Backend-Django-green?style=for-the-badge&logo=django) ![GraphQL](https://img.shields.io/badge/API-GraphQL-e535ab?style=for-the-badge&logo=graphql) ![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

[![Django CI](https://github.com/SoroScan/soroscan/actions/workflows/django.yml/badge.svg)](https://github.com/SoroScan/soroscan/actions/workflows/django.yml) [![Soroban CI](https://github.com/SoroScan/soroscan/actions/workflows/soroban.yml/badge.svg)](https://github.com/SoroScan/soroscan/actions/workflows/soroban.yml)

> **The Graph for Soroban — index, query, and subscribe to smart contract events.**

**SoroScan** is a developer-focused indexing service for Soroban smart contract events on the Stellar blockchain. It combines a Rust-based Soroban smart contract with a Django backend to provide real-time event ingestion, GraphQL/REST APIs, and webhook notifications.

Built for developers who need reliable event data without running their own infrastructure.

---

## ✨ Key Features

- **🦀 Soroban Native**: Rust smart contract with admin-controlled indexer whitelist and standardized event emission.
- **🐍 Django Backend**: Production-ready REST API with Django Rest Framework and PostgreSQL storage.
- **📊 GraphQL Playground**: Flexible event queries with Strawberry GraphQL — filter by contract, event type, ledger, or time range.
- **🔔 Webhook Subscriptions**: Real-time event notifications with HMAC-signed payloads via Celery + Redis.
- **⚡ Horizon Integration**: Stream ledger events directly from Stellar's Horizon API using `stellar-sdk`.

---

## 🏗️ Architecture Overview

SoroScan follows a **hybrid on-chain/off-chain pattern** for maximum flexibility and reliability.

```
┌─────────────────────┐     ┌──────────────────────┐     ┌─────────────────┐
│   Soroban Contract  │────▶│   Django Backend     │────▶│   PostgreSQL    │
│   (Event Emitter)   │     │   (Ingestion Layer)  │     │   (Storage)     │
└─────────────────────┘     └──────────────────────┘     └─────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                 ▼
              REST API          GraphQL API       Webhooks
```

1. **Smart Contract**: Emits structured `EventRecord` events with admin-controlled access.
2. **Ingestion Layer**: Streams events from Horizon/Soroban RPC and persists to PostgreSQL.
3. **Query Layer**: Exposes data via REST, GraphQL, and push-based webhooks.

---

## 🗂️ Project Structure

```
soroscan/
├── soroban-contracts/        # Rust smart contracts
│   └── soroscan_core/        # Core indexing contract
│       └── src/lib.rs        # Contract logic & event emission
└── django-backend/           # Python backend API
    └── soroscan/
        └── ingest/           # Ingestion & API module
            ├── models.py     # TrackedContract, ContractEvent, WebhookSubscription
            ├── views.py      # REST API viewsets
            ├── schema.py     # GraphQL schema (Strawberry)
            ├── stellar_client.py  # Soroban RPC interaction
            └── tasks.py      # Celery webhook dispatcher
```

---

## Environment Configuration

See [ENVIRONMENT.md](docs/ENVIRONMENT.md) for the complete list of required and optional environment variables, their types and defaults, and development, testing, and production examples.

---

## 🚀 Quick Start

Get SoroScan running locally in under 5 minutes with Docker Compose.

### Prerequisites

- Docker and Docker Compose
- (Optional) Rust + Soroban CLI for contract development

### Using Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/SoroScan/soroscan.git
cd soroscan

# 2. Copy environment file and configure if needed
cp django-backend/.env.example django-backend/.env

# 3. Start all services (PostgreSQL, Redis, Django, Celery)
docker-compose up --build

# The backend will be available at:
# - REST API: http://localhost:8000/api/events/
# - GraphQL Playground: http://localhost:8000/graphql/
# - Django Admin: http://localhost:8000/admin/
```

That's it! The stack auto-runs migrations on startup and supports live code reloading.

**Port Conflicts?** Edit `django-backend/.env` and uncomment the port override variables.

### Local Webhook Simulator

Test a webhook receiver without the Django backend, Celery, Redis, or PostgreSQL. The simulator in `tools/webhook-simulator/` sends the same JSON envelope and HMAC headers as production deliveries.

```bash
cd tools/webhook-simulator
pip install -e .
webhook-simulator --url http://127.0.0.1:8080/webhook --sample --secret test-secret
```

Docker:

```bash
docker compose -f tools/webhook-simulator/docker-compose.yml run --rm webhook-simulator \
  --url http://host.docker.internal:8080/webhook --sample --secret test-secret
```

See [tools/webhook-simulator/README.md](tools/webhook-simulator/README.md) and the [webhooks cookbook](docs/cookbook/webhooks.md).

### Manual Setup (Advanced)

<details>
<summary>Click to expand manual installation steps</summary>

#### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+

#### 1. Set up the backend

```bash
cd django-backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set DATABASE_URL to your local PostgreSQL instance

# Run migrations and start server
python manage.py migrate
python manage.py runserver
```

#### 2. Start Celery worker (separate terminal)

```bash
cd django-backend
source venv/bin/activate
celery -A soroscan worker --loglevel=info
```

#### 3. (Optional) Start Celery beat scheduler

```bash
cd django-backend
source venv/bin/activate
celery -A soroscan beat --loglevel=info
```

</details>

### Deploy the Smart Contract (Optional)

```bash
cd soroban-contracts/soroscan_core
cargo build --target wasm32-unknown-unknown --release

# Deploy to testnet
soroban contract deploy \
  --wasm target/wasm32-unknown-unknown/release/soroscan_core.wasm \
  --network testnet

# Update SOROSCAN_CONTRACT_ID in django-backend/.env
```

---

## 🚢 Production Deployment

SoroScan includes production-ready Kubernetes manifests for self-hosted deployments.

### Prerequisites

- Kubernetes cluster (1.19+)
- kubectl configured
- PostgreSQL database (managed or self-hosted)
- Redis instance (managed or self-hosted)
- Container registry with SoroScan image
- (Optional) External Secrets Operator for secret management

### 1. Build and Push Container Image

Build the backend image with gunicorn:

```bash
cd django-backend

# Create Dockerfile if not exists
cat > Dockerfile <<EOF
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -u 1000 -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Default command uses gunicorn (override in k8s manifests for workers)
CMD ["gunicorn", "soroscan.wsgi:application", "--bind", "0.0.0.0:8000"]
EOF

# Build and push
docker build -t your-registry/soroscan-backend:v1.0.0 .
docker push your-registry/soroscan-backend:v1.0.0
```

### 2. Configure Secrets

Create secrets using kubectl or External Secrets Operator:

```bash
kubectl create secret generic soroscan-secrets \
  --from-literal=SECRET_KEY='your-django-secret-key' \
  --from-literal=DATABASE_URL='postgresql://user:pass@host:5432/dbname' \
  --from-literal=REDIS_URL='redis://redis:6379/0' \
  --from-literal=SOROSCAN_CONTRACT_ID='CXXXXXXXX' \
  --from-literal=INDEXER_SECRET_KEY='your-indexer-key' \
  -n soroscan
```

Or use External Secrets Operator (see `k8s/secret-reference.yaml`).

### 3. Update Configuration

Edit `k8s/configmap.yaml`:
- Set `ALLOWED_HOSTS` to your domain
- Configure `SOROBAN_RPC_URL` and `STELLAR_NETWORK_PASSPHRASE` for your network
- Set `CORS_ALLOWED_ORIGINS` if needed

Edit `k8s/backend-deployment.yaml`, `k8s/worker-deployment.yaml`, `k8s/beat-cronjob.yaml`:
- Replace `soroscan/backend:v1.0.0` with your image

Edit `k8s/ingress.yaml`:
- Set your domain in `host` and `tls` sections
- Configure ingress class and annotations for your ingress controller

### 4. Deploy to Kubernetes

```bash
# Apply all manifests
kubectl apply -f k8s/

## Deployment Docs

For complete production deployment and operations guidance, see the `docs/deployment` section:

- Local Docker Compose: [docs/deployment/docker-compose](docs/deployment/docker-compose)
- Kubernetes (Helm + Terraform): [docs/deployment/kubernetes](docs/deployment/kubernetes)
- AWS EKS example: [docs/deployment/aws](docs/deployment/aws)
- Monitoring, backups, runbooks and troubleshooting: [docs/deployment/monitoring](docs/deployment/monitoring)


# Verify deployment
kubectl get pods -n soroscan
kubectl get svc -n soroscan
kubectl get ingress -n soroscan

# Check backend logs
kubectl logs -f deployment/soroscan-backend -n soroscan

# Check worker logs
kubectl logs -f deployment/soroscan-worker -n soroscan
```

### 5. Verify Deployment

```bash
# Check readiness
kubectl get pods -n soroscan -w

# Test API endpoint
curl https://your-domain.com/api/events/

# Check migrations completed
kubectl logs deployment/soroscan-backend -n soroscan --previous
```

### Architecture

The Kubernetes deployment includes:

- **Backend Deployment**: Django + gunicorn with readinessProbe on `/api/events/`
- **Worker Deployment**: Celery workers for default queue
- **Worker Backfill Deployment**: Dedicated workers for backfill queue
- **Beat Deployment**: Celery beat scheduler (single replica)
- **Service**: ClusterIP service exposing backend
- **Ingress**: HTTP/HTTPS routing to backend service

### Scaling

```bash
# Scale backend pods
kubectl scale deployment/soroscan-backend --replicas=4 -n soroscan

# Scale worker pods
kubectl scale deployment/soroscan-worker --replicas=3 -n soroscan

# Note: Beat scheduler must remain at 1 replica
```

### Troubleshooting

- **Migrations not running**: Check init container logs: `kubectl logs pod/soroscan-backend-xxx -n soroscan -c migrate`
- **Database connection failed**: Verify `DATABASE_URL` secret is correct
- **Redis connection failed**: Verify `REDIS_URL` secret and Redis accessibility
- **Readiness probe failing**: Check `/api/events/` endpoint is accessible after migrations

---

## 🤝 Contributing

1. Fork the repository and create your feature branch.
2. Look for issues labeled `good-first-issue` or `help-wanted`.
3. Submit a PR referencing the issue.

---

## 🗺️ Roadmap

### Phase 1: Core Infrastructure (Current)
- [x] Soroban smart contract with event emission
- [x] Django backend with REST API
- [x] GraphQL schema with Strawberry
- [x] Webhook subscriptions with Celery

### Phase 2: Production Readiness
- [x] Docker Compose setup for local development
- [x] Kubernetes manifests for production deployment
- [ ] Rate limiting and API authentication
- [ ] Comprehensive test suite

### Phase 3: Advanced Features
- [ ] Multi-contract indexing dashboard
- [ ] Historical backfill from Horizon archives
- [ ] Real-time WebSocket subscriptions
- [ ] SDK packages (Python, JavaScript)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 📚 Additional Documentation

- [CELERY.md](docs/cookbook/CELERY.md) — Celery worker queues, concurrency settings, and deployment examples
- [Architecture Overview](docs/architecture/README.md) — end-to-end system design, data flows, component interaction, and deployment architecture
- [Architecture Decision Records](docs/architecture/adr.md) — rationale for core technology and design choices
- [DATABASE_TUNING.md](docs/database/DATABASE_TUNING.md) — Recommended configuration settings for high-volume write workloads and indexing optimizations.
