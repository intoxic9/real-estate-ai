from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_groq import ChatGroq

from ...core.config import GROQ_API_KEY_SEARCH
from ...core.database import get_db
from ...core.schemas import MarketSnapshotORM

router = APIRouter(prefix="/api/neighborhood", tags=["neighborhood"])

AREA_ALIASES: dict[str, str] = {
    "new jersey": "new york metro",
    "jersey": "new york metro",
    "jersey city": "new york metro",
    "nyc": "new york metro",
    "new york": "new york metro",
}


class SimilarArea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    median_home_price: float
    relative_to_selected_pct: float


class NeighborhoodReportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area: str
    median_home_price: float
    home_price_trend_pct: float
    median_rent: float
    rent_trend_pct: float
    price_per_sqft: float
    metro_avg_price_per_sqft: float
    price_per_sqft_vs_metro_pct: float
    days_on_market: int
    inventory_months: float
    market_side: Literal["buyers", "balanced", "sellers"]
    mortgage_rate_30y: float
    estimated_monthly_payment: float
    market_summary: str
    best_for_tags: list[str]
    price_forecast: Literal["trending_up", "stable", "cooling"]
    similar_areas: list[SimilarArea]
    generated_at: datetime


class _NeighborhoodLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_summary: str = Field(min_length=20, max_length=500)
    best_for_tags: list[str] = Field(default_factory=list, max_length=4)
    price_forecast: Literal["trending_up", "stable", "cooling"]


async def _fetch_mortgage_rate() -> float:
    key = os.getenv("FRED_API_KEY", "").strip()
    if not key:
        return 6.75
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "MORTGAGE30US",
                    "api_key": key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": 1,
                },
            )
            res.raise_for_status()
            rows = res.json().get("observations", [])
            if rows:
                return float(rows[0].get("value"))
    except Exception:
        return 6.75
    return 6.75


def _monthly_payment(principal: float, annual_rate_pct: float, years: int = 30) -> float:
    r = (annual_rate_pct / 100.0) / 12.0
    n = years * 12
    if r <= 0:
        return principal / n
    return principal * (r * (1 + r) ** n) / (((1 + r) ** n) - 1)


