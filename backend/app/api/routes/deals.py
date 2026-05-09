from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.database import get_db
from ...services.deal_finder_service import DealFinderService

router = APIRouter(prefix="/api/deals", tags=["deals"])
deal_finder = DealFinderService()

DealType = Literal["price_drop", "new_listing", "foreclosure", "below_market"]


class DealItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    source: str
    location: str
    price_or_value: Optional[float] = None
    why_deal: str
    deal_type: DealType
    property_type: str
    context: str
    created_at: datetime


class DealSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DealItem]
    total: int


@router.get("/search", response_model=DealSearchResponse, status_code=status.HTTP_200_OK)
async def search_deals(
    city: str = Query(..., min_length=2),
    type: DealType = Query(default="below_market"),  # noqa: A002
    property_type: str = Query(default="any"),
    max_price: Optional[float] = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
) -> DealSearchResponse:
    rows = await deal_finder.search_deals(
        db,
        city=city,
        deal_type=type,
        property_type=property_type,
        max_price=max_price,
    )
    items = [
        DealItem(
            id=r.id,
            description=r.description,
            source=r.source,
            location=r.location,
            price_or_value=r.price_or_value,
            why_deal=r.why_deal,
            deal_type=r.deal_type,
            property_type=r.property_type,
            context=r.context,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return DealSearchResponse(items=items, total=len(items))

