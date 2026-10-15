# ShopSphere: e-commerce platform (raw application code)

You are the **DevOps engineer** joining this team. The developers hand you **working application code only**:
no Dockerfiles, no Kubernetes YAML, no Helm, no pipelines, no monitoring, no cloud.
**Onboarding this platform onto DevOps is your job**, ticket by ticket (`docs/backlog.md`).

## Architecture
```
                 Browser
                    │
             ┌──────▼──────┐
             │   gateway   │  Go · :8080 · web UI + /api/* router + rate limit
             └──┬────┬───┬─┘
   /api/catalog │    │   │ /api/orders
        ┌───────▼┐ ┌─▼───────────┐ ┌▼──────────┐
        │catalog │ │ inventory   │ │  orders   │
        │Python  │ │ Node.js     │ │  Python   │
        │ :8001  │ │ :8002       │ │  :8003    │
        └─┬────┬─┘ └──┬──────────┘ └┬───┬──────┘
          │    │      │   ▲ reserve │   │ outbox → XADD
          │  Redis    │   └─────────┘   │
          │  (cache)  │                 ▼
          ▼           ▼          Redis stream "orders.events"
     Postgres     Postgres              │
     db: catalog  db: inventory   ┌─────▼─────┐   ┌── Postgres db: orders
                                  │  worker   │   │
                                  │  Python   │───┘ (via orders API)
                                  │  :9100 ops│
                                  └───────────┘
```

### Order flow (what happens when a customer clicks "Place order")
1. **gateway** forwards `POST /api/orders/orders` to **orders**
2. **orders** asks **catalog** for the price of each SKU
3. **orders** asks **inventory** to reserve stock (409 if not enough)
4. **orders** saves the order (`PENDING`) **and** an `order.created` event in one DB transaction (outbox)
5. A background thread in **orders** publishes the event to the Redis stream
6. **worker** reads the event → payment check → `CONFIRMED` → commits stock → `SHIPPED`, sending "emails" (log lines)

## Services
| Service | Language | Port | Start command | Needs |
|---|---|---|---|---|
| gateway | Go 1.23 (stdlib only) | 8080 | `go build -o gateway . && ./gateway` | catalog, inventory, orders |
| catalog | Python 3.12, FastAPI | 8001 | `uvicorn app.main:app --host 0.0.0.0 --port 8001` | Postgres, Redis (optional) |
| inventory | Node.js 22, Express | 8002 | `node src/server.js` | Postgres |
| orders | Python 3.12, FastAPI | 8003 | `uvicorn app.main:app --host 0.0.0.0 --port 8003` | Postgres, Redis, catalog, inventory |
| worker | Python 3.12 | 9100 (ops only) | `python -m worker` | Redis, orders, inventory |

Each service runs its own **database migrations at startup** (`migrations/*.sql`) and seeds demo data.

## Configuration (environment variables)
### Common to every service
| Variable | Default | Meaning |
|---|---|---|
| `APP_VERSION` | `1.0.0` | Shown in `/health` and logs |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `CHAOS_ERROR_RATE` | `0` | 0–1: fraction of requests that fail on purpose (drills) |
| `CHAOS_LATENCY_MS` | `0` | Extra delay per request (not worker) |

### gateway
| Variable | Required | Default |
|---|---|---|
| `CATALOG_URL`, `INVENTORY_URL`, `ORDERS_URL` | ✅ | - |
| `PORT` | | `8080` |
| `STATIC_DIR` | | `./public` |
| `UPSTREAM_TIMEOUT_MS` | | `5000` |
| `RATE_LIMIT_RPS` / `RATE_LIMIT_BURST` | | `20` / `40` (0 = off) |
| `SHUTDOWN_GRACE_MS` | | `10000` |

### catalog
| Variable | Required | Default |
|---|---|---|
| `DATABASE_URL` | ✅ | - e.g. `postgresql://catalog:catalog@postgres:5432/catalog` |
| `REDIS_URL` | | empty = no cache |
| `CACHE_TTL_SECONDS` | | `60` |
| `DB_POOL_SIZE`, `DB_CONNECT_TIMEOUT` | | `5`, `5` |
| `RUN_MIGRATIONS` | | `true` |

### inventory
| Variable | Required | Default |
|---|---|---|
| `DATABASE_URL` | ✅ | - |
| `LOW_STOCK_THRESHOLD` | | `5` |
| `DB_POOL_MAX`, `DB_CONNECT_TIMEOUT_MS` | | `10`, `5000` |
| `RUN_MIGRATIONS`, `SHUTDOWN_GRACE_MS` | | `true`, `10000` |

### orders
| Variable | Required | Default |
|---|---|---|
| `DATABASE_URL`, `REDIS_URL` | ✅ | - |
| `CATALOG_URL`, `INVENTORY_URL` | ✅ | - |
| `INTERNAL_API_TOKEN` | ✅ **secret** | - (must equal the worker's) |
| `EVENT_STREAM` | | `orders.events` |
| `HTTP_TIMEOUT_SECONDS`, `HTTP_RETRIES` | | `3`, `2` |
| `OUTBOX_INTERVAL_SECONDS` | | `2` |

### worker
| Variable | Required | Default |
|---|---|---|
| `REDIS_URL`, `ORDERS_URL`, `INVENTORY_URL` | ✅ | - |
| `INTERNAL_API_TOKEN` | ✅ **secret** | - |
| `CONSUMER_GROUP` / `CONSUMER_NAME` | | `fulfilment` / hostname |
| `MAX_DELIVERIES`, `RETRY_IDLE_MS` | | `5`, `15000` |
| `DEAD_LETTER_STREAM` | | `orders.dlq` |
| `SHIP_DELAY_SECONDS`, `OPS_PORT` | | `2`, `9100` |

## Operational endpoints (every service)
| Endpoint | Purpose | Use it for |
|---|---|---|
| `GET /health` | Liveness: process alive, **never** checks dependencies | Kubernetes `livenessProbe` |
| `GET /ready` | Readiness: can serve traffic (own DB / Redis) | Kubernetes `readinessProbe` |
| `GET /metrics` | Prometheus metrics | Prometheus scraping |

All logs are **JSON, one line per event, on stdout**, with `request_id` passed through every service (`X-Request-ID`).

## Tests
| Service | Command | Needs |
|---|---|---|
| catalog | `pip install -r requirements-dev.txt && python -m pytest -q` | Postgres (+ Redis optional) |
| orders | same | Postgres + Redis |
| worker | same | nothing |
| inventory | `npm ci && npm test` | Postgres |
| gateway | `go test ./...` | nothing |

## Traffic generator
```bash
pip install httpx
python tools/loadgen.py --url http://localhost:8080 --users 10 --duration 120
```

## Your work
- Backlog with acceptance criteria: **`docs/backlog.md`**
- Team rules: **`CONTRIBUTING.md`**
- Your DevOps files go in: `platform/` (compose, Kubernetes, Helm, monitoring) and `infra/` (Terraform), Dockerfiles next to each service
- Incident write-ups: `docs/rca/` · Runbooks: `docs/runbooks/`
