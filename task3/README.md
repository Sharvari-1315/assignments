# Kubernetes Observability Stack

A complete observability setup for a Minikube-based Kubernetes cluster using Prometheus, Grafana, Loki, Fluent Bit, Alertmanager, and Jaeger.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MINIKUBE CLUSTER                         │
│                                                                 │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────┐   │
│  │    myapp     │   │node-exporter │   │kube-state-metrics│   │
│  │ (Deployment) │   │ (DaemonSet)  │   │  (Deployment)    │   │
│  │  Port: 30000 │   │ Port: 32090  │   │  Port: 32100     │   │
│  └──────┬───────┘   └──────┬───────┘   └────────┬─────────┘   │
│         │                  │                     │             │
│  ┌──────▼─────────────────────────────────────── ▼─────────┐   │
│  │               Fluent Bit (DaemonSet)                     │   │
│  │         Collects logs from /var/log/containers           │   │
│  └──────────────────────────┬───────────────────────────────┘   │
│                             │ ships logs                        │
│  ┌──────────────────────────▼──────────────────────────────┐   │
│  │                 Jaeger (Deployment)                      │   │
│  │          Distributed Tracing  NodePort: 31686            │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────┬──────────────────────────────────────────────┘
                   │ scrape metrics / receive logs
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EC2 HOST (Docker)                          │
│                                                                 │
│  ┌────────────┐  ┌──────────┐  ┌─────────┐  ┌─────────────┐  │
│  │ Prometheus │  │   Loki   │  │ Grafana │  │Alertmanager │  │
│  │ Port: 9090 │  │Port: 3100│  │Port:3000│  │ Port: 9093  │  │
│  └─────┬──────┘  └────┬─────┘  └────┬────┘  └──────┬──────┘  │
│        │              │             │               │         │
│        └──────────────┴─────────────┘               │         │
│                   Grafana reads all         Prometheus fires   │
│                   three data sources        alerts here        │
│                                                    │           │
│                                             PagerDuty          │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
.
├── alertmanager/
│   └── alertmanager.yml          # Alertmanager config with PagerDuty integration
├── codes/
│   ├── Dockerfile                # Python app container
│   ├── main.py                   # FastAPI Todo app with Prometheus metrics
│   └── requirements.txt          # Python dependencies
├── docker-compose.yml            # Prometheus, Loki, Grafana, Alertmanager
├── jaeger/
│   └── jaeger.yaml               # Jaeger deployment + NodePort service in Minikube
├── loki/
│   ├── configmap.yaml            # Fluent Bit configuration
│   ├── daemonset.yaml            # Fluent Bit DaemonSet
│   ├── loki-config.yml           # Loki server configuration
│   └── rbac.yaml                 # Fluent Bit RBAC permissions
├── manifests/
│   ├── deployment.yaml           # myapp Deployment + NodePort service
│   ├── kube-state-metric.yaml    # kube-state-metrics Deployment + RBAC
│   └── node-exporter.yaml        # Node Exporter DaemonSet + service
└── prometheus/
    ├── alerts.yml                # Alerting rules for pods, nodes, and app
    └── prometheus.yml            # Prometheus scrape config
```

---

## Components

### Application (`codes/`)

A FastAPI-based Todo REST API that exposes Prometheus metrics automatically via `prometheus-fastapi-instrumentator`.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/todos` | Get all todos |
| POST | `/todos/{title}` | Create a todo |
| PUT | `/todos/{todo_id}/{title}` | Update a todo |
| DELETE | `/todos/{todo_id}` | Delete a todo |
| GET | `/metrics` | Prometheus metrics endpoint |

The app is deployed in the `myapp` namespace with 2 replicas and exposed on NodePort `30000`. The Docker image is built locally inside Minikube using `eval $(minikube docker-env)` and `imagePullPolicy: Never`.

---

### Metrics (`prometheus/`)

Prometheus runs as a Docker container on the EC2 host with `network_mode: host` so it can reach Minikube's NodePort services directly via the Minikube IP (`192.168.49.2`).

**Scrape targets:**

| Job | Target | What it collects |
|-----|--------|-----------------|
| `prometheus` | `localhost:9090` | Prometheus self-metrics |
| `todo-app` | `192.168.49.2:30000` | App request metrics |
| `node-exporter` | `192.168.49.2:32090` | Node CPU, memory, disk |
| `kube-state-metrics` | `192.168.49.2:32100` | Pod and deployment state |

**Design decision:** Prometheus uses `network_mode: host` so it can reach the Minikube IP without extra networking. NodePorts act as the bridge between the Docker host and the Kubernetes cluster.

---

### Alerting (`prometheus/alerts.yml` + `alertmanager/`)

Alerts are grouped into three categories and routed to PagerDuty via Alertmanager.

**Pod Alerts:**

