from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import HotLeadNotification, HotLeadNotificationORM

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class HotLeadNotificationsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[HotLeadNotification]
    unread_count: int


@router.get("/hot-leads", response_model=HotLeadNotificationsResponse, status_code=status.HTTP_200_OK)
async def list_hot_lead_notifications(
    limit: int = Query(default=20, ge=1, le=100),
    unread_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> HotLeadNotificationsResponse:
    query = select(HotLeadNotificationORM).order_by(HotLeadNotificationORM.created_at.desc()).limit(limit)
    if unread_only:
        query = query.where(HotLeadNotificationORM.unread.is_(True))
    rows = (await db.execute(query)).scalars().all()
    unread_count = (
        await db.execute(
            select(HotLeadNotificationORM).where(HotLeadNotificationORM.unread.is_(True))
        )
    ).scalars().all()

    return HotLeadNotificationsResponse(
        items=[
            HotLeadNotification(
                id=r.id,
                lead_id=r.lead_id,
                lead_name=r.lead_name,
                intent=r.intent,
                score=r.score,
                budget_summary=r.budget_summary,
                market=r.market,
                timeline=r.timeline,
                destination=r.destination,
                lead_url=r.lead_url,
                unread=r.unread,
                created_at=r.created_at,
            )
            for r in rows
        ],
        unread_count=len(unread_count),
    )


@router.post(
    "/hot-leads/{notification_id}/read",
    status_code=status.HTTP_200_OK,
)
async def mark_hot_lead_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    try:
        nid = UUID(notification_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid notification id") from exc

    row = (
        await db.execute(select(HotLeadNotificationORM).where(HotLeadNotificationORM.id == nid))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    row.unread = False
    await db.commit()
    return {"status": "ok"}

