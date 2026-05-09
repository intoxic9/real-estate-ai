"""
Market data API routes for Dubai/UAE real estate snapshots.

All handlers currently return mock data structures.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import MarketSnapshot, MarketSnapshotORM


router = APIRouter(prefix="/api/market", tags=["market"])


class MarketSnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    median_sale_price_usd: float
    price_per_sqft_usd: float
    median_rent_usd: float
    days_on_market: int
    snapshot_date: date
    source: str


class AreaSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    median_sale_price_usd: float
    price_per_sqft_usd: float
    median_rent_usd: float
    days_on_market: int
    last_snapshot_date: date


class AreaComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area1: AreaSummary
    area2: AreaSummary


@router.get(
    "/snapshots",
    response_model=List[MarketSnapshot],
    status_code=status.HTTP_200_OK,
)
async def get_snapshots(
    area: Optional[str] = Query(default=None),
    from_date: Optional[date] = Query(default=None, alias="from"),
    to_date: Optional[date] = Query(default=None, alias="to"),
    db: AsyncSession = Depends(get_db),
) -> List[MarketSnapshot]:
    """
    Return market snapshots for an optional area and date range.
    """
    query = select(MarketSnapshotORM).order_by(
        MarketSnapshotORM.snapshot_date.asc(),
        MarketSnapshotORM.created_at.asc(),
    )
    if area:
        query = query.where(MarketSnapshotORM.area == area)
    if from_date:
        query = query.where(MarketSnapshotORM.snapshot_date >= from_date)
    if to_date:
        query = query.where(MarketSnapshotORM.snapshot_date <= to_date)

    rows = (await db.execute(query)).scalars().all()
    return [
        MarketSnapshot(
            id=row.id,
            area=row.area,
            median_sale_price_usd=row.median_sale_price_usd,
            price_per_sqft_usd=row.price_per_sqft_usd,
            median_rent_usd=row.median_rent_usd,
            days_on_market=row.days_on_market,
            snapshot_date=row.snapshot_date,
            source=row.source,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post(
    "/snapshots",
    response_model=MarketSnapshot,
    status_code=status.HTTP_201_CREATED,
)
async def create_snapshot(
    payload: MarketSnapshotCreate,
    db: AsyncSession = Depends(get_db),
) -> MarketSnapshot:
    """
    Store a new market snapshot (mock implementation).
    """

    _ = db
    now = datetime.now(timezone.utc)

    return MarketSnapshot(
        area=payload.area,
        median_sale_price_usd=payload.median_sale_price_usd,
        price_per_sqft_usd=payload.price_per_sqft_usd,
        median_rent_usd=payload.median_rent_usd,
        days_on_market=payload.days_on_market,
        snapshot_date=payload.snapshot_date,
        source=payload.source,
        created_at=now,
    )


@router.get(
    "/areas",
    response_model=List[AreaSummary],
    status_code=status.HTTP_200_OK,
)
async def list_areas(
    db: AsyncSession = Depends(get_db),
) -> List[AreaSummary]:
    """
    List all areas with latest metrics.
    """
    latest_dates_subq = (
        select(
            MarketSnapshotORM.area.label("area"),
            func.max(MarketSnapshotORM.snapshot_date).label("latest_snapshot_date"),
        )
        .group_by(MarketSnapshotORM.area)
        .subquery()
    )
    query = (
        select(MarketSnapshotORM)
        .join(
            latest_dates_subq,
            (MarketSnapshotORM.area == latest_dates_subq.c.area)
            & (MarketSnapshotORM.snapshot_date == latest_dates_subq.c.latest_snapshot_date),
        )
        .order_by(MarketSnapshotORM.area.asc())
    )
    rows = (await db.execute(query)).scalars().all()
    return [
        AreaSummary(
            area=row.area,
            median_sale_price_usd=row.median_sale_price_usd,
            price_per_sqft_usd=row.price_per_sqft_usd,
            median_rent_usd=row.median_rent_usd,
            days_on_market=row.days_on_market,
            last_snapshot_date=row.snapshot_date,
        )
        for row in rows
    ]


@router.get(
    "/compare",
    response_model=AreaComparison,
    status_code=status.HTTP_200_OK,
)
async def compare_areas(
    areas: str = Query(..., description="Comma-separated list of two areas."),
    db: AsyncSession = Depends(get_db),
) -> AreaComparison:
    """
    Compare two areas side by side using latest snapshots.
    """

    parts = [a.strip() for a in areas.split(",") if a.strip()]
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Exactly two areas must be provided for comparison.",
        )

    summaries = await list_areas(db=db)
    by_area = {summary.area: summary for summary in summaries}
    if parts[0] not in by_area or parts[1] not in by_area:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or both requested areas were not found in market snapshots.",
        )

    area1_summary = by_area[parts[0]]
    area2_summary = by_area[parts[1]]

    return AreaComparison(area1=area1_summary, area2=area2_summary)


__all__ = ["router"]

