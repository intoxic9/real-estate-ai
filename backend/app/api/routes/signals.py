"""
Lead signal capture and enrichment endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agents.lead_finder_agent import LeadFinderAgent
from ...core.database import get_db
from ...core.schemas import (
    FinancingType,
    LeadIntent,
    LeadTimeline,
    LeadProfileORM,
    LeadSignal,
    LeadSignalORM,
    PropertyType,
    SignalIntentLevel,
    SignalSource,
)

router = APIRouter(prefix="/api/signals", tags=["signals"])
lead_finder_agent = LeadFinderAgent()


class SignalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[LeadSignal]
    total: int


class SignalStatsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_source: Dict[str, int]
    by_intent_level: Dict[str, int]
    by_location: Dict[str, int]


class GoogleAlertIngestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str = Field(..., min_length=1)
    snippet: str = Field(..., min_length=1)
    forwarded_by: Optional[str] = None
    raw_email: Optional[str] = None


class AddSignalToPipelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    lead_id: UUID
    status: str


def _to_signal_model(row: LeadSignalORM) -> LeadSignal:
    return LeadSignal(
        id=row.id,
        source=row.source,
        source_id=row.source_id,
        username=row.username,
        content=row.content,
        locations_mentioned=list(row.locations_mentioned or []),
        apparent_intent=row.apparent_intent,
        intent_score=row.intent_score,
        intent_level=row.intent_level,
        raw_data=row.raw_data or {},
        captured_at=row.captured_at,
        converted_to_lead=row.converted_to_lead,
        lead_id=row.lead_id,
    )


@router.get("", response_model=SignalListResponse, status_code=status.HTTP_200_OK)
async def list_signals(
    source: Optional[SignalSource] = Query(default=None),
    intent_level: Optional[SignalIntentLevel] = Query(default=None),
    converted_to_lead: Optional[bool] = Query(default=None),
    location: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> SignalListResponse:
    query = select(LeadSignalORM)
    if source is not None:
        query = query.where(LeadSignalORM.source == source)
    if intent_level is not None:
        query = query.where(LeadSignalORM.intent_level == intent_level)
    if converted_to_lead is not None:
        query = query.where(LeadSignalORM.converted_to_lead == converted_to_lead)
    if location:
        query = query.where(LeadSignalORM.content.ilike(f"%{location}%"))

    query = query.order_by(LeadSignalORM.captured_at.desc()).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    return SignalListResponse(items=[_to_signal_model(row) for row in rows], total=len(rows))


@router.get("/stats", response_model=SignalStatsResponse, status_code=status.HTTP_200_OK)
async def get_signal_stats(db: AsyncSession = Depends(get_db)) -> SignalStatsResponse:
    source_rows = (
        await db.execute(
            select(LeadSignalORM.source, func.count(LeadSignalORM.id))
            .group_by(LeadSignalORM.source)
        )
    ).all()
    level_rows = (
        await db.execute(
            select(LeadSignalORM.intent_level, func.count(LeadSignalORM.id))
            .group_by(LeadSignalORM.intent_level)
        )
    ).all()
    location_counter: Dict[str, int] = {}
    signals = (await db.execute(select(LeadSignalORM.locations_mentioned))).all()
    for (locations,) in signals:
        for loc in locations or []:
            location_counter[loc] = location_counter.get(loc, 0) + 1

    return SignalStatsResponse(
        by_source={str(src.value if hasattr(src, "value") else src): int(count) for src, count in source_rows},
        by_intent_level={str(level.value if hasattr(level, "value") else level): int(count) for level, count in level_rows},
        by_location=dict(sorted(location_counter.items(), key=lambda item: item[1], reverse=True)[:25]),
    )


@router.post("/ingest/google-alerts", response_model=LeadSignal, status_code=status.HTTP_201_CREATED)
async def ingest_google_alert(
    payload: GoogleAlertIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> LeadSignal:
    row = await lead_finder_agent.ingest_google_alert(
        db,
        source_url=payload.source_url,
        snippet=payload.snippet,
        forwarded_by=payload.forwarded_by,
        raw_email=payload.raw_email,
    )
    return _to_signal_model(row)


@router.post("/ingest/reddit", status_code=status.HTTP_200_OK)
async def ingest_reddit_signals(db: AsyncSession = Depends(get_db)) -> dict:
    inserted = await lead_finder_agent.ingest_reddit(db)
    return {"inserted": inserted}


@router.post("/ingest/twitter", status_code=status.HTTP_200_OK)
async def ingest_twitter_signals(db: AsyncSession = Depends(get_db)) -> dict:
    inserted = await lead_finder_agent.ingest_twitter(db)
    return {"inserted": inserted}


@router.post(
    "/{signal_id}/add-to-pipeline",
    response_model=AddSignalToPipelineResponse,
    status_code=status.HTTP_200_OK,
)
async def add_signal_to_pipeline(
    signal_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> AddSignalToPipelineResponse:
    signal = (
        await db.execute(select(LeadSignalORM).where(LeadSignalORM.id == signal_id))
    ).scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    if signal.converted_to_lead and signal.lead_id is not None:
        return AddSignalToPipelineResponse(signal_id=signal.id, lead_id=signal.lead_id, status="already_converted")

    now = datetime.now(timezone.utc)
    intent = signal.apparent_intent
    if intent not in {LeadIntent.buyer_primary, LeadIntent.buyer_investment, LeadIntent.seller, LeadIntent.renter, LeadIntent.refinance}:
        intent = LeadIntent.unknown

    lead = LeadProfileORM(
        full_name=None,
        email=None,
        phone=None,
        intent=intent,
        budget_min=None,
        budget_max=None,
        target_market=signal.locations_mentioned[0] if signal.locations_mentioned else None,
        preferred_locations=list(signal.locations_mentioned or []),
        timeline=LeadTimeline.exploring,
        property_type=PropertyType.apartment,
        financing_type=FinancingType.unknown,
        is_first_time_buyer=None,
        consent_given=False,
        consent_timestamp=None,
        source=f"lead_signal_{signal.source.value}",
        created_at=now,
        updated_at=now,
    )
    db.add(lead)
    await db.flush()

    signal.converted_to_lead = True
    signal.lead_id = lead.id
    await db.commit()
    await db.refresh(signal)

    return AddSignalToPipelineResponse(signal_id=signal.id, lead_id=lead.id, status="converted")

