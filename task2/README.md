# FastAPI CI/CD Pipeline with ArgoCD & Kustomize

## Overview

This project implements a **GitOps-based CI/CD pipeline** for a FastAPI application. Code changes are automatically linted, tested, containerized, and deployed to Kubernetes clusters via ArgoCD — with a manual approval gate before production promotion.

**Tech Stack:**
- **App:** FastAPI (Python 3.11)
- **Containerization:** Docker → DockerHub
- **Orchestration:** Kubernetes
- **Config Management:** Kustomize (base + overlays)
- **CI/CD:** GitHub Actions
- **GitOps:** ArgoCD
- **Environments:** Staging → Production (manual gate)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DEVELOPER WORKFLOW                           │
│                                                                     │
│   Code Change  ──►  Pull Request  ──►  Review  ──►  Merge to main  │
└─────────────────────────────┬───────────────────────────────────────┘
                              │  push to main (task2/test.txt changed)
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      GITHUB ACTIONS (CI)                            │
│                                                                     │
│   1. Checkout → Setup Python → Install Deps                         │
│   2. Lint (flake8)                                                  │
│   3. Test (pytest)                                                  │
│   4. Docker Build & Push ──► DockerHub (tagged with git SHA)        │
│   5. Update staging/kustomization.yaml with new image tag           │
│   6. Commit & Push GitOps change                                    │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
              ┌───────────────┴──────────────────┐
              ▼                                  ▼
┌─────────────────────────┐       ┌──────────────────────────────────┐
│   STAGING ENVIRONMENT   │       │     PRODUCTION ENVIRONMENT       │
│                         │       │                                  │
│  ArgoCD auto-syncs      │       │  ⛔ Requires Manual Approval     │
│  staging overlay        │       │  (GitHub Environment Protection) │
│                         │       │                                  │
│  Namespace: staging     │       │  ArgoCD syncs production overlay │
│  Replicas: 1            │       │  Namespace: production           │
│  NodePort: 30007        │       │  Replicas: 2                     │
└─────────────────────────┘       │  NodePort: 30008                 │
                                  └──────────────────────────────────┘
```

---

## Project Structure

```
task2/
├── app/
│   └── main.py                    # FastAPI application
├── tests/
│   └── test_app.py                # pytest test suite
├── k8s/
│   ├── base/                      # Shared Kubernetes manifests
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   └── kustomization.yaml
│   └── overlays/
│       ├── staging/               # Staging-specific patches
│       │   ├── patch-replicas.yaml
│       │   └── kustomization.yaml
│       └── production/            # Production-specific patches
│           ├── patch-replicas.yaml
│           ├── patch_service.yaml
│           └── kustomization.yaml
├── Dockerfile
├── requirements.txt
└── test.txt                       # Trigger file for CI pipeline
```

---

## CI/CD Pipeline

### Pipeline Stages

#### Stage 1: `deploy-staging`

| Step | Description |
|------|-------------|
| Checkout | Clone repository |
| Setup Python 3.11 | Prepare Python environment |
| Install Dependencies | `pip install -r task2/requirements.txt` |
| Lint | `flake8 task2/app` — enforces PEP8 style |
| Test | `pytest task2/tests` — runs unit/integration tests |
| Docker Build & Push | Builds image tagged with `${{ github.sha }}` |
| Update Kustomize | Sets new image tag in `staging/kustomization.yaml` |
| GitOps Commit | Commits updated manifest and pushes to repo |

#### Stage 2: `deploy-production`

> ⚠️ **This stage requires manual approval** via GitHub Environment protection rules.

| Step | Description |
|------|-------------|
| Checkout | Fresh checkout |
| Pull Latest | `git pull --rebase` to get staging commit |
| Update Kustomize | Sets same SHA image tag in `production/kustomization.yaml` |
| GitOps Commit | Commits and pushes — ArgoCD picks up the change |

---

## Kubernetes & Kustomize Setup

### Kustomize Base

The `base/` layer defines environment-agnostic resources:
- **Deployment:** 1 replica (overridden by overlays), image `devsharvari/fastapi-app:latest`
- **Service:** NodePort on port 30007, targeting container port 8000

### Overlays

Overlays patch the base config per environment without duplicating manifests:

| Config | Staging | Production |
|--------|---------|------------|
| Namespace | `staging` | `production` |
| Replicas | 1 | 2 |
| NodePort | 30007 | 30008 |
| Image Tag | `<git-sha>` | `<git-sha>` (same build, promoted) |


---

## GitOps with ArgoCD

ArgoCD watches the Git repository for changes to the Kustomize overlay files. When GitHub Actions commits an updated `kustomization.yaml` with a new image tag, ArgoCD automatically reconciles the cluster state.

For production, set `automated: {}` to disabled (or remove it) and sync manually after the GitHub approval gate triggers the GitOps commit.

---

## Branch Protection & Review Workflow

### Branch Protection Rules (main branch)

The following rules are configured on the `main` branch in GitHub repository settings:

- ✅ **Require pull request before merging** — no direct pushes to `main`
- ✅ **Require at least 1 approving review** before merge
- ✅ **Dismiss stale reviews** when new commits are pushed
- ✅ **Require status checks to pass** (lint + tests must be green)
- ✅ **Require branches to be up to date** before merging

### GitHub Environment Protection (Manual Approval Gate)

The `production` job has a `needs: deploy-staging` dependency, meaning it only starts after the staging job completes successfully. Once staging is deployed, a DevOps engineer validates the deployment on the staging environment — checking app health, logs, and behaviour — and only then approves the `production` job to proceed in GitHub Actions.

The `production` GitHub Environment is configured with:

- ✅ **Required reviewers** — DevOps engineer must manually approve after validating staging
- ✅ **Wait timer** (optional) — enforces a soak period to observe staging before approving
- ✅ **Deployment branches** — only `main` can deploy to production
---

## Rollback Strategy

Since this pipeline is GitOps-based, **rolling back means reverting Git** — not manually patching the cluster. ArgoCD will detect the reverted commit and reconcile the cluster back to the previous state automatically.

There are three rollback methods depending on the situation:

---

### Method 1: Git Revert (Recommended — GitOps Safe)

Revert the GitOps commit that updated the image tag. ArgoCD picks up the change and redeploys the previous image.

```bash
# Find the bad commit SHA in the overlay
git log --oneline task2/k8s/overlays/production/kustomization.yaml

