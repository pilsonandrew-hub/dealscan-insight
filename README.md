# DealerScope

**Unified vehicle arbitrage platform** — scrapes government/surplus auctions, scores deals against dealer MMR comps, and surfaces high-margin opportunities through a real-time React dashboard.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        docker-compose                        │
│                                                             │
│  ┌──────────────┐   REST/WS    ┌──────────────────────────┐ │
│  │   frontend   │◄────────────►│        backend           │ │
│  │  React+Vite  │              │  FastAPI  (port 8000)    │ │
│  │  port 5173   │              │                          │ │
│  └──────────────┘              │  /api/auth               │ │
│                                │  /api/vehicles           │ │
│  ┌──────────────┐              │  /api/opportunities      │ │
│  │    worker    │              │  /api/ml                 │ │
│  │  Celery      │◄────────────►│  /api/pipeline/run  ◄──┐ │ │
│  │  (scraping)  │   task queue │  /api/pipeline/status   │ │ │
│  └──────┬───────┘              └──────────────────────────┘ │ │
│         │                                     │             │ │
│         ▼                                     ▼             │ │
│  ┌──────────────────────────────────────────────────────┐   │ │
│  │                   backend/ingest/                    │   │ │
│  │                                                      │   │ │
│  │  scrapers/govdeals.py  ──► scrape_all.py             │   │ │
│  │  scrapers/publicsurplus.py   │                       │   │ │
│  │  scrapers/govdeals_live.py   ▼                       │   │ │
│  │                         normalize.py                 │   │ │
│  │                         transport.py                 │   │ │
│  │                         score.py                     │   │ │
│  └──────────────────────────────────────────────────────┘   │ │
│         │                                                    │ │
│  ┌──────▼───────┐    ┌──────────────┐                       │ │
│  │  PostgreSQL  │    │    Redis     │                       │ │
│  │  (listings,  │    │  (Celery     │                       │ │
│  │   sales,     │    │   broker +   │                       │ │
│  │   audit log) │    │   cache)     │                       │ │
│  └──────────────┘    └──────────────┘                       │ │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/pilsonandrew-hub/dealerscope.git
cd dealerscope

# 2. Copy env file and set secrets
cp .env.example .env
# edit SECRET_KEY in .env

# 3. Start everything
docker-compose up

# Frontend → http://localhost:5173
# API docs → http://localhost:8000/docs  (DEBUG=true only)
# API      → http://localhost:8000
```

## Python Backend Tests

This repo targets Python 3.11 for backend work. The backend test dependencies are
kept in `requirements-dev.txt` as a narrow test/dev set for analytics and router
coverage, so local backend test setup does not need the full production runtime
stack.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
bash scripts/run_backend_tests.sh
```

`bash scripts/run_backend_tests.sh` uses `pytest` and defaults to the
analytics trust-model backend test path (`tests/test_analytics_trust_model.py`).
Pass one or more test files/modules explicitly once the test dependency set is
installed. If `pytest` is missing, the script fails clearly instead of
switching frameworks under the hood.

### Run the pipeline manually

```bash
# Trigger a scrape+score run via the API
curl -X POST http://localhost:8000/api/pipeline/run

# Check status
curl http://localhost:8000/api/pipeline/status
```

---

## Services

| Service    | Port  | Description                                      |
|------------|-------|--------------------------------------------------|
| `frontend` | 5173  | React + Vite dev server                          |
| `backend`  | 8000  | FastAPI unified entrypoint (webapp + pipeline)   |
| `worker`   | —     | Celery worker for background scraping/scoring    |
| `db`       | 5432  | PostgreSQL 15 — listings, sales, audit logs      |
| `redis`    | 6379  | Celery broker, result backend, rate-limit cache  |

---

## Environment Variables

