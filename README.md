# 810 Realty — Multi-Agent Real Estate Lead Intelligence Platform

An AI-powered platform that captures, qualifies, scores, and routes real estate leads automatically using five specialized AI agents. Built for the US residential real estate market.

**Team:** Vedant Khatri · Rashi Agrawal · Abhishek Mishra
**Course:** 810 — Special Topics in BIA · Spring 2026

---

## What This Project Does

810 Realty replaces manual lead qualification with an automated five-agent AI pipeline. When a prospect visits the website and starts a conversation, the system:

1. **Conversation Agent** — engages the user in natural dialogue, extracts intent (buy/sell/rent/invest), budget, location, timeline, financing type, and pre-approval status using Llama 3.3 70B
2. **Compliance Agent** — verifies explicit consent, redacts PII (SSN, bank accounts), blocks Fair Housing Act violations and hallucinated guarantees using Llama 3.1 8B
3. **Intent Agent** — classifies the lead as buyer_primary, buyer_investment, seller, renter, refinance, or unknown with calibrated confidence using Llama 3.3 70B with 3-pass majority voting
4. **Scoring Agent** — computes a deterministic heat score (0–100) using seven weighted factors: timeline (25%), budget clarity (20%), location specificity (15%), pre-qualification (15%), intent confidence (10%), engagement quality (10%), consent + contact (5%). The score is computed by Python math, not the LLM — same inputs always produce the same score
5. **Routing Agent** — stores the lead with full audit trail in PostgreSQL, checks for duplicates, and auto-routes hot leads (score ≥ 60) to Google Sheets CRM. No LLM needed — pure logic

Beyond reactive lead capture, the platform also:
- **Proactively discovers leads** by monitoring Reddit RSS feeds, Twitter, and Google Alerts for real estate intent signals using DuckDuckGo search and LLM-powered intent classification
- **Scrapes property listings** by city (rent/sale) via DuckDuckGo search
- **Provides market intelligence** across 16 US metros using FRED API (mortgage rates) and Redfin public data
- **Offers consumer tools** — home valuation, neighborhood reports, mortgage calculator, deal finder, and foreclosure tracker — each serving as a lead capture mechanism

---

## Project Structure