| Alert | Condition | Severity |
|-------|-----------|----------|
| PodNotRunning | Pod not in Running phase for 2m | critical |
| PodCrashLooping | High restart rate for 2m | critical |
| PodNotReady | Pod not ready for 2m | warning |
| PodOOMKilled | Container OOM killed | critical |
| PodHighCPU | CPU > 80% for 2m | warning |
| PodHighMemory | Memory > 85% for 2m | warning |
| PodStuckPending | Pending for more than 5m | warning |
| ContainerWaiting | CrashLoopBackOff / ImagePullBackOff | critical |

**Node Alerts:**

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighCPUUsage | CPU > 80% for 2m | critical |
| HighMemoryUsage | Memory > 85% for 2m | warning |

**App Alerts:**

| Alert | Condition | Severity |
|-------|-----------|----------|
| HighRequestLatency | p95 latency > 1s for 2m | warning |
| HighErrorRate | 5xx error rate > 0.05 for 1m | critical |

Alertmanager groups alerts by `alertname`, `pod`, and `namespace` with a 10s group wait and 60s repeat interval, forwarding to PagerDuty with dynamic severity and description from alert labels.

---

### Log Aggregation (`loki/`)

Logs flow from pods → Fluent Bit → Loki → Grafana.

**Fluent Bit** runs as a DaemonSet in the `logging` namespace on every Minikube node. It reads container logs from `/var/log/containers/*.log`, enriches them with Kubernetes metadata (namespace, pod name, container name), and ships them to Loki on the EC2 host (`65.0.117.83:3100`).

Fluent Bit runs as root (`runAsUser: 0`, `privileged: true`) because container log files on the host node are only readable by root. It supports both `docker` and `cri` log parsers since Minikube uses containerd (CRI) as its runtime.

**Loki** runs as a Docker container on the EC2 host. It uses schema `v13` with `tsdb` index storage and `allow_structured_metadata: false` for compatibility. The `user: "0"` setting in docker-compose is required to allow Loki to create its storage directories.

**Design decision:** Loki is kept outside the cluster alongside Prometheus and Grafana so all observability tooling is centralized on the EC2 host and is not affected by cluster restarts.

---

### Distributed Tracing (`jaeger/`)

Jaeger runs inside the Minikube cluster as a single all-in-one deployment in the `default` namespace with OTLP ingestion enabled.

**Exposed ports via NodePort:**

| Port | NodePort | Purpose |
|------|----------|---------|
| 16686 | 31686 | Jaeger UI |
| 4318 | 31318 | OTLP HTTP trace ingestion |

**Design decision:** Jaeger is deployed inside Minikube (not on EC2 via Docker) so applications running in the cluster can reach it via Kubernetes DNS (`jaeger.default.svc.cluster.local:4318`) without routing through the EC2 host. The Jaeger UI is then added as a data source in Grafana using the Minikube IP and NodePort `31686`.

---

### Visualization (Grafana)

Grafana runs as a Docker container on the EC2 host with `network_mode: host`. It connects to three data sources providing the three pillars of observability in one place.

| Data Source | URL | What you see |
|-------------|-----|-------------|
| Prometheus | `localhost:9090` | Metrics and dashboards |
| Loki | `http://loki:3100` | Pod and application logs |
| Jaeger | `http://192.168.49.2:31686` | Distributed traces |

---

## EC2 Security Group — Required Open Ports

| Port | Service |
|------|---------|
| 3000 | Grafana UI |
| 9090 | Prometheus UI |
| 9093 | Alertmanager |
| 3100 | Loki API |
| 31686 | Jaeger UI (Minikube NodePort) |
| 31318 | Jaeger OTLP HTTP (Minikube NodePort) |

---

## Kubernetes Resources

| Resource | Namespace | Type | NodePort |
|----------|-----------|------|----------|
| myapp-deployment | myapp | Deployment (2 replicas) | 30000 |
| node-exporter | default | DaemonSet | 32090 |
| kube-state-metrics | default | Deployment | 32100 |
| fluent-bit | logging | DaemonSet | — |
| jaeger | default | Deployment | 31686, 31318 |

---

## Useful Queries

### Prometheus (Metrics)
```promql
# Running pods per namespace
count by (namespace) (kube_pod_status_phase{phase="Running", namespace=~"myapp|default"})

# Pod restarts
sum by (pod, namespace) (kube_pod_container_status_restarts_total{namespace=~"myapp|default"})

# CPU usage by namespace
sum by (namespace) (rate(container_cpu_usage_seconds_total{container!="", namespace=~"myapp|default"}[5m]))

# Memory usage by namespace in MB
sum by (namespace) (container_memory_usage_bytes{container!="", namespace=~"myapp|default"}) / 1024 / 1024

# OOM events
count by (namespace, pod) (kube_pod_container_status_last_terminated_reason{reason="OOMKilled", namespace=~"myapp|default"})
```

### Loki (Logs)
```logql
# All logs from myapp namespace
{namespace="myapp"}

# Error logs across namespaces
{namespace=~"myapp|default"} |= "error"

# Logs by specific pod
{namespace="myapp", pod=~"myapp.*"}

# CrashLoop related logs
{namespace=~"myapp|default"} |= "CrashLoop"
```