@router.get("/report", response_model=NeighborhoodReportResponse, status_code=status.HTTP_200_OK)
async def get_neighborhood_report(
    area: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
) -> NeighborhoodReportResponse:
    area_norm = area.strip().lower()
    area_norm = AREA_ALIASES.get(area_norm, area_norm)

    async def _query_rows(filter_clause: Any) -> list[MarketSnapshotORM]:
        return (
            await db.execute(
                select(MarketSnapshotORM)
                .where(filter_clause)
                .order_by(desc(MarketSnapshotORM.snapshot_date), desc(MarketSnapshotORM.created_at))
                .limit(24)
            )
        ).scalars().all()

    # 1) Exact match (best).
    latest_rows = await _query_rows(func.lower(MarketSnapshotORM.area) == area_norm)

    # 2) Flexible contains match (e.g. "new york" -> "New York Metro").
    if not latest_rows:
        latest_rows = await _query_rows(func.lower(MarketSnapshotORM.area).ilike(f"%{area_norm}%"))

    # 3) Token fallback (e.g. "new jersey" -> token "jersey").
    if not latest_rows:
        stop_words = {"new", "city", "metro", "county", "state", "the"}
        tokens = [t for t in area_norm.replace(",", " ").split() if t and t not in stop_words]
        if tokens:
            token_clauses = [func.lower(MarketSnapshotORM.area).ilike(f"%{token}%") for token in tokens]
            latest_rows = await _query_rows(or_(*token_clauses))

    if not latest_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No market data found for area '{area}'.")

    latest = latest_rows[0]
    one_year_ago_cutoff = latest.snapshot_date - timedelta(days=365)
    past_candidates = [r for r in latest_rows if r.snapshot_date <= one_year_ago_cutoff]
    past = past_candidates[0] if past_candidates else latest_rows[-1]

    def pct_change(curr: float, prev: float) -> float:
        if prev <= 0:
            return 0.0
        return round(((curr - prev) / prev) * 100.0, 2)

    home_price_trend = pct_change(float(latest.median_sale_price_usd), float(past.median_sale_price_usd))
    rent_trend = pct_change(float(latest.median_rent_usd), float(past.median_rent_usd))

    metro_avg_ppsf = (
        await db.execute(
            select(func.avg(MarketSnapshotORM.price_per_sqft_usd)).where(
                MarketSnapshotORM.snapshot_date == latest.snapshot_date
            )
        )
    ).scalar_one_or_none()
    metro_avg_ppsf_value = float(metro_avg_ppsf or latest.price_per_sqft_usd)
    ppsf_vs_metro = pct_change(float(latest.price_per_sqft_usd), metro_avg_ppsf_value)

    inventory_months = round(max(1.0, min(10.0, (float(latest.days_on_market) / 22.0))), 2)
    if inventory_months >= 6.0:
        market_side: Literal["buyers", "balanced", "sellers"] = "buyers"
    elif inventory_months >= 4.0:
        market_side = "balanced"
    else:
        market_side = "sellers"

    mortgage_rate = await _fetch_mortgage_rate()
    loan_amount = float(latest.median_sale_price_usd) * 0.8
    monthly_payment = _monthly_payment(loan_amount, mortgage_rate)

    # Similar area comparison by nearest latest median price.
    all_latest_rows = (
        await db.execute(
            select(MarketSnapshotORM)
            .where(MarketSnapshotORM.snapshot_date == latest.snapshot_date)
            .order_by(MarketSnapshotORM.area.asc())
        )
    ).scalars().all()
    others = [r for r in all_latest_rows if r.area.lower() != latest.area.lower()]
    others_sorted = sorted(
        others,
        key=lambda x: abs(float(x.median_sale_price_usd) - float(latest.median_sale_price_usd)),
    )[:3]

    similar = [
        SimilarArea(
            area=r.area,
            median_home_price=float(r.median_sale_price_usd),
            relative_to_selected_pct=pct_change(float(r.median_sale_price_usd), float(latest.median_sale_price_usd)),
        )
        for r in others_sorted
    ]

    # LLM insights (fallback to deterministic text if key missing/fails).
    summary = (
        f"{latest.area} currently looks like a {market_side} market with median pricing at "
        f"${latest.median_sale_price_usd:,.0f} and about {latest.days_on_market} days on market. "
        f"Over roughly 12 months, home prices moved {home_price_trend:+.2f}% and rents moved {rent_trend:+.2f}%."
    )
    tags = ["Families", "First-time buyers"] if market_side != "sellers" else ["Sellers", "Move-up buyers"]
    forecast: Literal["trending_up", "stable", "cooling"] = (
        "trending_up" if home_price_trend > 2 else "cooling" if home_price_trend < -2 else "stable"
    )

    api_key = (GROQ_API_KEY_SEARCH or os.getenv("GROQ_API_KEY", "")).strip()
    if api_key:
        try:
            model_name = os.getenv("NEIGHBORHOOD_MODEL", "llama-3.3-70b-versatile")
            llm = ChatGroq(api_key=api_key, model=model_name, temperature=0.7).with_structured_output(_NeighborhoodLLMOutput)
            llm_out = await llm.ainvoke(
                [
                    (
                        "system",
                        "You are a US housing market analyst. Use supplied metrics to produce concise, practical neighborhood insights.",
                    ),
                    (
                        "user",
                        (
                            f"Area: {latest.area}\n"
                            f"Median home price: {latest.median_sale_price_usd}\n"
                            f"Home price 12m trend pct: {home_price_trend}\n"
                            f"Median rent: {latest.median_rent_usd}\n"
                            f"Rent trend pct: {rent_trend}\n"
                            f"Price per sqft: {latest.price_per_sqft_usd}\n"
                            f"Price per sqft vs metro pct: {ppsf_vs_metro}\n"
                            f"Days on market: {latest.days_on_market}\n"
                            f"Inventory months: {inventory_months}\n"
                            f"Market side: {market_side}\n"
                            "Return market summary, best-for tags, and price forecast."
                        ),
                    ),
                ]
            )
            summary = llm_out.market_summary
            tags = llm_out.best_for_tags or tags
            forecast = llm_out.price_forecast
        except Exception:
            pass

    return NeighborhoodReportResponse(
        area=latest.area,
        median_home_price=float(latest.median_sale_price_usd),
        home_price_trend_pct=home_price_trend,
        median_rent=float(latest.median_rent_usd),
        rent_trend_pct=rent_trend,
        price_per_sqft=float(latest.price_per_sqft_usd),
        metro_avg_price_per_sqft=metro_avg_ppsf_value,
        price_per_sqft_vs_metro_pct=ppsf_vs_metro,
        days_on_market=int(latest.days_on_market),
        inventory_months=inventory_months,
        market_side=market_side,
        mortgage_rate_30y=round(mortgage_rate, 2),
        estimated_monthly_payment=round(monthly_payment, 2),
        market_summary=summary,
        best_for_tags=tags[:4],
        price_forecast=forecast,
        similar_areas=similar,
        generated_at=datetime.now(timezone.utc),
    )