```
810-realty/
├── backend/                          # Python FastAPI service
│   ├── app/
│   │   ├── agents/                   # The 5 specialized AI agents
│   │   │   ├── conversation_agent.py # Llama 3.3 70B — adaptive lead intake
│   │   │   ├── compliance_agent.py   # Llama 3.1 8B — consent, PII, Fair Housing
│   │   │   ├── intent_agent.py       # Llama 3.3 70B — lead classification
│   │   │   ├── scoring_agent.py      # Llama 3.1 8B — deterministic scoring + rationale
│   │   │   ├── routing_agent.py      # No LLM — pure routing logic
│   │   │   └── lead_finder_agent.py  # Llama 3.1 8B — social media intent classification
│   │   ├── api/routes/               # REST API endpoints
│   │   │   ├── chat.py               # POST /api/chat/message
│   │   │   ├── leads.py              # CRUD + manual routing + CSV import
│   │   │   ├── analytics.py          # Lead analytics and trends
│   │   │   ├── market.py             # Market snapshots and comparisons
│   │   │   ├── signals.py            # Lead signal feed from social monitoring
│   │   │   ├── scraper.py            # Property listing scraper jobs
│   │   │   ├── deals.py              # Deal finder
│   │   │   ├── foreclosures.py       # Foreclosure/auction properties
│   │   │   ├── mortgage.py           # Mortgage affordability calculator
│   │   │   ├── neighborhood.py       # Neighborhood intelligence reports
│   │   │   ├── valuation.py          # AI home valuation
│   │   │   └── notifications.py      # Hot lead notifications
│   │   ├── core/
│   │   │   ├── config.py             # Environment variable loading
│   │   │   ├── database.py           # Async SQLAlchemy + Neon PostgreSQL
│   │   │   └── schemas.py            # Pydantic models + SQLAlchemy ORM models
│   │   ├── services/
│   │   │   ├── agent_orchestrator.py  # Coordinates the 5-agent pipeline
│   │   │   ├── sheets_service.py      # Google Sheets CRM integration
│   │   │   ├── market_data_service.py # FRED + Redfin data fetching
│   │   │   ├── listing_scraper_service.py # DuckDuckGo property search
│   │   │   ├── deal_finder_service.py # Deal discovery
│   │   │   ├── foreclosure_service.py # Foreclosure data
│   │   │   ├── clay_service.py        # Clay/Apollo enrichment integration
│   │   │   └── notification_service.py # Slack/email notifications
│   │   └── main.py                    # FastAPI app with CORS, middleware, routers
│   ├── alembic/                       # Database migrations
│   ├── scripts/
│   │   ├── seed_market_data.py        # Seed 16 US metros with 12-24 months of data
│   │   └── cleanup_dubai_market_data.py
│   ├── tests/
│   │   └── test_full_pipeline.py      # End-to-end pipeline test
│   ├── requirements.txt
│   └── .env.example
├── frontend/                          # Next.js 14 + TypeScript + Tailwind
│   ├── src/app/
│   │   ├── chat/                      # AI chatbot with interactive widgets
│   │   │   ├── page.tsx               # Chat UI with quick-select buttons, budget slider
│   │   │   └── widgets.tsx            # Interactive widget components
│   │   ├── dashboard/page.tsx         # Lead management dashboard
│   │   ├── analytics/page.tsx         # Market analytics with 16 US metros
│   │   ├── signals/page.tsx           # Lead signal feed from social monitoring
│   │   ├── scraper/page.tsx           # Property scraper job launcher  
│   │   ├── deals/page.tsx             # Deal finder
│   │   ├── foreclosures/page.tsx      # Foreclosure tracker
│   │   ├── valuation/page.tsx         # Home valuation tool
│   │   ├── neighborhood/page.tsx      # Neighborhood reports
│   │   ├── mortgage/page.tsx          # Mortgage calculator
│   │   ├── login/page.tsx             # Authentication
│   │   ├── settings/page.tsx          # Configuration
│   │   └── layout.tsx                 # Sidebar navigation + auth wrapper
│   ├── src/components/ui/             # shadcn/ui components
│   └── src/lib/                       # API client, auth, utilities
├── PropScraperPro/                    # Standalone scraper module
├── docker-compose.yml
└── README.md
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Python 3.11+ / FastAPI | Async-native, auto-generated API docs, Pydantic validation |
| Frontend | Next.js 14 / TypeScript / Tailwind | SSR for SEO, type safety, rapid UI development |
| LLM Inference | Groq (Llama 3.3 70B + Llama 3.1 8B) | Sub-second inference via custom LPU chips, free tier |
| Agent Framework | LangChain | Model-agnostic orchestration, structured output parsing |
| Database | PostgreSQL on Neon | ACID transactions for compliance, serverless, free tier |
| CRM | Google Sheets API | Zero-cost, universally accessible, auto-routing for hot leads |
| Market Data | FRED API + Redfin public data | Real mortgage rates, 16 US metro price/rent/inventory data |
| Lead Discovery | DuckDuckGo Search (ddgs) + Reddit RSS | Free, no API key required, monitors public intent signals |

### Model Assignment

| Agent | Model | Temp | Why |
|-------|-------|------|-----|
| Conversation | Llama 3.3 70B | 0.7 | User-facing, needs natural language quality |
| Compliance | Llama 3.1 8B | 0.2 | Mostly rule-based, LLM only for claim detection |
| Intent | Llama 3.3 70B | 0.3 | Classification accuracy critical, uses 3-pass calibration |
| Scoring | Llama 3.1 8B | 0.3 | Score is deterministic math, LLM only writes rationale |
| Lead Finder | Llama 3.1 8B | 0.2 | Simple intent classification of social posts |
| Routing | None | — | Pure logic, no LLM needed |

Three separate Groq API keys distribute token usage: Key 1 (chat), Key 2 (pipeline agents), Key 3 (search/analysis).

---

## Prerequisites

- **Python 3.11+** (3.12 recommended)
- **Node.js 20+** and **npm**
- **Git**
- **PostgreSQL** — local install or hosted (Neon recommended, free tier)
- **Groq API key** — free from [console.groq.com](https://console.groq.com)
- **Google Cloud service account** — for Sheets CRM routing (optional for initial setup)

---

## Setup and Run

### 1. Clone the repository

```bash
git clone https://github.com/intoxic9/real-estate-ai.git
cd real-estate-ai
```

### 2. Configure environment variables

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` with your values:

