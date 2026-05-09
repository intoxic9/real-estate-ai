from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import MarketSnapshotORM

router = APIRouter(prefix="/api/valuation", tags=["valuation"])


ConditionValue = Literal["excellent", "good", "fair", "needs_work"]
RenovationValue = Literal["recent_full", "partial", "none"]


class ValuationEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(min_length=3)
    bedrooms: int = Field(ge=0, le=20)
    bathrooms: float = Field(ge=0, le=20)
    sqft: float = Field(gt=100, le=50000)
    condition: ConditionValue
    renovations: RenovationValue
    area: str = Field(min_length=2)


class ValuationEstimateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str
    area: str
    estimated_low: float
    estimated_mid: float
    estimated_high: float
    area_avg_price_per_sqft: float
    adjusted_price_per_sqft: float
    market_trend: Literal["up", "down", "flat"]
    trend_percent: float
    generated_at: datetime


@router.post(
    "/estimate",
    response_model=ValuationEstimateResponse,
    status_code=status.HTTP_200_OK,
)
async def estimate_valuation(
    payload: ValuationEstimateRequest,
    db: AsyncSession = Depends(get_db),
) -> ValuationEstimateResponse:
    rows = (
        await db.execute(
            select(MarketSnapshotORM)
            .where(func.lower(MarketSnapshotORM.area) == payload.area.strip().lower())
            .order_by(desc(MarketSnapshotORM.snapshot_date), desc(MarketSnapshotORM.created_at))
            .limit(2)
        )
    ).scalars().all()

    if not rows:
        rows = (
            await db.execute(
                select(MarketSnapshotORM)
                .order_by(desc(MarketSnapshotORM.snapshot_date), desc(MarketSnapshotORM.created_at))
                .limit(2)
            )
        ).scalars().all()

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No market snapshot data available yet.",
        )

    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    area_price_per_sqft = float(latest.price_per_sqft_usd)

    condition_multiplier = {
        "excellent": 1.10,
        "good": 1.00,
        "fair": 0.90,
        "needs_work": 0.75,
    }[payload.condition]

    renovation_multiplier = {
        "recent_full": 1.08,
        "partial": 1.04,
        "none": 1.00,
    }[payload.renovations]

    bedroom_multiplier = 1.0
    if payload.bedrooms >= 4:
        bedroom_multiplier = 1.03
    elif payload.bedrooms <= 1:
        bedroom_multiplier = 0.97

    base_estimate = payload.sqft * area_price_per_sqft
    adjusted_mid = base_estimate * condition_multiplier * renovation_multiplier * bedroom_multiplier
    adjusted_low = adjusted_mid * 0.92
    adjusted_high = adjusted_mid * 1.08
    adjusted_ppsf = adjusted_mid / payload.sqft

    market_trend: Literal["up", "down", "flat"] = "flat"
    trend_percent = 0.0
    if previous and previous.median_sale_price_usd > 0:
        delta = float(latest.median_sale_price_usd - previous.median_sale_price_usd)
        trend_percent = round((delta / float(previous.median_sale_price_usd)) * 100.0, 2)
        if trend_percent > 0.25:
            market_trend = "up"
        elif trend_percent < -0.25:
            market_trend = "down"

    return ValuationEstimateResponse(
        address=payload.address,
        area=latest.area,
        estimated_low=round(adjusted_low, 2),
        estimated_mid=round(adjusted_mid, 2),
        estimated_high=round(adjusted_high, 2),
        area_avg_price_per_sqft=round(area_price_per_sqft, 2),
        adjusted_price_per_sqft=round(adjusted_ppsf, 2),
        market_trend=market_trend,
        trend_percent=trend_percent,
        generated_at=datetime.now(timezone.utc),
    )

