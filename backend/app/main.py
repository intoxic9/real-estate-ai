"""
FastAPI application entrypoint for the Dubai/UAE real estate
multi-agent lead intelligence system.

This file wires up:
- CORS middleware for the frontend.
- API routers for chat, leads, analytics, and market data.
- Database initialization on startup.
- A basic health check endpoint.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import asyncio
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api.routes.analytics import router as analytics_router
from .api.routes.chat import router as chat_router
from .api.routes.deals import router as deals_router
from .api.routes.foreclosures import router as foreclosures_router
from .api.routes.leads import router as leads_router
from .api.routes.market import router as market_router
from .api.routes.mortgage import router as mortgage_router
from .api.routes.notifications import router as notifications_router
from .api.routes.neighborhood import router as neighborhood_router
from .api.routes.signals import router as signals_router
from .api.routes.valuation import router as valuation_router
from .core.database import Base, engine
from .core.database import AsyncSessionLocal
from .services.deal_finder_service import DealFinderService
from .services.foreclosure_service import ForeclosureService


async def _align_existing_schema() -> None:
    """
    Align existing PostgreSQL schema with current ORM/Pydantic models.

    This is a safety bridge for environments where tables already exist and
    Alembic migrations have not yet been applied.
    """
    async with engine.begin() as conn:
        # Ensure enum values exist on previously created enum types.
        await conn.execute(text("ALTER TYPE lead_intent_enum ADD VALUE IF NOT EXISTS 'buyer_primary'"))
        await conn.execute(text("ALTER TYPE lead_intent_enum ADD VALUE IF NOT EXISTS 'buyer_investment'"))
        await conn.execute(text("ALTER TYPE lead_intent_enum ADD VALUE IF NOT EXISTS 'refinance'"))
        await conn.execute(text("ALTER TYPE intent_classification_enum ADD VALUE IF NOT EXISTS 'buyer_primary'"))
        await conn.execute(text("ALTER TYPE intent_classification_enum ADD VALUE IF NOT EXISTS 'buyer_investment'"))
        await conn.execute(text("ALTER TYPE intent_classification_enum ADD VALUE IF NOT EXISTS 'refinance'"))
        await conn.execute(text("ALTER TYPE property_type_enum ADD VALUE IF NOT EXISTS 'single_family'"))
        await conn.execute(text("ALTER TYPE signal_source_enum ADD VALUE IF NOT EXISTS 'reddit_api'"))
        await conn.execute(text("ALTER TYPE signal_source_enum ADD VALUE IF NOT EXISTS 'reddit_rss'"))
        await conn.execute(text("ALTER TYPE signal_source_enum ADD VALUE IF NOT EXISTS 'twitter_google'"))

        # financing_type_enum might not exist in older deployments.
        await conn.execute(
            text(
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_type WHERE typname = 'financing_type_enum'
                    ) THEN
                        CREATE TYPE financing_type_enum AS ENUM (
                            'cash', 'conventional', 'fha', 'va', 'other', 'unknown'
                        );
                    END IF;
                END$$;
                """
            )
        )

        # Add missing lead_profiles columns required by current schema.
        await conn.execute(
            text("ALTER TABLE lead_profiles ADD COLUMN IF NOT EXISTS target_market VARCHAR")
        )
        await conn.execute(
            text(
                "ALTER TABLE lead_profiles "
                "ADD COLUMN IF NOT EXISTS financing_type financing_type_enum NOT NULL DEFAULT 'unknown'"
            )
        )
        await conn.execute(
            text("ALTER TABLE lead_profiles ADD COLUMN IF NOT EXISTS is_first_time_buyer BOOLEAN")
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
    """
    Application lifespan for startup/shutdown hooks.

    On startup, ensure that database metadata is created. In production,
    this will typically be managed by Alembic migrations instead.
    """

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _align_existing_schema()

    deal_finder_service = DealFinderService()
    foreclosure_service = ForeclosureService()
    deals_task = asyncio.create_task(deal_finder_service.run_daily_refresh_loop(AsyncSessionLocal))
    foreclosure_task = asyncio.create_task(foreclosure_service.run_daily_refresh_loop(AsyncSessionLocal))

    yield

    # Place for graceful shutdown logic if needed.
    deals_task.cancel()
    foreclosure_task.cancel()


app = FastAPI(
    title="Dubai Real Estate Lead Intelligence API",
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(chat_router)
app.include_router(leads_router)
app.include_router(analytics_router)
app.include_router(market_router)
app.include_router(mortgage_router)
app.include_router(signals_router)
app.include_router(notifications_router)
app.include_router(valuation_router)
app.include_router(neighborhood_router)
app.include_router(deals_router)
app.include_router(foreclosures_router)


@app.get("/api/health", tags=["health"])
async def health_check() -> JSONResponse:
    """
    Lightweight health check endpoint.
    """

    return JSONResponse({"status": "ok"})


__all__ = ["app"]

