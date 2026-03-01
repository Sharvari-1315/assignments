# Task 1: Kubernetes Cluster Setup & Microservices Deployment

## Overview

This task sets up a Kubernetes cluster on Minikube and deploys a microservices-based application with three services — a React frontend (served by Nginx), a Python FastAPI backend, and a PostgreSQL database.

All external traffic enters through a single URL `http://dodo-app.local`. Nginx inside the frontend pod handles routing — serving the React UI for `/` and proxying `/api` calls to the backend service inside the cluster.

---

## Architecture Diagram

![Architecture](docs/architecture.png)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Nginx (reverse proxy) |
| Backend | Python 3.12, FastAPI, asyncpg |
| Database | PostgreSQL 16 |
| Container Runtime | Docker |
| Orchestration | Kubernetes (Minikube) |
| Ingress | Nginx Ingress Controller |

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Minikube | ≥ 1.33 | https://minikube.sigs.k8s.io/docs/start |
| kubectl | ≥ 1.29 | https://kubernetes.io/docs/tasks/tools |
| Docker | ≥ 24 | https://docs.docker.com/get-docker |

---

## Repository Structure

```
task1/
├── frontend/
│   ├── src/
│   │   ├── App.jsx            # Main React UI — CRUD operations
│   │   └── index.js           # React entry point
│   ├── public/
│   │   └── index.html         # HTML shell
│   ├── nginx.conf             # Serves React + proxies /api to backend
│   ├── Dockerfile             # Multi-stage: Node build → Nginx serve
│   └── package.json
│
├── backend/
│   ├── main.py                # FastAPI — CRUD routes, health checks, DB pool
│   ├── requirements.txt
│   └── Dockerfile             # Multi-stage: build deps → slim production image
│
├── k8s/
│   ├── base/
│   │   ├── namespace.yaml          # Namespace + Pod Security Standards
│   │   ├── configmap-secret.yaml   # App config + DB credentials
│   │   ├── postgres.yaml           # StatefulSet + PVC + headless Service
│   │   ├── backend.yaml            # Deployment + Service
│   │   ├── frontend.yaml           # Deployment + Service
│   │   └── ingress.yaml            # Nginx Ingress
│   ├── hpa/
│   │   └── hpa.yaml                # HPA for backend + frontend
│   ├── nw-policies/
│   │   └── nw-policies.yaml        # Zero-trust network rules
│   └── pdb/
│       └── pdb.yaml                # Pod Disruption Budgets
│
└── README.md
```

---

## Setup & Deployment

### Step 1: Start Minikube

```bash
minikube start --cpus=4 --memory=3072 --driver=docker
minikube addons enable ingress
minikube addons enable metrics-server
```

### Step 2: Point Docker to Minikube's daemon

```bash
eval $(minikube docker-env)
```

> Run this every time you open a new terminal or restart Minikube.

### Step 3: Build Docker images

```bash
docker build -t your-username/dodo-backend:latest ./backend/
docker build -t your-username/dodo-frontend:latest ./frontend/
```

### Step 4: Apply Kubernetes manifests

```bash
kubectl apply -f k8s/base/
kubectl apply -f k8s/hpa/
kubectl apply -f k8s/pdb/
kubectl apply -f k8s/nw-policies/
```

### Step 5: Add hosts entry

```bash
echo "$(minikube ip) dodo-app.local" | sudo tee -a /etc/hosts
```

### Step 6: Access the app

| What | URL |
|------|-----|
| Frontend UI | http://dodo-app.local |
| Backend API (via Nginx proxy) | http://dodo-app.local/api/items |

> Note: The backend is not directly exposed externally. All API calls go through Nginx inside the frontend pod which proxies `/api/` to `backend-service.dodo-app.svc.cluster.local:8000` inside the cluster.

---

## Kubernetes Features Implemented

