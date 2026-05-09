from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...core.schemas import ForeclosureProperty, ForeclosurePropertyORM
from ...services.foreclosure_service import ForeclosureService

router = APIRouter(prefix="/api/foreclosures", tags=["foreclosures"])
foreclosure_service = ForeclosureService()


class ForeclosureListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ForeclosureProperty]
    total: int


class ForeclosureRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: str
    city: Optional[str] = None
    county: Optional[str] = None


@router.get("", response_model=ForeclosureListResponse, status_code=status.HTTP_200_OK)
async def list_foreclosures(
    state: Optional[str] = Query(default=None),
    city: Optional[str] = Query(default=None),
    status_value: Optional[str] = Query(default=None, alias="status"),
    property_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ForeclosureListResponse:
    query = select(ForeclosurePropertyORM).where(ForeclosurePropertyORM.is_active.is_(True))
    if state:
        query = query.where(ForeclosurePropertyORM.state.ilike(state))
    if city:
        query = query.where(ForeclosurePropertyORM.city.ilike(city))
    if status_value:
        query = query.where(ForeclosurePropertyORM.status == status_value)
    if property_type:
        query = query.where(ForeclosurePropertyORM.property_type == property_type)
    query = query.order_by(desc(ForeclosurePropertyORM.captured_at)).limit(200)
    rows = (await db.execute(query)).scalars().all()
    return ForeclosureListResponse(
        items=[
            ForeclosureProperty(
                id=r.id,
                address=r.address,
                city=r.city,
                state=r.state,
                zip=r.zip,
                property_type=r.property_type,
                status=r.status,
                estimated_value_usd=r.estimated_value_usd,
                auction_date=r.auction_date,
                auction_location=r.auction_location,
                minimum_bid=r.minimum_bid,
                source=r.source,
                source_url=r.source_url,
                description=r.description,
                captured_at=r.captured_at,
                is_active=r.is_active,
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.get("/{property_id}", response_model=ForeclosureProperty, status_code=status.HTTP_200_OK)
async def get_foreclosure(property_id: str, db: AsyncSession = Depends(get_db)) -> ForeclosureProperty:
    try:
        pid = UUID(property_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid property id") from exc
    row = (
        await db.execute(select(ForeclosurePropertyORM).where(ForeclosurePropertyORM.id == pid))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    return ForeclosureProperty(
        id=row.id,
        address=row.address,
        city=row.city,
        state=row.state,
        zip=row.zip,
        property_type=row.property_type,
        status=row.status,
        estimated_value_usd=row.estimated_value_usd,
        auction_date=row.auction_date,
        auction_location=row.auction_location,
        minimum_bid=row.minimum_bid,
        source=row.source,
        source_url=row.source_url,
        description=row.description,
        captured_at=row.captured_at,
        is_active=row.is_active,
    )


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_foreclosures(
    payload: ForeclosureRefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, int | str | datetime]:
    inserted = await foreclosure_service.refresh(
        db,
        state=payload.state,
        city=payload.city,
        county=payload.county,
    )
    return {"inserted": inserted, "state": payload.state, "refreshed_at": datetime.utcnow().isoformat()}