# Revert it
git revert <bad-commit-sha>
git push origin main
```

ArgoCD will auto-sync (or manually sync) and restore the previous image tag.

> ✅ This is the preferred approach — it keeps Git history intact and the revert itself is auditable.

---

### Method 2: ArgoCD UI / CLI Rollback

ArgoCD stores a history of recent syncs. You can roll back directly from the ArgoCD dashboard or CLI without touching Git, useful for an immediate hotfix.

**Via ArgoCD CLI:**
```bash
# List sync history
argocd app history fastapi-production

# Roll back to a specific revision
argocd app rollback fastapi-production <revision-id>
```
---

### Method 3: Kustomize Image Tag Override

If you need to target a specific known-good image SHA without waiting for a full pipeline run:

```bash
# Point production back to the last known good image SHA
cd task2/k8s/overlays/production
kustomize edit set image devsharvari/fastapi-app=devsharvari/fastapi-app:<last-good-sha>

git add kustomization.yaml
git commit -m "rollback: revert to <last-good-sha>"
git push origin main
```

ArgoCD will detect the commit and redeploy the good image.

---

### Rollback Decision Flow

```
Issue detected in production
         │
         ▼
Is it a config/manifest issue?
    │               │
   Yes              No (bad image/code)
    │               │
    ▼               ▼
git revert     Do you need instant recovery?
the patch          │               │
commit            Yes              No
                   │               │
                   ▼               ▼
             ArgoCD UI/CLI    git revert the
             rollback to      GitOps commit
             last revision    (Method 1)
                   │
                   ▼
             Follow up with
             git revert to
             re-sync Git
```



---

### Prevention: Why Rollbacks Are Rare

The pipeline is designed to minimize the need for rollbacks:

- **Lint + tests must pass** before any image is built
- **Staging acts as a pre-production gate** — issues should surface there first
- **Manual approval** prevents rushed production deployments
- **Git SHA image tags** mean every deployment is fully reproducible and traceable

---

## Design Decisions

### 1. Git SHA as Image Tag
Using `${{ github.sha }}` as the Docker image tag ensures full traceability — every deployment can be traced back to the exact commit that produced it. This avoids the mutable `latest` tag anti-pattern.

### 2. GitOps over Push-based Deployment
Rather than `kubectl apply` directly from CI, the pipeline commits updated Kustomize overlays to Git. ArgoCD then reconciles the cluster. This means Git is always the source of truth and cluster state is auditable and reproducible.

### 3. Kustomize Base + Overlays
Avoids copy-pasting YAML across environments. The base defines shared resources; overlays patch only what differs (replicas, ports, namespaces, image tags). Adding a new environment (e.g., `dev`) requires only a new overlay directory.

### 4. Manual Approval Gate for Production
The `production` GitHub Environment requires explicit human approval before the `deploy-production` job runs. This ensures no untested or unreviewed code reaches production automatically, even if staging passes all checks.
---