| Variable                | Default                                    | Description                          |
|-------------------------|--------------------------------------------|--------------------------------------|
| `SECRET_KEY`            | *(required in prod)*                       | JWT signing key                      |
| `DATABASE_URL`          | `postgresql://dealerscope:...@db:5432/...` | Postgres connection string           |
| `REDIS_URL`             | `redis://redis:6379/0`                     | Redis connection (webapp)            |
| `CELERY_BROKER_URL`     | `redis://redis:6379/1`                     | Celery broker                        |
| `CELERY_RESULT_BACKEND` | `redis://redis:6379/2`                     | Celery result backend                |
| `OFFLINE_MODE`          | `1`                                        | `1` = use demo fixtures; `0` = live  |
| `USE_LIVE_GOVDEALS`     | `0`                                        | `1` = scrape GovDeals live           |
| `DATA_DIR`              | `/app/data`                                | Where pipeline writes CSV/DB files   |
| `CORS_ORIGINS`          | `http://localhost:5173`                    | Allowed frontend origins             |
| `DEBUG`                 | `false`                                    | Enables `/docs` and verbose logs     |

---

## Pipeline — End to End

```
POST /api/pipeline/run
        │
        ▼
  scrape_all.py          ← async-gathers all scrapers concurrently
        │
        ├─ GovDealsScraper / GovDealsLive
        └─ PublicSurplusScraper
        │
        ▼
  Rust/state filter      ← backend/config/states.yml whitelist
        │
        ▼
  normalize.py           ← canonical make/model aliases
        │
        ▼
  transport.py           ← mileage-band cost from state → CA
        │
        ▼
  score.py               ← margin = MMR_CA - bid - premium - doc_fee - transport
                            score  = margin / max(1000, bid)
        │
        ▼
  opportunities.csv      ← ranked deals written to DATA_DIR
        │
        ▼
  /api/opportunities     ← served to React dashboard
```

### Auction sources & fees

| Source        | Buyer's Premium | Doc Fee |
|---------------|-----------------|---------|
| GovDeals      | 12.5%           | $75     |
| PublicSurplus | 10.0%           | $50     |

Configured in `backend/config/fees.yml` and `backend/config/sources.yml`.

---

## Project Layout

```
dealerscope/
├── backend/                  # Scraper/pipeline engine (NEW)
│   ├── __init__.py
│   ├── main.py               # Unified FastAPI entrypoint
│   ├── config/
│   │   ├── sources.yml       # Auction source URLs + cadence
│   │   ├── states.yml        # Rust-safe state whitelist
│   │   ├── fees.yml          # Buyer premiums + doc fees per site
│   │   ├── transit_rates.yml # Mileage-band transport rates
│   │   └── state_miles_to_ca.yml
│   └── ingest/
│       ├── normalize.py      # Make/model alias resolution
│       ├── transport.py      # Transport cost calculation
│       ├── score.py          # Deal margin + score
│       ├── scrape_all.py     # Scraper orchestrator
│       └── scrapers/
│           ├── structures.py     # PublicListing dataclass
│           ├── govdeals.py       # GovDeals scraper (offline + live)
│           ├── govdeals_live.py  # Live HTML scraper (lxml)
│           ├── publicsurplus.py  # PublicSurplus scraper
│           └── registry.py       # Scraper factory
├── webapp/                   # Original FastAPI app (routers, ML, auth)
│   ├── main.py
│   ├── routers/
│   ├── ml/
│   ├── middleware/
│   └── ...
├── src/                      # React + TypeScript frontend
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## Tech Stack

| Layer      | Technology                                      |
|------------|-------------------------------------------------|
| Frontend   | React 18, TypeScript, Vite, Tailwind, shadcn/ui |
| Backend    | FastAPI, Uvicorn, SQLAlchemy 2                  |
| Pipeline   | asyncio, aiohttp/requests, lxml, PyYAML         |
| Queue      | Celery 5 + Redis 7                              |
| Database   | PostgreSQL 15                                   |
| ML         | scikit-learn, SHAP, joblib                      |
| Auth       | JWT, bcrypt, TOTP (2FA)                         |
| Containers | Docker + docker-compose                         |
