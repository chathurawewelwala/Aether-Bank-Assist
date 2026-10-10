# Aether Bank – Docker & Kubernetes deployment

## Architecture (enterprise)

```
Browser → web (nginx/React dashboard)
              │ /api proxy (optional)
              ▼
         aether-api (FastAPI × N replicas)
              ├── PostgreSQL (users, conversations, audit)
              ├── Redis (sessions / HITL pending / cache)
              └── Keycloak (OIDC)  [AUTH_MODE=keycloak]
```

Dashboard menu: **Overview · Aether Assistant · Knowledge · Settings**

---

## Local: Docker Compose

Prerequisites: Docker Desktop (Windows/Mac) or Docker Engine + Compose.

```bash
# from repo root
export OPENAI_API_KEY=sk-...   # optional

docker compose up --build -d
```

| Service   | URL |
|-----------|-----|
| Dashboard | http://localhost:4200 |
| API       | http://localhost:8000/docs |
| Keycloak  | http://localhost:8080 (admin/admin) |
| Postgres  | localhost:5432 / aether / aether |
| Redis     | localhost:6379 |

**Local auth (default `AUTH_MODE=local`):**  
`analyst@aether.bank` / `password123`

### Enable Keycloak auth

1. In `docker-compose.yml` set API env `AUTH_MODE: keycloak`
2. Restart API: `docker compose up -d api`
3. Login via Keycloak users: `analyst` / `password123` (direct grant)  
   Or configure the dashboard OIDC redirect (realm `aether`, client `aether-web`).

---

## Kubernetes

### 1. Build images (load into your cluster)

```bash
docker build -t aether-api:latest -f backend/Dockerfile .
docker build -t aether-web:latest \
  --build-arg VITE_API_BASE=http://localhost:8000/api/v1 \
  -f frontend/Dockerfile frontend/

# kind
kind load docker-image aether-api:latest
kind load docker-image aether-web:latest

# minikube
minikube image load aether-api:latest
minikube image load aether-web:latest
```

### 2. Apply manifests

```bash
kubectl apply -k deploy/k8s/
kubectl -n aether get pods,svc
```

### 3. Access the UI

```bash
kubectl -n aether port-forward svc/aether-web 4200:80
# open http://localhost:4200
```

For production, point an Ingress at `aether-web` and set `KEYCLOAK_PUBLIC_URL` / `VITE_API_BASE` to public HTTPS URLs. Store secrets via Sealed Secrets / External Secrets—not plain YAML.

---

## Environment variables (API)

| Variable | Description |
|----------|-------------|
| `AUTH_MODE` | `local` or `keycloak` |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://redis:6379/0` |
| `KEYCLOAK_URL` | Internal Keycloak base URL |
| `KEYCLOAK_PUBLIC_URL` | Browser-facing Keycloak URL |
| `KEYCLOAK_REALM` | `aether` |
| `OPENAI_API_KEY` | Optional LLM key |
| `MOCK_DOCS_PATH` | Path to markdown corpus |

Postgres and Redis failures are logged; the API falls back to in-memory memory/HITL so the stack still boots for demos.
