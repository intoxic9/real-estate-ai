# Multi-Agent Real Estate Lead Intelligence System

Production-focused full-stack platform for conversational lead intake, compliance screening, intent classification, lead scoring, routing, and market analytics for US real estate teams.

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
│ Agent Orchestrator                                          │
│  ├─ Conversation Agent                                      │
│  ├─ Compliance Agent                                        │
│  ├─ Intent Agent                                            │
│  ├─ Scoring Agent                                           │
│  └─ Routing Agent                                           │
├─────────────────────────────────────────────────────────────┤
│ Services                                                    │
│  ├─ SheetsService (Google Sheets)                           │
│  └─ MarketDataService (Redfin, FRED, Census)                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                ┌──────────────▼──────────────┐
                │ PostgreSQL (SQLAlchemy ORM) │
                │ + Alembic migrations         │
                └──────────────────────────────┘
```

## Repository Structure

- `backend/` FastAPI backend, agents, services, migrations, tests
- `frontend/` Next.js 14 frontend
- `docker-compose.yml` local deployment stack

## Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 15 (if running local without Docker)
- Docker + Docker Compose (for containerized setup)

## Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill secrets.

Core:

- `DATABASE_URL`
- `APP_ENV`
- `APP_DEBUG`
- `FRONTEND_ORIGIN`
- `CORS_ORIGINS`

LLM:

- `GROQ_API_KEY` (current provider)
- `OPENAI_API_KEY` (optional compatibility placeholder)
- `CONVERSATION_MODEL`
- `COMPLIANCE_MODEL`
- `INTENT_MODEL`
- `SCORING_MODEL`

Sheets:

- `GOOGLE_SERVICE_ACCOUNT_FILE`
- `GOOGLE_SHEETS_SPREADSHEET_ID`
- `GOOGLE_SHEETS_SHEET_NAME`
- `GOOGLE_SHEETS_CREDENTIALS_PATH` (legacy compatibility)
- `GOOGLE_SHEET_ID` (legacy compatibility)

Market Data:

- `FRED_API_KEY`
- `CENSUS_API_KEY`
- `CENSUS_ACS_YEAR`

Scoring:

- `SCORING_WEIGHT_TIMELINE`
- `SCORING_WEIGHT_BUDGET`
- `SCORING_WEIGHT_LOCATION`
- `SCORING_WEIGHT_PREAPPROVAL`
- `SCORING_WEIGHT_INTENT_CONFIDENCE`
- `SCORING_WEIGHT_ENGAGEMENT`
- `SCORING_WEIGHT_CONSENT_CONTACT`

## Local Development (without Docker)

### Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

- Frontend: `http://localhost:3001` (current dev script)
- Backend: `http://127.0.0.1:8000`

## Docker Run

```bash
docker compose up --build
```

Services:

- Postgres: `localhost:5432`
- Backend: `localhost:8000`
- Frontend: `localhost:3000`

Backend container startup runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Alembic Migrations

Alembic is configured under `backend/alembic`.

Common commands:

```bash
cd backend
alembic upgrade head
alembic revision -m "description"
```

Initial migration file:

- `backend/alembic/versions/0001_initial_models.py`

## Seed Market Data

Populate realistic US metro market snapshots (24 months):

```bash
cd backend
python scripts/seed_market_data.py
```

## Integration Test

End-to-end chat pipeline integration test:

- `backend/tests/test_full_pipeline.py`

Run:

```bash
cd backend
pytest -q
```

> Note: test requires `GROQ_API_KEY` and live backend dependencies.

## API Endpoints (High-Level)

Chat:

- `POST /api/chat/message`
- `GET /api/chat/history/{session_id}`

Leads:

- `GET /api/leads`
- `GET /api/leads/{lead_id}`
- `PUT /api/leads/{lead_id}`
- `DELETE /api/leads/{lead_id}`
- `POST /api/leads/{lead_id}/route`

Analytics:

- `GET /api/analytics/overview`
- `GET /api/analytics/trends`

Market:

- `GET /api/market/snapshots`
- `POST /api/market/snapshots`
- `GET /api/market/areas`
- `GET /api/market/compare`

Health:

- `GET /api/health`

## Screenshots

_Placeholders (replace with real captures):_

- Chat UI screenshot
- Lead dashboard screenshot
- Market analytics screenshot
- Settings screenshot

