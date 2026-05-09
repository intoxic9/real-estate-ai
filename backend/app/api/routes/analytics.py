"""
Analytics API routes for lead performance and trends.

Currently returns mock analytics data structures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import LeadProfileORM, ScoreBucket, ScoreResultORM


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class AnalyticsOverview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    conversion_rate: float = Field(ge=0.0, le=1.0)
    average_score: float = Field(ge=0.0, le=100.0)


class TrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    lead_volume: int


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
    status_code=status.HTTP_200_OK,
)
async def get_overview(
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    """
    Return real overview analytics (counts and averages) from database.
    """
    total_leads_query = select(func.count(LeadProfileORM.id))
    total_leads = int((await db.execute(total_leads_query)).scalar_one() or 0)

    # Latest score per lead
    latest_score_ts = (
        select(
            ScoreResultORM.lead_id.label("lead_id"),
            func.max(ScoreResultORM.timestamp).label("latest_ts"),
        )
        .group_by(ScoreResultORM.lead_id)
        .subquery()
    )
    latest_scores = (
        select(
            ScoreResultORM.lead_id,
            ScoreResultORM.bucket,
            ScoreResultORM.heat_score,
        )
        .join(
            latest_score_ts,
            (ScoreResultORM.lead_id == latest_score_ts.c.lead_id)
            & (ScoreResultORM.timestamp == latest_score_ts.c.latest_ts),
        )
        .subquery()
    )

    bucket_counts_query = select(
        latest_scores.c.bucket,
        func.count().label("count"),
    ).group_by(latest_scores.c.bucket)
    bucket_rows = (await db.execute(bucket_counts_query)).all()
    bucket_map = {
        str(bucket): int(count)
        for bucket, count in bucket_rows
    }

    hot_leads = bucket_map.get(ScoreBucket.hot.value, 0)
    warm_leads = bucket_map.get(ScoreBucket.warm.value, 0)
    cold_leads = bucket_map.get(ScoreBucket.cold.value, 0)

    avg_score_query = select(func.avg(latest_scores.c.heat_score))
    avg_score_raw = (await db.execute(avg_score_query)).scalar_one_or_none()
    average_score = float(avg_score_raw) if avg_score_raw is not None else 0.0

    # Routed status is not persisted yet; use hot share as operational proxy.
    conversion_rate = (hot_leads / total_leads) if total_leads > 0 else 0.0

    return AnalyticsOverview(
        total_leads=total_leads,
        hot_leads=hot_leads,
        warm_leads=warm_leads,
        cold_leads=cold_leads,
        conversion_rate=conversion_rate,
        average_score=round(average_score, 2),
    )


@router.get(
    "/trends",
    response_model=List[TrendPoint],
    status_code=status.HTTP_200_OK,
)
async def get_trends(
    db: AsyncSession = Depends(get_db),
) -> List[TrendPoint]:
    """
    Return mock time-series lead volume data.
    """

    _ = db
    now = datetime.now(timezone.utc)

    return [
        TrendPoint(timestamp=now, lead_volume=10),
        TrendPoint(timestamp=now, lead_volume=15),
        TrendPoint(timestamp=now, lead_volume=20),
    ]


__all__ = ["router"]

