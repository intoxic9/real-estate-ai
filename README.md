# Multi-Agent Real Estate Lead Intelligence System

Full-stack platform for conversational lead intake, compliance screening, intent classification, lead scoring, routing, and market analytics.

---

## Quick start

**URLs after a successful run**

- **API health check:** [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health) → `{"status":"ok"}`
- **Frontend:** [http://localhost:3001](http://localhost:3001) — the dev script uses port **3001**

---

## Prerequisites

- **Git**
- **PostgreSQL 15+** running locally *or* a hosted database (e.g. Neon) — the API needs a valid `DATABASE_URL`
- **Python 3.10+** (3.12 recommended). *Python 3.9 may work with extra packages; see [Troubleshooting](#troubleshooting).*
- **Node.js 20+** and **npm** — for the frontend

---

## 1. Clone and enter the repo

```bash
git clone <your-fork-or-repo-url> real-estate-ai
cd real-estate-ai
```

All paths below assume this folder is your **repository root** (it contains `backend/` and `frontend/`).

---

## 2. Configure environment

1. Copy the example env file:

   ```bash
   cp backend/.env.example backend/.env
   ```

2. Edit `backend/.env`. The **minimum** to boot the API is a working **`DATABASE_URL`** (PostgreSQL with the async driver). Examples:

   **PostgreSQL on your machine** (adjust user, password, host, port, and database name to match your install):

   ```env
   DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/DATABASE_NAME
   ```

   **Managed Postgres (e.g. Neon):** paste the URL from the provider. This project normalizes `postgresql://` to `postgresql+asyncpg://` in code; for Neon hosts, query params are adjusted automatically in `backend/app/core/database.py`.

3. Create the database and user in Postgres if needed, then run migrations (see step 4).

4. Optional but useful for the UI talking to the API:

   ```env
   FRONTEND_ORIGIN=http://localhost:3001
   CORS_ORIGINS=http://localhost:3000,http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001
   ```

5. **LLM and integrations:** set `GROQ_API_KEY` (and any Google Sheets / market keys) when you need those features. Chat and some routes need a valid LLM key. See [Environment variables (reference)](#environment-variables-reference) below.

---

## 3. Backend (FastAPI)

Open a terminal:

**Windows (PowerShell or cmd):**

```bat
cd backend
python -m venv venv
.\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**macOS / Linux:**

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Check: [http://127.0.0.1:8000/api/health](http://127.0.0.1:8000/api/health)

---

## 4. Frontend (Next.js)

Open a **second** terminal:

```bash
cd frontend
npm install
npm run dev
```

Open: [http://localhost:3001](http://localhost:3001)

The app defaults API calls to `http://127.0.0.1:8000`. To override, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

---

## Troubleshooting

| Problem | What to try |
|--------|-------------|
| **`Address already in use` on port 8000** | Stop another API process, or run on port `8001` and set `NEXT_PUBLIC_API_BASE_URL` to match. |
| **API exits on startup / DB errors** | Confirm PostgreSQL is running and `DATABASE_URL` matches your database (host, port, user, password, database name). |
| **`alembic` errors (e.g. missing `psycopg2`)** | `pip install psycopg2-binary` in the same venv, then `alembic upgrade head` again. |
| **Python 3.9 + type hint errors (`\|` unions)** | Prefer upgrading to **Python 3.10+**, or `pip install eval_type_backport`. |
| **`npm: command not found`** | Install [Node.js LTS](https://nodejs.org/) (includes npm). |
| **`Permission denied` on `node_modules/.bin/next`** | Run `node node_modules/next/dist/bin/next dev -p 3001` from `frontend`, or reinstall: `rm -rf node_modules && npm install`. |
| **Frontend loads but API calls fail** | Ensure the backend is running and `NEXT_PUBLIC_API_BASE_URL` matches the API URL (default `http://127.0.0.1:8000`). |

---

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                  │
│  /chat    /dashboard    /analytics    /settings    /login  │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP (REST)
┌──────────────────────────────▼──────────────────────────────┐
│                    Backend API (FastAPI)                   │
│  /api/chat   /api/leads   /api/analytics   /api/market     │
├─────────────────────────────────────────────────────────────┤
│ Agent Orchestrator + agents (conversation, compliance, …)   │
├─────────────────────────────────────────────────────────────┤
│ Services (Sheets, market data, scrapers, notifications)     │
└──────────────────────────────┬──────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │ PostgreSQL + Alembic         │
                └─────────────────────────────┘
```

## Repository structure

- `backend/` — FastAPI app, agents, services, Alembic migrations, tests
- `frontend/` — Next.js 14 app
- `PropScraperPro/` — separate scraper tooling (see that folder’s README if present)

---

## Environment variables (reference)

Copy `backend/.env.example` to `backend/.env` and fill in values.

**Core:** `DATABASE_URL`, `APP_ENV`, `APP_DEBUG`, `FRONTEND_ORIGIN`, `CORS_ORIGINS`

**LLM:** `GROQ_API_KEY`, `CONVERSATION_MODEL`, `COMPLIANCE_MODEL`, `INTENT_MODEL`, `SCORING_MODEL` (optional: `OPENAI_API_KEY`)

**Google Sheets:** `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_SHEETS_SPREADSHEET_ID`, `GOOGLE_SHEETS_SHEET_NAME`, etc.

**Market data:** `FRED_API_KEY`, `CENSUS_API_KEY`, `CENSUS_ACS_YEAR`

**Scoring weights:** `SCORING_WEIGHT_*` (see `.env.example`)

---

## Alembic migrations

```bash
cd backend
# activate venv first
alembic upgrade head
alembic revision -m "description"
```

Initial migration: `backend/alembic/versions/0001_initial_models.py`

---

## Seed market data

```bash
cd backend
# activate venv
python scripts/seed_market_data.py
```

---

## Tests

```bash
cd backend
pytest -q
```

> Full pipeline tests may require `GROQ_API_KEY` and other live dependencies. See `backend/tests/test_full_pipeline.py`.

---

## API endpoints (high level)

- **Health:** `GET /api/health`
- **Chat:** `POST /api/chat/message`, `GET /api/chat/history/{session_id}`
- **Leads:** `GET /api/leads`, `GET /api/leads/{lead_id}`, `PUT`, `DELETE`, `POST /api/leads/{lead_id}/route`
- **Analytics:** `GET /api/analytics/overview`, `GET /api/analytics/trends`
- **Market:** `GET /api/market/snapshots`, `POST /api/market/snapshots`, `GET /api/market/areas`, `GET /api/market/compare`

---

## Screenshots

_Placeholders — replace with real captures:_ chat UI, lead dashboard, market analytics, settings.