```env
# Database (required)
DATABASE_URL=postgresql+asyncpg://user:password@host:5432/dbname?ssl=require

# LLM (required for chat)
GROQ_API_KEY_CHAT=gsk_your_key_1
GROQ_API_KEY_AGENTS=gsk_your_key_2
GROQ_API_KEY_SEARCH=gsk_your_key_3

# Google Sheets (required for CRM routing)
GOOGLE_SERVICE_ACCOUNT_FILE=./credentials.json
GOOGLE_SHEET_ID=your_sheet_id

# Market data (optional)
FRED_API_KEY=your_fred_key
CENSUS_API_KEY=your_census_key

# Frontend
FRONTEND_ORIGIN=http://localhost:3001
```

### 3. Start the backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload
```

Verify: http://127.0.0.1:8000/api/health → `{"status":"ok"}`

API docs: http://127.0.0.1:8000/docs

### 4. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open: http://localhost:3001

### 5. Seed market data (optional but recommended)

```bash
cd backend
python scripts/seed_market_data.py
```

Populates 16 US metros with 12-24 months of price, rent, inventory, and days-on-market data.

---

## How It Works

### The Five-Agent Pipeline

```
User sends message
        │
        ▼
┌─────────────────┐
│ Conversation     │ ← Llama 3.3 70B (temp 0.7)
│ Agent            │   Extracts: intent, budget, location, timeline,
│                  │   financing, pre-approval, name, contact
└────────┬────────┘
         │ (after consent given)
         ▼
┌─────────────────┐
│ Compliance       │ ← Llama 3.1 8B (temp 0.2)
│ Agent            │   Checks: consent ✓, PII redacted ✓,
│                  │   Fair Housing ✓, no hallucinated claims ✓
└────────┬────────┘
         │ (if compliant)
         ▼
┌─────────────────┐
│ Intent           │ ← Llama 3.3 70B (temp 0.3)
│ Agent            │   Classifies: buyer_primary | buyer_investment |
│                  │   seller | renter | refinance | unknown
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Scoring          │ ← Deterministic Python formula + Llama 3.1 8B for rationale
│ Agent            │   Score: 0-100 → Hot (≥60) | Warm (35-59) | Cold (<35)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Routing          │ ← No LLM, pure logic
│ Agent            │   Hot + compliant → Google Sheets CRM
│                  │   All leads → PostgreSQL with audit trail
└─────────────────┘
```

### Scoring Formula (deterministic)

```
score = (timeline_pts × 0.25) +
        (budget_pts × 0.20) +
        (location_pts × 0.15) +
        (prequalification_pts × 0.15) +
        (intent_confidence_pts × 0.10) +
        (engagement_pts × 0.10) +
        (consent_contact_pts × 0.05)
```

Same inputs always produce the same score. The LLM is only used to generate human-readable reasoning.

### Proactive Lead Discovery

```
Reddit RSS Feeds ──┐
DuckDuckGo Search ──┤──→ Intent Classifier (8B) ──→ Lead Signals Dashboard
Google Alerts ──────┘                                      │
                                                    "Add to Pipeline"
                                                           │
                                              Scoring → Routing → CRM