| Feature | Implementation |
|---------|---------------|
| 3 Microservices | Frontend (React/Nginx), Backend (FastAPI), Database (PostgreSQL) |
| Deployments | Backend & Frontend with RollingUpdate strategy, revisionHistoryLimit for rollback |
| StatefulSet | PostgreSQL with volumeClaimTemplates (5Gi PVC) — data persists across restarts |
| Services | ClusterIP for all services; headless service for StatefulSet DNS |
| ConfigMaps | App config + PostgreSQL init SQL script |
| Secrets | DB credentials + DATABASE_URL injected at runtime |
| Ingress | Single entry point — dodo-app.local routes all traffic to frontend service |
| HPA | Backend & Frontend auto-scale on CPU utilization (1–3 pods) |
| Resource Limits | requests and limits defined on all 3 services |
| Liveness Probes | HTTP /health for frontend & backend; pg_isready shell for PostgreSQL |
| Readiness Probes | HTTP /ready for backend (verifies DB connection); /health for frontend |
| Network Policies | default-deny-all + explicit allow rules per service pair |
| Pod Disruption Budgets | minAvailable: 1 for frontend/backend; maxUnavailable: 0 for PostgreSQL |

---

## How Traffic Flows

```
1. User opens http://dodo-app.local
2. /etc/hosts resolves dodo-app.local → Minikube IP
3. Nginx Ingress Controller receives the request
4. Ingress routes ALL traffic to frontend-service (port 80)
5. Nginx inside the frontend pod:
      GET /        → serves React static files
      GET /api/*   → proxies to backend-service.dodo-app.svc.cluster.local:8000
6. FastAPI backend handles the API request
7. Backend queries PostgreSQL via asyncpg connection pool
8. Response flows back to the browser
```

---

## Security Design Decisions

**Non-root containers**
All containers run as non-root users — frontend as UID 101 (nginx user), backend as UID 1001, PostgreSQL as UID 999. This limits blast radius if a container is compromised.

**Pod Security Standards**
The namespace is labeled with `pod-security.kubernetes.io/enforce: restricted` which enforces security controls at namespace level — no privileged containers, no host network access, seccomp profiles required on all pods.

**Dropped Linux capabilities**
All Linux capabilities are dropped (`capabilities.drop: [ALL]`) on every container. Containers only have the minimum permissions needed to run.

**Secrets management**
Database credentials are stored in Kubernetes Secrets, never hardcoded in code or manifests. The backend reads DATABASE_URL from the Secret at runtime via environment variable injection.

**Network segmentation (Zero-trust)**
Default-deny-all policy blocks all traffic by default. Only these connections are explicitly allowed:
- Ingress controller → Frontend (port 80)
- Frontend → Backend (port 8000)
- Backend → PostgreSQL (port 5432)
- All pods → DNS (port 53)

**seccompProfile: RuntimeDefault**
Applied at pod level — restricts system calls a container can make to the Linux kernel.

**emptyDir volumes for Nginx**
Since readOnlyRootFilesystem is enforced, Nginx needs writable directories for cache, PID file, and temp files. emptyDir volumes provide ephemeral writable space without loosening the restriction.

---

## Useful Commands

```bash
# Check all resources
kubectl get all -n dodo-app

# Check HPA, PDB, Network Policies
kubectl get hpa -n dodo-app
kubectl get pdb -n dodo-app
kubectl get networkpolicy -n dodo-app

# View logs
kubectl logs -n dodo-app -l app=backend -f
kubectl logs -n dodo-app -l app=frontend -f
kubectl logs -n dodo-app -l app=postgres -f

# Connect to PostgreSQL directly
kubectl exec -it -n dodo-app statefulset/postgres -- psql -U dodo -d dodo_db

# Test HPA — run load against backend
kubectl run load-test --image=busybox -n dodo-app --rm -it \
  -- sh -c "while true; do wget -q -O- http://backend-service:8000/items; done"

# Watch HPA scale in real time
kubectl get hpa -n dodo-app -w

# Rollback a deployment
kubectl rollout undo deployment/backend -n dodo-app
kubectl rollout history deployment/backend -n dodo-app
```