```

---

## Database Schema

12 tables in PostgreSQL:

| Table | Purpose |
|-------|---------|
| lead_profiles | Core lead data (name, email, intent, budget, location, consent) |
| chat_messages | Raw conversation messages per session |
| conversation_transcripts | Sanitized transcripts linked to leads |
| compliance_results | Consent verification, PII redaction, claim blocking results |
| intent_results | Classification, confidence score, rationale |
| score_results | Heat score, bucket, scoring signals |
| market_snapshots | Time-series market data for 16 US metros |
| lead_signals | Social media intent signals from Reddit/Twitter/Alerts |
| hot_lead_notifications | Notification log for routed leads |
| foreclosure_properties | Bank auction and REO property listings |
| properties | Scraped property listings |
| alembic_version | Migration tracking |

---

## API Endpoints (25+)

| Group | Endpoints |
|-------|----------|
| Health | `GET /api/health` |
| Chat | `POST /api/chat/message`, `GET /api/chat/history/{session_id}` |
| Leads | `GET /api/leads`, `GET /api/leads/{id}`, `PUT`, `DELETE`, `POST /api/leads/{id}/route`, `POST /api/leads/import/csv` |
| Analytics | `GET /api/analytics/overview`, `GET /api/analytics/trends` |
| Market | `GET /api/market/snapshots`, `POST /api/market/snapshots`, `GET /api/market/areas`, `GET /api/market/compare` |
| Signals | `GET /api/signals`, `GET /api/signals/stats` |
| Scraper | `POST /api/scraper/jobs`, `GET /api/scraper/jobs`, `GET /api/scraper/listings` |
| Deals | `GET /api/deals/search` |
| Foreclosures | `GET /api/foreclosures`, `POST /api/foreclosures/refresh` |
| Valuation | `POST /api/valuation/estimate` |
| Neighborhood | `GET /api/neighborhood/report` |
| Mortgage | `POST /api/mortgage/calculate` |

Full interactive docs at `/docs` when the backend is running.

---

## Frontend Pages (11)

**Public (lead magnets — no login required):**
- `/chat` — AI chatbot with interactive widgets (quick-select buttons, budget slider)
- `/deals` — Property deal finder
- `/listings` — Scraped property listings browser
- `/foreclosures` — Bank auction and foreclosure tracker
- `/valuation` — Free AI home valuation
- `/neighborhood` — Neighborhood intelligence reports
- `/mortgage` — Mortgage affordability calculator

**Private (brokerage tools — require authentication):**
- `/dashboard` — Lead management with scores, filters, charts
- `/analytics` — Market analytics across 16 US metros
- `/signals` — Social media lead signal feed
- `/scraper` — Property listing scraper job launcher
- `/settings` — Configuration

---

## Testing

### Quick API test

```bash
curl -X POST http://127.0.0.1:8000/api/chat/message \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test1","message":"Hi, I want to buy a home in Austin"}'
```

### Full pipeline test

```bash
cd backend
pytest tests/test_full_pipeline.py -v
```

### Manual test scenario

1. Open http://localhost:3001/chat
2. Type: "I want to buy my first home in Austin, single family, 350-400K, FHA pre-approved, need to move in 2 months"
3. Provide name and email when asked
4. Give consent
5. Expected: Score 70+, bucket HOT, routed to Google Sheets

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Application startup failed` on database | Check `DATABASE_URL` in `.env`. Must use `postgresql+asyncpg://`. For Neon: use `?ssl=require` not `?sslmode=require` |
| `429 RESOURCE_EXHAUSTED` from Groq | Token limit hit. Wait 60 seconds or switch to a different API key |
| CORS errors in browser | Ensure `FRONTEND_ORIGIN` matches your frontend URL (including port) |
| `python-multipart` error | Run `pip install python-multipart` |
| Chat returns 500 | Check terminal for traceback. Usually missing API key or schema mismatch |
| Google Sheets routing fails | Verify `credentials.json` exists, service account has Editor access on the sheet, sheet tab name matches code |
| Port 3000 in use | Frontend auto-switches to 3001. Update `FRONTEND_ORIGIN` in backend `.env` |

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string with `postgresql+asyncpg://` prefix |
| `GROQ_API_KEY_CHAT` | Yes | Groq API key for Conversation Agent |
| `GROQ_API_KEY_AGENTS` | Yes | Groq API key for Intent, Compliance, Scoring agents |
| `GROQ_API_KEY_SEARCH` | Yes | Groq API key for Lead Finder and search services |
| `GROQ_API_KEY` | Fallback | Generic key used if specific keys not set |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | For routing | Path to Google service account JSON |
| `GOOGLE_SHEET_ID` | For routing | Google Sheets spreadsheet ID |
| `FRED_API_KEY` | For market data | Free from fred.stlouisfed.org |
| `CENSUS_API_KEY` | For neighborhood | Free from api.census.gov |
| `FRONTEND_ORIGIN` | Recommended | Frontend URL for CORS (default: http://localhost:3000) |

---

## License

Academic project — Spring 2026. For educational use unless otherwise specified.
